"""Which cases a skills change can affect, so a PR runs those instead of every case.

A case is affected when a nightly baseline trial of it read a changed reference file, or when the
case itself changed or is new. Reads come from the agent's tool-call arguments (`cat .../metrics.md`),
never tool output: every transcript holds SKILL.md, which names every reference file.

Modes:
- `none`: nothing under skills/ or the cases changed;
- `cases`: run these cases and gate them against the baseline;
- `all`: SKILL.md or a file outside references/ changed; every case reads it;
- `ab`: the runner or harness changed, so the baseline is not comparable; run both sides;
- `stale`: platform changed skills, cases or the runner since the branch forked; merge platform
  first, or the candidate would be measured without those changes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from .cases import _git, case_hash, load_cases

SKILLS = "skills/"
CASES_FILE = "evals/evals.json"
CODE_DIRS = ("evals/runner/", "evals/tfy_eval/")
# Runner files that neither produce nor grade an answer: changing one keeps runs comparable.
RUNNER_TOOLING = frozenset({
    "README.md", ".env.example", "affected.py", "gate.py", "handgrade.py", "seed_fixtures.py", "selftest.py",
})


def is_code(path: str) -> bool:
    return path.startswith(CODE_DIRS) and not (
        path.startswith("evals/runner/") and PurePosixPath(path).name in RUNNER_TOOLING)


@dataclass
class Affected:
    mode: str
    cases: list[str] = field(default_factory=list)
    reason: str = ""

    def to_json(self) -> str:
        return json.dumps({"mode": self.mode, "cases": self.cases, "only": ",".join(self.cases), "reason": self.reason})


def _changed(repo: Path, since: str, until: str) -> list[str]:
    return [line for line in _git(repo, "diff", "--name-only", f"{since}...{until}").splitlines() if line]


def reads_by_case(run_dir: Path) -> dict[str, set[str]]:
    """File names each case's trials named in a tool call, over all its baseline trials."""
    reads: dict[str, set[str]] = {}
    for path in (run_dir / "transcripts").glob("*.json"):
        case_id = path.stem.rsplit("-", 1)[0]
        arguments = " ".join(
            str(call.get("arguments", ""))
            for entry in json.loads(path.read_text())
            for call in entry.get("tool_calls", [])
        )
        reads.setdefault(case_id, set()).add(arguments)
    return reads


def affected(repo: Path, baseline_dir: Path, head: str) -> Affected:
    config = json.loads((baseline_dir / "config.json").read_text())
    base = config["skills_sha"]

    if any(path.startswith(SKILLS) or is_code(path) or path == CASES_FILE for path in _changed(repo, head, base)):
        return Affected("stale", reason=f"the baseline commit {base[:12]} has skills, case or runner changes "
                                        "this branch lacks; merge platform")

    changed = _changed(repo, base, head)
    code = [path for path in changed if is_code(path)]
    if code:
        return Affected("ab", reason=f"runner or harness changed: {', '.join(code)}")

    cases, _ = load_cases(repo, head)
    ids = [case.id for case in cases]
    base_hashes = config["case_hashes"]
    case_changes = {case.id for case in cases if base_hashes.get(case.id) != case_hash(case)}

    skill_files = [path for path in changed if path.startswith(SKILLS)]
    if not skill_files and not case_changes:
        return Affected("none", reason="no skills or case changes")
    outside = [path for path in skill_files if "/references/" not in path]
    if outside:
        return Affected("all", ids, reason=f"{', '.join(outside)} is read by every case")

    names = {PurePosixPath(path).name for path in skill_files}
    reads = reads_by_case(baseline_dir)
    readers = {case_id for case_id in ids if any(name in text for name in names for text in reads.get(case_id, ()))}
    chosen = [case_id for case_id in ids if case_id in readers | case_changes]
    if not chosen:
        return Affected("none", reason=f"no baseline trial read {', '.join(sorted(names))}")
    reason = f"read {', '.join(sorted(names))}" if names else ""
    if case_changes:
        reason += ("; " if reason else "") + f"changed or new: {', '.join(sorted(case_changes))}"
    return Affected("cases", chosen, reason=reason)
