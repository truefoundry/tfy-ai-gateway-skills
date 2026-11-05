"""python -m runner probe | run | ab | gate | affected

    probe     create one Ask TFY session on a skills commit and check sfy pinned it (no turn, no cost)
    run       run the eval cases on that commit as a LangSmith experiment, plus a local run directory
    ab        run a baseline and a candidate commit side by side, then gate the candidate
    gate      compare candidate run directories with baseline ones; exit 1 on regression
    affected  which cases a skills commit affects, from what a baseline run's trials read

Connection settings come from the environment (see README.md); flags win over it. Nothing has a
default host, tenant or judge: a runner that guesses where it points produces numbers nobody can
reproduce.
"""

from __future__ import annotations

import argparse
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from langsmith import Client
from tfy_eval.judge import DEFAULT_NUMERIC_TOLERANCE

from . import gate as gate_mod
from .affected import affected
from .asktfy import PinMismatch, PinnedAskTfy, probe
from .cases import case_hash, load_cases, resolve_commit
from .experiment import Settings, example_id, execute, run_experiment, start_experiment, sync_dataset

HERE = Path(__file__).resolve().parent
RUNS_DIR = HERE / "runs"
WRITES_ALLOWED = HERE / "writes-allowed.txt"


def _need(value: str | None, flag: str, env: str) -> str:
    if not value:
        sys.exit(f"No {flag.lstrip('-')}: set {env} or pass {flag}")
    return value


def _positive(kind: type):
    def parse(text: str):
        value = kind(text)
        if value <= 0:
            raise argparse.ArgumentTypeError(f"must be positive, got {text}")
        return value
    return parse


def _writes_allowed() -> frozenset[str]:
    lines = WRITES_ALLOWED.read_text().splitlines() if WRITES_ALLOWED.exists() else []
    return frozenset(line.split("#", 1)[0].strip() for line in lines if line.split("#", 1)[0].strip())


def _check_writes_allowed(*sides: Settings) -> None:
    """Every allow-listed case must exist on some side; an `ab` candidate may add a write case."""
    known = set().union(*(set(side.case_ids) | set(side.skipped) for side in sides))
    unknown = _writes_allowed() - known
    if unknown:
        sys.exit(f"{WRITES_ALLOWED.name} names cases that do not exist: {', '.join(sorted(unknown))}")


def _repo(args: argparse.Namespace) -> Path:
    return Path(args.skills_repo).expanduser() if args.skills_repo else HERE.parents[1]


def cmd_probe(args: argparse.Namespace) -> None:
    sha = resolve_commit(_repo(args), args.skills_ref)
    client = PinnedAskTfy(
        _need(args.host, "--host", "ASK_TFY_HOST"),
        _need(args.tenant, "--tenant", "ASK_TFY_TENANT"),
        _need(args.token, "--token", "TFY_API_KEY"),
        sha,
        args.timeout,
    )
    try:
        stamped = probe(client)
    except PinMismatch as exc:
        sys.exit(f"FAIL: {exc}")
    print(f"OK: sfy pinned the session to {sha}")
    for key in ("skillsRef", "modelIdentifier", "modelSource", "tenantName", "subjectSlug"):
        print(f"  {key:16} {stamped.get(key)}")


def _settings(args: argparse.Namespace, ref: str, run_dir: Path | None = None) -> tuple[Settings, list]:
    repo = _repo(args)
    sha = resolve_commit(repo, ref)
    only = {case.strip() for case in args.only.split(",") if case.strip()} if args.only else None
    all_cases, _ = load_cases(repo, sha)
    cases, skipped = load_cases(repo, sha, only)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    settings = Settings(
        host=_need(args.host, "--host", "ASK_TFY_HOST"),
        tenant=_need(args.tenant, "--tenant", "ASK_TFY_TENANT"),
        token=_need(args.token, "--token", "TFY_API_KEY"),
        judge_base_url=_need(args.judge_base_url, "--judge-base-url", "TRUEFORGE_BASE_URL"),
        judge_token=_need(args.judge_token or args.token, "--judge-token", "TRUEFORGE_TOKEN"),
        judge_model=_need(args.judge_model, "--judge-model", "TRUEFORGE_JUDGE_MODEL"),
        skills_ref=ref,
        skills_sha=sha,
        dataset_name=args.dataset_name,
        run_dir=run_dir or RUNS_DIR / f"{stamp}-{sha[:8]}",
        repeats=args.repeats,
        concurrency=args.concurrency,
        judge_repeats=args.judge_repeats,
        pass_threshold=args.pass_threshold,
        numeric_tolerance=args.numeric_tolerance,
        timeout=args.timeout,
        max_rounds=args.max_rounds,
        retries=args.retries,
        max_reconnects=args.max_reconnects,
        writes_allowed=_writes_allowed() & {case.id for case in all_cases},
        case_ids=tuple(case.id for case in cases),
        skipped=skipped,
        allow_dirty=args.allow_dirty,
        all_case_hashes={case.id: case_hash(case) for case in all_cases},
    )
    return settings, cases


def cmd_run(args: argparse.Namespace) -> None:
    settings, cases = _settings(args, args.skills_ref, Path(args.run) if args.run else None)
    _check_writes_allowed(settings)
    try:
        run_experiment(settings, cases)
    except PinMismatch as exc:
        sys.exit(f"FAIL before running any case: {exc}")


def cmd_ab(args: argparse.Namespace) -> None:
    base, base_cases = _settings(args, args.baseline_ref)
    cand, cand_cases = _settings(args, args.skills_ref)
    if base.skills_sha == cand.skills_sha:
        sys.exit(f"baseline and candidate are the same commit {base.skills_sha[:12]}")
    _check_writes_allowed(base, cand)
    # Same moment, same devtest state; split the concurrency so the pair loads devtest like one run.
    half = max(1, args.concurrency // 2)
    base = replace(base, run_dir=base.run_dir.with_name(base.run_dir.name + "-base"), concurrency=half)
    cand = replace(cand, run_dir=cand.run_dir.with_name(cand.run_dir.name + "-cand"), concurrency=half)
    # Everything that can fail cheaply fails here, before either side spends a turn.
    try:
        sides = [start_experiment(base, base_cases), start_experiment(cand, cand_cases)]
    except PinMismatch as exc:
        sys.exit(f"FAIL before running any case: {exc}")
    examples = sync_dataset(Client(), args.dataset_name, base_cases + cand_cases, cand.skills_sha)
    by_id = {example.id: example for example in examples}
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = {
            pool.submit(execute, side, [by_id[example_id(args.dataset_name, c)] for c in side.cases.values()]): side
            for side in sides
        }
        failed = None
        for job in as_completed(jobs):
            if job.exception() is not None and failed is None:
                failed = job.exception()
                for side in sides:
                    side.aborted = side.aborted or f"the other side failed: {failed}"
    if failed is not None:
        sys.exit(f"FAIL: {failed}")
    _gate([base.run_dir], [cand.run_dir], args)


def _gate(baseline: list[Path], candidate: list[Path], args: argparse.Namespace) -> None:
    accept = frozenset(c.strip() for c in (args.accept or "").split(",") if c.strip())
    result = gate_mod.compare(baseline, candidate, max_unmeasured=args.max_unmeasured, alpha=args.alpha, accept=accept)
    print(gate_mod.render(result, baseline, candidate))
    sys.exit(0 if result.passed else 1)


def cmd_gate(args: argparse.Namespace) -> None:
    _gate([Path(d) for d in args.baseline], [Path(d) for d in args.candidate], args)


def cmd_affected(args: argparse.Namespace) -> None:
    repo = _repo(args)
    print(affected(repo, Path(args.baseline), resolve_commit(repo, args.skills_ref)).to_json())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m runner", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    target = argparse.ArgumentParser(add_help=False)
    target.add_argument("--host", default=os.environ.get("ASK_TFY_HOST"),
                        help="control plane URL whose sfy serves Ask TFY")
    target.add_argument("--tenant", default=os.environ.get("ASK_TFY_TENANT"), help="tenant the PAT belongs to")
    target.add_argument("--token", default=os.environ.get("TFY_API_KEY"), help="TrueFoundry PAT")
    target.add_argument("--skills-repo", default=os.environ.get("TFY_SKILLS_REPO"),
                        help="clone of tfy-ai-gateway-skills to read commits from (default: the one this runner is in)")
    target.add_argument("--skills-ref", default="origin/platform",
                        help="branch, tag or commit to test; resolved to a full SHA that must be on origin")
    target.add_argument("--timeout", type=_positive(float), default=900.0, help="per-request timeout (s)")

    running = argparse.ArgumentParser(add_help=False)
    running.add_argument("--judge-base-url", default=os.environ.get("TRUEFORGE_BASE_URL"),
                         help="TrueForge URL the judge runs on, including /trueforge")
    running.add_argument("--judge-token", default=os.environ.get("TRUEFORGE_TOKEN"), help="defaults to --token")
    running.add_argument("--judge-model", default=os.environ.get("TRUEFORGE_JUDGE_MODEL"))
    running.add_argument("--judge-repeats", type=_positive(int), default=1, help="judge each answer N times, take the median")
    running.add_argument("--pass-threshold", type=float, default=0.7)
    running.add_argument("--numeric-tolerance", type=float, default=DEFAULT_NUMERIC_TOLERANCE)
    running.add_argument("--repeats", type=_positive(int), default=3,
                         help="trials per case; the gate needs 3 for a single case to reach significance")
    running.add_argument("--concurrency", type=_positive(int), default=4)
    running.add_argument("--only", help="comma-separated case ids, e.g. s1,s74")
    running.add_argument("--dataset-name", default="ask-tfy-core", help="LangSmith dataset")
    running.add_argument("--max-rounds", type=_positive(int), default=8,
                         help="pause/resume rounds per trial; each question and each approval is one")
    running.add_argument("--retries", type=int, default=2, help="fresh-session retries on infrastructure failure")
    running.add_argument("--max-reconnects", type=int, default=8)
    running.add_argument("--allow-dirty", action="store_true",
                         help="run with uncommitted harness or runner changes (not reproducible; for trying things)")

    gating = argparse.ArgumentParser(add_help=False)
    gating.add_argument("--max-unmeasured", type=float, default=0.1, help="largest share of unmeasured trials allowed")
    gating.add_argument("--alpha", type=float, default=0.05, help="significance level for regressions")
    gating.add_argument("--accept", help="comma-separated case ids whose change or removal is intended")

    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("probe", parents=[target], help="check sfy pins a session to the skills commit")
    p.set_defaults(func=cmd_probe)

    r = sub.add_parser("run", parents=[target, running], help="run the eval cases as a LangSmith experiment")
    r.add_argument("--run", help="run directory (default: runner/runs/<time>-<sha>)")
    r.set_defaults(func=cmd_run)

    a = sub.add_parser("ab", parents=[target, running, gating],
                       help="run baseline and candidate side by side, then gate (--skills-ref is the candidate)")
    a.add_argument("--baseline-ref", default="origin/platform", help="commit to compare against")
    a.set_defaults(func=cmd_ab)

    g = sub.add_parser("gate", parents=[gating], help="compare candidate runs with baseline runs")
    g.add_argument("--baseline", required=True, nargs="+", help="baseline run directories, pooled")
    g.add_argument("--candidate", required=True, nargs="+", help="candidate run directories, pooled")
    g.set_defaults(func=cmd_gate)

    f = sub.add_parser("affected", parents=[target], help="which cases a skills commit affects, as JSON")
    f.add_argument("--baseline", required=True, help="baseline run directory whose transcripts show what each case read")
    f.set_defaults(func=cmd_affected)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    args.func(args)
