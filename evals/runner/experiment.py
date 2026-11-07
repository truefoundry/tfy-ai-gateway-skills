"""One experiment: every case, repeated, through Ask TFY on one skills commit.

LangSmith's `evaluate()` drives it: the target is the harness's `run_question` against sfy, and
the evaluators are the harness judge plus code checks. Every trial is also written as a tfy_eval
run directory, so `python -m tfy_eval report` and the gate read it without LangSmith.

A trial ends one of three ways:
- answered: graded by the judge;
- an agent failure (step limit, stalled on approvals, empty answer): a fail, since that is what a
  user would have got;
- an infrastructure failure (dropped turn, model error, MCP login): retried by the harness, then
  left unmeasured, never counted as pass or fail.
"""

from __future__ import annotations

import json
import re
import subprocess
import threading
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langsmith import Client
from langsmith.schemas import Example, Run
from tfy_eval import agent as agent_mod
from tfy_eval import dataset as dataset_mod
from tfy_eval import judge as judge_mod
from tfy_eval import report as report_mod
from tfy_eval.dataset import Question

from . import redaction
from .asktfy import AGENT, PinnedAskTfy, probe
from .cases import case_hash, fill, is_regression

RUNNER_DIR = Path(__file__).resolve().parent

# Example ids derive from the dataset, the case id and the case content: an edited case is a new
# example, so LangSmith only lines up experiments on cases that asked the same thing.
EXAMPLE_NAMESPACE = uuid.UUID("5b0c7f3e-2f1a-4c52-9a43-6f1d2d6c4e11")

# Tools that change state. The harness denies these unless the case is in writes-allowed.txt, but
# which calls pause for approval is decided by tool annotations on the server; this is the
# runner's own check that every write it saw was actually put to it.
WRITE_TOOL = re.compile(
    r"^(apply|create|update|delete|patch|restart|register|invite|deactivate|activate|reset|remove|add|set|"
    r"revoke|scale|redeploy|deploy|cancel|terminate|rotate|pause|resume|promote|rollback|trigger|"
    r"upload|send|assign|unassign|enable|disable)_"
)


@dataclass(frozen=True)
class Settings:
    host: str
    tenant: str
    token: str
    judge_base_url: str
    judge_token: str
    judge_model: str
    skills_ref: str
    skills_sha: str
    dataset_name: str
    run_dir: Path
    repeats: int
    concurrency: int
    judge_repeats: int
    pass_threshold: float
    numeric_tolerance: float
    timeout: float
    max_rounds: int
    retries: int
    max_reconnects: int
    writes_allowed: frozenset[str]
    skipped: dict[str, str]
    case_ids: tuple[str, ...] = ()
    allow_dirty: bool = False
    # Every runnable case at the commit, so a run of a few cases is not read as deleting the rest.
    all_case_hashes: dict[str, str] | None = None
    # Values for the cases' {{...}} placeholders, from seed_fixtures.
    fixtures: dict[str, str] | None = None


ANSWER_KEY = "evals.json"
SANDBOX_FAILED = "Sandbox initialization failed"
ANSWER_KEY_LINE = re.compile(r"evals\.json:\d+:")


def is_write(tool: str) -> bool:
    return bool(WRITE_TOOL.match(agent_mod.tool_label_name(tool).rsplit("/", 1)[-1]))


def attempts(run: agent_mod.AgentRun) -> list[agent_mod.AgentRun]:
    return [*run.earlier_attempts, run]


def sandbox_failure(run: agent_mod.AgentRun) -> str | None:
    """The error of a sandbox that never started. Without one no skill is loaded, so the answer
    measures the bare model, not the skills."""
    for attempt in attempts(run):
        for entry in attempt.transcript:
            content = str(entry.get("content", "")) if entry.get("type") == "tool.response" else ""
            if SANDBOX_FAILED in content:
                return content[content.index(SANDBOX_FAILED):][:300]
    return None


def unapproved_writes(run: agent_mod.AgentRun) -> list[str]:
    """Writes the agent made, in any attempt, that were never put to the user.

    A direct MCP write is approved when its own call id was put to approval. Sandbox programs
    have no approval path at all, so every write they make counts.
    """
    found = []
    for attempt in attempts(run):
        asked = set(attempt.approval_call_ids)
        found += [call["tool"] for call in agent_mod.mcp_invocations(attempt.transcript)
                  if is_write(call["tool"]) and call["id"] not in asked]
        found += [f"sandbox/{call}" for call in attempt.sandbox_tool_calls if is_write(call)]
    return found


def answer_key_reads(run: agent_mod.AgentRun) -> int:
    """Tool calls that read the eval cases file, which older skills commits ship in the sandbox:
    by naming it, or through a search whose output quotes its lines. A listing that only shows
    the file name does not count."""
    reads = 0
    for attempt in attempts(run):
        for entry in attempt.transcript:
            reads += sum(ANSWER_KEY in str(call.get("arguments", "")) for call in entry.get("tool_calls", []))
            if entry.get("type") == "tool.response":
                reads += bool(ANSWER_KEY_LINE.search(str(entry.get("content", ""))))
    return reads


def git_version(directory: Path) -> str:
    """The committed tree of one directory: unchanged by commits that touch only skills or cases."""
    def git(*args: str) -> str:
        return subprocess.run(["git", "-C", str(directory), *args], check=True, capture_output=True, text=True).stdout.strip()

    dirty = git("status", "--porcelain", "--", ".")
    return git("rev-parse", "HEAD:./") + ("-dirty" if dirty else "")


def harness_version() -> str:
    return git_version(Path(agent_mod.__file__).resolve().parent)


def runner_version() -> str:
    return git_version(RUNNER_DIR)


def example_id(dataset_name: str, case: Question) -> uuid.UUID:
    return uuid.uuid5(EXAMPLE_NAMESPACE, f"{dataset_name}:{case.id}:{case_hash(case)}")


def sync_dataset(client: Client, name: str, cases: list[Question], skills_sha: str) -> list[Example]:
    """Add any case version the dataset lacks; versions are never edited or deleted, so concurrent
    runs on different commits cannot change each other's examples."""
    dataset = (
        client.read_dataset(dataset_name=name)
        if client.has_dataset(dataset_name=name)
        else client.create_dataset(name, description="Ask TFY eval cases from tfy-ai-gateway-skills evals/evals.json")
    )
    existing = {example.id for example in client.list_examples(dataset_id=dataset.id)}
    # Baseline and candidate share most cases; each version is one example.
    cases = list({example_id(name, case): case for case in cases}.values())
    wanted = []
    for case in cases:
        eid = example_id(name, case)
        if eid not in existing:
            client.create_example(
                inputs={"case_id": case.id, "question": case.question},
                outputs={"expected": case.expected, "expectations": case.expectations},
                metadata={"case_id": case.id, "case_hash": case_hash(case), "tags": case.tags,
                          "first_seen_skills_sha": skills_sha},
                dataset_id=dataset.id,
                example_id=eid,
            )
        wanted.append(eid)
    examples = list(client.list_examples(dataset_id=dataset.id, example_ids=wanted))
    if len(examples) != len(cases):
        raise RuntimeError(f"LangSmith dataset {name} returned {len(examples)} examples for {len(cases)} cases")
    return examples


class Experiment:
    def __init__(self, settings: Settings, cases: list[Question], judge_model: str, model: str | None):
        self.settings = settings
        self.cases = {case.id: case for case in cases}
        self.judge_model = judge_model
        self.model = model
        self.aborted: str | None = None
        self.config: dict = {}
        self._local = threading.local()
        self._lock = threading.Lock()
        self._trials: dict[str, int] = defaultdict(int)
        # LangSmith gets redacted outputs; the judge grades what the agent really said.
        self._raw: dict[tuple[str, int], dict] = {}

    def agent_client(self) -> PinnedAskTfy:
        """One client per thread; httpx clients are not meant to be shared."""
        if not hasattr(self._local, "agent"):
            s = self.settings
            self._local.agent = PinnedAskTfy(s.host, s.tenant, s.token, s.skills_sha, s.timeout, model=self.model)
        return self._local.agent

    def judge_client(self) -> Any:
        if not hasattr(self._local, "judge"):
            s = self.settings
            self._local.judge = agent_mod.make_client(s.judge_base_url, s.judge_token, s.timeout)
        return self._local.judge

    def target(self, inputs: dict) -> dict:
        if self.aborted:
            raise RuntimeError(f"run aborted: {self.aborted}")
        s = self.settings
        case = self.cases[inputs["case_id"]]
        with self._lock:
            trial = self._trials[case.id]
            self._trials[case.id] += 1
        try:
            run = agent_mod.run_question_with_retries(
                self.agent_client(),
                AGENT,
                case.question,
                retries=s.retries,
                on_progress=self._note,
                question_id=case.id,
                trial=trial,
                # Writes really apply on devtest, so only cases that clean up after themselves may.
                on_approval="allow" if case.id in s.writes_allowed else "deny",
                clarification_reply=case.clarification_reply or agent_mod.DEFAULT_CLARIFICATION_REPLY,
                follow_up=case.clarification_reply,
                max_rounds=s.max_rounds,
                max_reconnects=s.max_reconnects,
            )
        except agent_mod.AbortRun as exc:
            self.aborted = str(exc)
            print(f"\nABORTING: {exc}", flush=True)
            raise
        broken = sandbox_failure(run)
        if broken:
            self.aborted = f"{case.id}: the agent sandbox did not start, so no skill was loaded: {broken}"
            print(f"\nABORTING: {self.aborted}", flush=True)
            raise agent_mod.AbortRun(self.aborted)
        unasked = unapproved_writes(run)
        key_reads = answer_key_reads(run)
        record = run.to_json() | {"unapproved_writes": unasked, "answer_key_reads": key_reads}
        self._record_answer(run, record)
        print(f"  {s.skills_sha[:7]} {case.id}#{trial} {run.status} {run.duration_s:.0f}s tools={len(run.tool_calls)}"
              + (f" ({run.failure}: {run.error})" if run.failure else "")
              + (f" UNAPPROVED WRITES {unasked}" if unasked else "")
              + (f" READ {ANSWER_KEY}" if key_reads else ""), flush=True)
        outputs = {
            "trial": trial,
            "answer": run.answer,
            "status": run.status,
            "failure": run.failure,
            "error": run.error,
            "session_id": run.session_id,
            "tool_calls": run.tool_calls,
            "sandbox_tool_calls": run.sandbox_tool_calls,
            "clarifications_asked": run.clarifications_asked,
            "secrets_requested": run.secrets_requested,
            "exchanges": run.exchanges,
            "interim_messages": run.interim_messages,
            "approvals": run.approvals_granted,
            "unapproved_writes": unasked,
            "answer_key_reads": key_reads,
            "duration_s": round(run.duration_s, 1),
            "cost_usd": run.metrics.get("total_cost_in_usd"),
        }
        with self._lock:
            self._raw[(case.id, trial)] = outputs
        return redaction.redact(outputs)

    def grade(self, run: Run, example: Example) -> dict:
        case = self.cases[example.inputs["case_id"]]
        uploaded = run.outputs or {}
        with self._lock:
            out = self._raw.get((case.id, uploaded.get("trial", -1)), uploaded)
        s = self.settings
        failure = out.get("failure") or ("infra:exception" if run.error else None)
        # Whatever interim text an infrastructure failure left behind is not an answer to grade,
        # and an agent failure is a fail whatever it said on the way.
        if failure in agent_mod.INFRA_FAILURES or (run.error and not out):
            grade = judge_mod.Grade(question_id=case.id, trial=out.get("trial", -1),
                                    error=f"{failure}: {out.get('error') or run.error}")
        elif failure in agent_mod.AGENT_FAILURES:
            grade = judge_mod.Grade(question_id=case.id, trial=out.get("trial", -1), verdict="incorrect",
                                    error=f"{failure}: {out.get('error')}")
        else:
            grade = judge_mod.grade_one(
                self.judge_client(),
                self.judge_model,
                question_id=case.id,
                trial=out.get("trial", -1),
                question=case.question,
                expected=case.expected,
                candidate=out.get("answer") or "",
                expectations=case.expectations,
                tool_calls=(out.get("tool_calls") or []) + [f"sandbox/{c}" for c in out.get("sandbox_tool_calls") or []]
                or None,
                exchanges=out.get("exchanges"),
                interim=out.get("interim_messages"),
                pass_threshold=s.pass_threshold,
                repeats=s.judge_repeats,
                numeric_tolerance=s.numeric_tolerance,
            )
        self._append("grades.jsonl", grade.to_json() | {"failure": failure})
        results = [
            {"key": "infra_failure", "score": int(grade.verdict == "ungraded" and failure is not None),
             "comment": failure},
            {"key": "agent_failure", "score": int(failure in agent_mod.AGENT_FAILURES), "comment": failure},
            {"key": "judge_error", "score": int(grade.verdict == "ungraded" and failure is None), "comment": grade.error},
        ]
        if grade.verdict != "ungraded":
            results += [
                {"key": "expectation_score", "score": grade.score, "comment": grade.summary},
                {"key": "correct", "score": int(grade.verdict == "correct"), "value": grade.verdict},
                {"key": "contradictions", "score": grade.contradictions},
                {"key": "high_risk_additions", "score": grade.high_risk_additions},
            ]
        return {"results": _redact_comments(results)}

    def behaviour(self, run: Run, example: Example) -> dict:
        out = run.outputs or {}
        denied = sum(1 for approval in out.get("approvals") or [] if approval.endswith(":deny"))
        results = [
            {"key": "secret_requested", "score": int(bool(out.get("secrets_requested")))},
            {"key": "clarification_asked", "score": int(bool(out.get("clarifications_asked")))},
            {"key": "writes_denied", "score": denied},
            {"key": "unapproved_writes", "score": len(out.get("unapproved_writes") or []),
             "comment": ", ".join(out.get("unapproved_writes") or []) or None},
            {"key": "answer_key_reads", "score": out.get("answer_key_reads") or 0},
            {"key": "tool_calls", "score": len(out.get("tool_calls") or [])},
            {"key": "duration_s", "score": out.get("duration_s")},
        ]
        if out.get("cost_usd") is not None:
            results.append({"key": "cost_usd", "score": out["cost_usd"]})
        return {"results": _redact_comments([r for r in results if r["score"] is not None])}

    def _note(self, message: str) -> None:
        print(f"      - {self.settings.skills_sha[:7]} {message}", flush=True)

    def _record_answer(self, run: agent_mod.AgentRun, record: dict) -> None:
        self._append("answers.jsonl", record)
        if run.transcript:
            transcripts = self.settings.run_dir / "transcripts"
            transcripts.mkdir(exist_ok=True)
            (transcripts / f"{run.question_id}-{run.trial}.json").write_text(
                json.dumps(run.transcript, indent=2, ensure_ascii=False)
            )

    def _append(self, name: str, record: dict) -> None:
        with self._lock, (self.settings.run_dir / name).open("a") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def run_experiment(settings: Settings, cases: list[Question]) -> Path:
    experiment = start_experiment(settings, cases)
    return execute(experiment, sync_dataset(Client(), settings.dataset_name, cases, settings.skills_sha))


def start_experiment(settings: Settings, cases: list[Question]) -> Experiment:
    """Everything that can fail before an agent turn costs anything: versions, run dir, pin probe, judge."""
    harness, runner = harness_version(), runner_version()
    dirty = [name for name, version in (("harness", harness), ("runner", runner)) if version.endswith("-dirty")]
    if dirty and not settings.allow_dirty:
        raise SystemExit(f"uncommitted changes in {' and '.join(dirty)}: a run must be reproducible from its "
                         "recorded commits (pass --allow-dirty for a throwaway run)")
    filled = [fill(case, settings.fixtures or {}) for case in cases]
    run_dir = settings.run_dir
    if run_dir.exists():
        raise SystemExit(f"{run_dir} already exists; pick another --run")
    run_dir.mkdir(parents=True)
    probe_client = PinnedAskTfy(settings.host, settings.tenant, settings.token, settings.skills_sha, settings.timeout)
    stamped = probe(probe_client)
    experiment = Experiment(settings, filled, judge_model="", model=stamped.get("modelIdentifier"))
    experiment.judge_model = judge_mod.pick_model(experiment.judge_client(), settings.judge_model)

    config = {
        "run_id": run_dir.name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": "ask-tfy",
        "agent": f"Ask TFY via {settings.host} ({settings.tenant})",
        "base_url": settings.host,
        "tenant": settings.tenant,
        "dataset": str(run_dir / "dataset.jsonl"),
        "questions": len(cases),
        "case_hashes": {case.id: case_hash(case) for case in cases},
        "all_case_hashes": settings.all_case_hashes or {case.id: case_hash(case) for case in cases},
        "skipped": settings.skipped,
        "regression_cases": sorted(case.id for case in cases if is_regression(case)),
        "repeats": settings.repeats,
        "max_rounds": settings.max_rounds,
        "on_approval": "deny, except writes-allowed.txt",
        "writes_allowed": sorted(settings.writes_allowed),
        "skills_ref": settings.skills_ref,
        "skills_sha": settings.skills_sha,
        "model": stamped.get("modelIdentifier"),
        "model_source": stamped.get("modelSource"),
        "harness": harness,
        "runner": runner,
        "judge_model": experiment.judge_model,
        "judge_version": judge_mod.JUDGE_VERSION,
        "judge_repeats": settings.judge_repeats,
        "pass_threshold": settings.pass_threshold,
        "numeric_tolerance": settings.numeric_tolerance,
    }
    dataset_mod.save(filled, run_dir / "dataset.jsonl")
    (run_dir / "config.json").write_text(json.dumps(config, indent=2))
    experiment.config = config
    print(
        f"Ask TFY on skills {settings.skills_sha[:12]} ({settings.skills_ref}), model {config['model']}: "
        f"{len(cases)} case(s) x {settings.repeats}, judge {experiment.judge_model}"
        + (f"; skipped {', '.join(sorted(settings.skipped))}" if settings.skipped else "")
    )
    return experiment


def execute(experiment: Experiment, examples: list[Example]) -> Path:
    settings, config, run_dir = experiment.settings, experiment.config, experiment.settings.run_dir
    cases = list(experiment.cases.values())
    client = Client()
    results = client.evaluate(
        experiment.target,
        data=examples,
        evaluators=[experiment.grade, experiment.behaviour],
        experiment_prefix=f"ask-tfy {settings.skills_sha[:8]}",
        description=f"skills {settings.skills_sha} ({settings.skills_ref}) on {settings.host}",
        metadata={key: value for key, value in config.items()
                  if key not in ("run_id", "dataset", "created_at", "case_hashes", "all_case_hashes")},
        max_concurrency=settings.concurrency,
        num_repetitions=settings.repeats,
    )
    config["experiment"] = results.experiment_name
    (run_dir / "config.json").write_text(json.dumps(config, indent=2))

    if experiment.aborted:
        # No summary.json: the gate refuses a run without one.
        (run_dir / "ABORTED").write_text(experiment.aborted + "\n")
        raise SystemExit(f"run aborted, results discarded: {experiment.aborted}")

    answers = _read_jsonl(run_dir / "answers.jsonl")
    grades = _read_jsonl(run_dir / "grades.jsonl")
    summary = report_mod.build_summary(cases, answers, grades, meta=config)
    summary["unapproved_writes"] = {
        f"{a['question_id']}#{a['trial']}": a["unapproved_writes"] for a in answers if a.get("unapproved_writes")
    }
    summary["answer_key_reads"] = {
        f"{a['question_id']}#{a['trial']}": a["answer_key_reads"] for a in answers if a.get("answer_key_reads")
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    (run_dir / "report.md").write_text(report_mod.to_markdown(summary))
    totals = summary["totals"]
    print(
        f"\nRuns fully correct {totals['runs_correct']}/{totals['graded_runs']}, mean score "
        f"{totals['mean_score']:.2f}, questions correct in every trial {totals['pass_rate'] * 100:.0f}% of "
        f"{totals['graded_questions']}, {totals['unanswered']} unanswered, cost ${totals['total_cost_usd']:.2f}\n"
        f"Experiment {results.experiment_name}\nRun        {run_dir}"
    )
    if summary["unapproved_writes"]:
        print(f"WARNING: writes that were never put to approval: {summary['unapproved_writes']}")
    if summary["answer_key_reads"]:
        print(f"WARNING: trials that touched {ANSWER_KEY}: {sorted(summary['answer_key_reads'])}")
    return run_dir


def _redact_comments(results: list[dict]) -> list[dict]:
    """Judge summaries and errors quote the raw answer, so they get the same redaction as outputs."""
    return [r | {"comment": redaction.redact_text(r["comment"])} if r.get("comment") else r for r in results]


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []
