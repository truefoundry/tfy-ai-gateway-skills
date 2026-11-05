"""Did a candidate skills commit make Ask TFY worse than a baseline?

Each side is one or more complete run directories on the same commit, pooled. Run the two sides
back to back (`python -m runner ab`): devtest data and deployments drift, so a week-old baseline
confounds the comparison.

The gate fails on:
- a regression: a case whose candidate pass rate is significantly below its baseline pass rate
  (one-sided Fisher exact test, Holm-corrected across the compared cases, or testing 75 cases
  would fail most unchanged runs by chance). With 3 trials a side no single case can reach that,
  so the overall test carries the gate and big per-case drops are listed to watch; pool more runs
  of each side to make single cases decisive;
- an aggregate regression: pass rates across all compared cases dropped (paired sign-flip test);
- runs that are not comparable: a different agent model, judge, harness, runner or tenant;
- cases that changed or disappeared, unless accepted explicitly: a PR must not be able to weaken
  or delete the case it fails;
- too many unmeasured trials on either side, a missing trial counting as unmeasured, or a case
  measured on the baseline that is mostly unmeasured on the candidate (skills can cause
  "infrastructure" failures too: context overflow, loops, a server that needs a login);
- a write in the candidate that was never put to approval;
- any trial that read the eval cases file.

A trial is a pass, a fail, or unmeasured (infrastructure failure, judge error). Agent failures
(step limit, stalling, empty answer) are fails.
"""

from __future__ import annotations

import itertools
import json
import random
from dataclasses import dataclass, field
from math import comb
from pathlib import Path

# Anything that changes how an answer is produced or graded, other than the skills.
DRIFT_KEYS = (
    "model", "model_source", "base_url", "tenant", "max_rounds", "writes_allowed",
    "harness", "runner", "judge_model", "judge_version", "judge_repeats", "pass_threshold", "numeric_tolerance",
)
EXACT_SIGN_FLIP_LIMIT = 16
SIGN_FLIP_SAMPLES = 20000


class GateError(SystemExit):
    pass


@dataclass
class CaseOutcome:
    passes: int = 0
    fails: int = 0
    unmeasured: int = 0

    @property
    def measured(self) -> int:
        return self.passes + self.fails

    @property
    def rate(self) -> float:
        return self.passes / self.measured if self.measured else 0.0


@dataclass
class Side:
    dirs: list[Path]
    config: dict
    case_hashes: dict[str, str]
    all_case_hashes: dict[str, str]
    outcomes: dict[str, CaseOutcome]
    unapproved_writes: dict[str, list[str]]
    answer_key_reads: list[str]

    @property
    def unmeasured_share(self) -> float:
        total = sum(o.measured + o.unmeasured for o in self.outcomes.values())
        return sum(o.unmeasured for o in self.outcomes.values()) / total if total else 1.0


@dataclass
class GateResult:
    regressions: list[tuple[str, CaseOutcome, CaseOutcome, float]] = field(default_factory=list)
    watch: list[tuple[str, CaseOutcome, CaseOutcome, float]] = field(default_factory=list)
    fixed: list[tuple[str, CaseOutcome, CaseOutcome, float]] = field(default_factory=list)
    new_cases: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    accepted: list[str] = field(default_factory=list)
    not_run: list[str] = field(default_factory=list)
    lost: list[tuple[str, CaseOutcome, CaseOutcome]] = field(default_factory=list)
    answer_key_reads: list[str] = field(default_factory=list)
    drift: dict[str, tuple] = field(default_factory=dict)
    unmeasured: dict[str, float] = field(default_factory=dict)
    unapproved_writes: dict[str, list[str]] = field(default_factory=dict)
    aggregate_delta: float = 0.0
    aggregate_p: float = 1.0
    aggregate_cases: int = 0
    min_trials: int = 0
    max_unmeasured: float = 0.1
    alpha: float = 0.05

    @property
    def aggregate_regression(self) -> bool:
        return self.aggregate_delta < 0 and self.aggregate_p <= self.alpha

    @property
    def passed(self) -> bool:
        return not (
            self.regressions or self.aggregate_regression or self.drift or self.changed or self.removed
            or self.lost or self.unapproved_writes or self.answer_key_reads
            or any(share > self.max_unmeasured for share in self.unmeasured.values())
        )


def holm(p_values: dict[str, float], alpha: float) -> set[str]:
    """The keys Holm's step-down procedure rejects at family-wise error rate alpha."""
    rejected = set()
    ordered = sorted(p_values.items(), key=lambda item: item[1])
    for rank, (key, p) in enumerate(ordered):
        if p > alpha / (len(ordered) - rank):
            break
        rejected.add(key)
    return rejected


def fisher_less(base_pass: int, base_fail: int, cand_pass: int, cand_fail: int) -> float:
    """P(candidate passes <= observed) if both sides shared one pass rate (one-sided Fisher exact)."""
    total, passes, cand = base_pass + base_fail + cand_pass + cand_fail, base_pass + cand_pass, cand_pass + cand_fail
    if not cand or not (base_pass + base_fail):
        return 1.0
    denominator = comb(total, cand)
    low = max(0, cand - (total - passes))
    return sum(comb(passes, x) * comb(total - passes, cand - x) for x in range(low, cand_pass + 1)) / denominator


def sign_flip_p(deltas: list[float]) -> float:
    """One-sided paired test: how often random signs give a mean drop at least this large."""
    nonzero = [d for d in deltas if d]
    if not nonzero:
        return 1.0
    observed = sum(nonzero)
    if len(nonzero) <= EXACT_SIGN_FLIP_LIMIT:
        flips = list(itertools.product((1, -1), repeat=len(nonzero)))
    else:
        rng = random.Random(0)
        flips = [[rng.choice((1, -1)) for _ in nonzero] for _ in range(SIGN_FLIP_SAMPLES)]
    as_low = sum(1 for signs in flips if sum(s * abs(d) for s, d in zip(signs, nonzero)) <= observed + 1e-12)
    return as_low / len(flips)


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


def load_side(dirs: list[Path]) -> Side:
    configs, hashes, all_hashes, outcomes, writes, key_reads = [], {}, {}, {}, {}, []
    for run_dir in dirs:
        if (run_dir / "ABORTED").exists():
            raise GateError(f"{run_dir} was aborted: {(run_dir / 'ABORTED').read_text().strip()}")
        if not (run_dir / "summary.json").exists() or not (run_dir / "config.json").exists():
            raise GateError(f"{run_dir} is not a complete run (no summary.json); it may have crashed or be running")
        config = json.loads((run_dir / "config.json").read_text())
        configs.append(config)
        run_hashes = config.get("case_hashes")
        if run_hashes is None:
            raise GateError(f"{run_dir} predates case hashes; rerun it with the current runner")
        for case_id, digest in run_hashes.items():
            if hashes.setdefault(case_id, digest) != digest:
                raise GateError(f"case {case_id} differs between pooled runs ({run_dir.name})")
        all_hashes.update(config.get("all_case_hashes") or run_hashes)

        trials: dict[str, dict] = {}
        for grade in _read_jsonl(run_dir / "grades.jsonl"):
            trial = grade.get("trial", -1)
            # A trial that crashed before it had a number cannot collide with a real one.
            key = f"{trial}" if trial >= 0 else f"x{len(trials)}"
            trials.setdefault(grade["question_id"], {})[key] = grade
        repeats = int(config["repeats"])
        for case_id in run_hashes:
            outcome = outcomes.setdefault(case_id, CaseOutcome())
            graded = list(trials.get(case_id, {}).values())[:repeats]
            for grade in graded:
                if grade["verdict"] == "ungraded":
                    outcome.unmeasured += 1
                elif grade["verdict"] == "correct":
                    outcome.passes += 1
                else:
                    outcome.fails += 1
            outcome.unmeasured += repeats - len(graded)
        for answer in _read_jsonl(run_dir / "answers.jsonl"):
            trial = f"{run_dir.name}/{answer['question_id']}#{answer['trial']}"
            if answer.get("unapproved_writes"):
                writes[trial] = answer["unapproved_writes"]
            if answer.get("answer_key_reads"):
                key_reads.append(trial)

    same = ("skills_sha",) + DRIFT_KEYS
    for config, run_dir in zip(configs[1:], dirs[1:]):
        differing = [key for key in same if config.get(key) != configs[0].get(key)]
        if differing:
            raise GateError(f"cannot pool {run_dir} with {dirs[0]}: differs in {', '.join(differing)}")
    return Side(dirs=dirs, config=configs[0], case_hashes=hashes, all_case_hashes=all_hashes, outcomes=outcomes,
                unapproved_writes=writes, answer_key_reads=key_reads)


def compare(
    baseline_dirs: list[Path],
    candidate_dirs: list[Path],
    *,
    max_unmeasured: float = 0.1,
    alpha: float = 0.05,
    accept: frozenset[str] = frozenset(),
) -> GateResult:
    base, cand = load_side(baseline_dirs), load_side(candidate_dirs)
    result = GateResult(max_unmeasured=max_unmeasured, alpha=alpha)
    result.drift = {
        key: (base.config.get(key), cand.config.get(key))
        for key in DRIFT_KEYS
        if base.config.get(key) != cand.config.get(key)
    }
    result.unmeasured = {"baseline": base.unmeasured_share, "candidate": cand.unmeasured_share}
    result.unapproved_writes = cand.unapproved_writes
    result.answer_key_reads = base.answer_key_reads + cand.answer_key_reads
    result.min_trials = min(
        [o.measured for o in base.outcomes.values()] + [o.measured for o in cand.outcomes.values()] or [0]
    )

    deltas, compared = [], {}
    for case_id in sorted(set(base.case_hashes) | set(cand.all_case_hashes), key=_case_order):
        if case_id not in cand.all_case_hashes:
            (result.accepted if case_id in accept else result.removed).append(case_id)
            continue
        if case_id not in cand.case_hashes:
            if base.all_case_hashes.get(case_id) != cand.all_case_hashes[case_id]:
                raise GateError(f"case {case_id} changed but the candidate did not run it")
            result.not_run.append(case_id)
            continue
        if case_id not in base.case_hashes:
            result.new_cases.append(case_id)
            continue
        if base.case_hashes[case_id] != cand.case_hashes[case_id]:
            (result.accepted if case_id in accept else result.changed).append(case_id)
            continue
        before, now = base.outcomes[case_id], cand.outcomes[case_id]
        if before.measured > before.unmeasured and now.unmeasured > now.measured:
            result.lost.append((case_id, before, now))
        if not before.measured or not now.measured:
            continue
        deltas.append(now.rate - before.rate)
        compared[case_id] = (before, now)
    worse = {cid: fisher_less(b.passes, b.fails, n.passes, n.fails) for cid, (b, n) in compared.items()}
    better = {cid: fisher_less(n.passes, n.fails, b.passes, b.fails) for cid, (b, n) in compared.items()}
    regressed, fixed = holm(worse, alpha), holm(better, alpha)
    for case_id, (before, now) in compared.items():
        if case_id in regressed:
            result.regressions.append((case_id, before, now, worse[case_id]))
        elif before.rate >= 2 / 3 and now.rate <= 1 / 3:
            result.watch.append((case_id, before, now, worse[case_id]))
        elif case_id in fixed:
            result.fixed.append((case_id, before, now, better[case_id]))
    result.aggregate_cases = len(deltas)
    result.aggregate_delta = sum(deltas) / len(deltas) if deltas else 0.0
    result.aggregate_p = sign_flip_p(deltas)
    return result


def _fmt(outcome: CaseOutcome) -> str:
    return f"{outcome.passes}/{outcome.measured}" + (f" (+{outcome.unmeasured} unmeasured)" if outcome.unmeasured else "")


def render(result: GateResult, baseline_dirs: list[Path], candidate_dirs: list[Path]) -> str:
    def cases(rows: list) -> str:
        return ", ".join(f"{cid} {_fmt(b)} -> {_fmt(c)} (p={p:.3f})" for cid, b, c, p in rows) if rows else "none"

    lines = [
        f"## Ask TFY eval gate: {'PASS' if result.passed else 'FAIL'}",
        "",
        f"Baseline {', '.join(d.name for d in baseline_dirs)}; candidate {', '.join(d.name for d in candidate_dirs)}.",
        "",
        f"- Regressions (significantly fewer passes, Holm-corrected at {result.alpha}): {cases(result.regressions)}",
        f"- Overall: pass rate {result.aggregate_delta:+.1%} across {result.aggregate_cases} cases "
        f"(p={result.aggregate_p:.3f}){' - REGRESSION' if result.aggregate_regression else ''}",
        f"- Watch (looks worse, not significant; pool another run of each side): {cases(result.watch)}",
        f"- Fixed: {cases(result.fixed)}",
        f"- New cases: {', '.join(result.new_cases) or 'none'}",
        f"- Changed cases, not compared (accept with --accept): {', '.join(result.changed) or 'none'}",
        f"- Removed cases (accept with --accept): {', '.join(result.removed) or 'none'}",
        f"- Accepted changes or removals: {', '.join(result.accepted) or 'none'}",
        f"- Not run by the candidate (unchanged, not affected): {len(result.not_run)}",
        f"- Unmeasured trials: baseline {result.unmeasured['baseline']:.0%}, "
        f"candidate {result.unmeasured['candidate']:.0%} (limit {result.max_unmeasured:.0%})",
    ]
    for key, (before, after) in result.drift.items():
        # The gate is posted on a public repo; where Ask TFY runs is not shown there.
        values = "" if key in ("base_url", "tenant") else f": {before!r} -> {after!r}"
        lines.append(f"- Not comparable, `{key}` differs{values}")
    for case_id, before, now in result.lost:
        lines.append(f"- Mostly unmeasured on the candidate only: {case_id} {_fmt(before)} -> {_fmt(now)}")
    for trial, writes in result.unapproved_writes.items():
        lines.append(f"- Write never put to approval in {trial}: {', '.join(writes)}")
    for trial in result.answer_key_reads:
        lines.append(f"- Read the eval cases file, so its grade means nothing: {trial}")
    if result.aggregate_cases and result.min_trials < 6:
        lines.append(f"- Note: with {result.min_trials} measured trial(s) a side, a single case can hardly be "
                     "significant after correcting for the number of cases; the overall test carries the gate.")
    return "\n".join(lines)


def _case_order(case_id: str) -> tuple:
    digits = case_id.lstrip("s")
    return (0, int(digits)) if digits.isdigit() else (1, case_id)
