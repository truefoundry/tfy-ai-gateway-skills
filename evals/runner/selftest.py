"""Offline checks for the runner: the sfy transport and pin check, case loading, the write check,
grading of failed trials, the gate, affected-case selection and fixture placeholders.

    cd evals && python -m runner.selftest
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import time
import types
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import httpx
from tfy_eval import agent as agent_mod

from . import asktfy
from .affected import affected
from .asktfy import AGENT, DeadlineStream, PinMismatch, PinnedAskTfy, SfyTransport, check_pinned, sfy_raw_path
from .cases import (
    PLACEHOLDER, case_from_eval, case_hash, conditional_critical_claims, fill, load_cases, load_fixtures,
    skip_unseeded, unavailable_fixtures,
)
from .experiment import (
    Experiment, Settings, answer_key_reads, example_id, is_write, sandbox_failure, unapproved_writes,
)
from .gate import GateError, compare, fisher_less, holm, sign_flip_p
from .seed_fixtures import TRACES

SHA = "0235a3f0cb8af8913e628b3eaddb0f449a88be43"
SESSIONS = "/api/svc/v1/ai-features/acme/sessions"
failures: list[str] = []


def check(name: str, condition: bool) -> None:
    print(f"{'ok  ' if condition else 'FAIL'} {name}")
    if not condition:
        failures.append(name)


def raises(error: type[BaseException], fn) -> bool:
    try:
        fn()
    except error:
        return True
    return False


# --- sfy path rewrite
check("create goes to sfy's own route", sfy_raw_path(b"/api/v1/sessions", SESSIONS) == SESSIONS.encode())
check(
    "turns keep their id, suffix and query",
    sfy_raw_path(b"/api/v1/sessions/ab%2Fc/turns?stream=true", SESSIONS) == f"{SESSIONS}/ab%2Fc/turns?stream=true".encode(),
)
check("other TrueForge routes are refused", raises(RuntimeError, lambda: sfy_raw_path(b"/api/v1/models", SESSIONS)))
check("a lookalike prefix is refused", raises(RuntimeError, lambda: sfy_raw_path(b"/api/v1/sessionsX", SESSIONS)))

# --- stream deadline
REQUEST = httpx.Request("GET", "https://example.test/api/v1/sessions/s/turns")
pings = httpx.ByteStream(b": ping\n\n")
check("a stream within its deadline passes through",
      list(DeadlineStream(pings, REQUEST, time.monotonic() + 60)) == [b": ping\n\n"])
check("a stream past its deadline raises a transport error the harness re-attaches on",
      raises(httpx.TransportError, lambda: list(DeadlineStream(pings, REQUEST, time.monotonic() - 1))))


def read_sse_through_sfy(content_type: str) -> list[bytes]:
    upstream = httpx.Response(200, headers={"content-type": content_type}, stream=httpx.ByteStream(b": ping\n\n"))
    with mock.patch.object(httpx.HTTPTransport, "handle_request", return_value=upstream), \
            mock.patch.object(asktfy, "STREAM_DEADLINE_S", -1.0):
        with httpx.Client(transport=SfyTransport("acme")) as client:
            with client.stream("GET", "https://example.test/api/v1/sessions/s/turns") as response:
                return list(response.iter_raw())


check("sfy event streams get the deadline", raises(httpx.ReadTimeout, lambda: read_sse_through_sfy("text/event-stream")))
check("plain responses do not", read_sse_through_sfy("application/json") == [b": ping\n\n"])

# --- pin check
check("matching ref passes", raises(PinMismatch, lambda: check_pinned({"skillsRef": SHA}, SHA)) is False)
check("sfy without the override stamps no ref", raises(PinMismatch, lambda: check_pinned({}, SHA)))
check("a different ref is refused", raises(PinMismatch, lambda: check_pinned({"skillsRef": "platform"}, SHA)))
check("the run's model passes", not raises(PinMismatch, lambda: check_pinned(
    {"skillsRef": SHA, "modelIdentifier": "m1"}, SHA, "m1")))
check("a different model is refused", raises(PinMismatch, lambda: check_pinned(
    {"skillsRef": SHA, "modelIdentifier": "m2"}, SHA, "m1")))
check("a pin mismatch aborts the harness run", issubclass(PinMismatch, agent_mod.AbortRun))


# --- the SDK through the transport, against a fake sfy
def session_body(metadata: dict) -> dict:
    return {
        "data": {
            "id": "sess-1",
            "agent": {"name": "ask-tfy"},
            "created_at": "2026-11-04T00:00:00Z",
            "updated_at": "2026-11-04T00:00:00Z",
            "metadata": metadata,
            "shared": False,
            "source": {"type": "api"},
        }
    }


def create_with(metadata: dict, model: str | None = None) -> tuple[list[httpx.Request], BaseException | None]:
    seen: list[httpx.Request] = []

    def fake_network(_transport: httpx.HTTPTransport, request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=session_body(metadata), request=request)

    with mock.patch.object(httpx.HTTPTransport, "handle_request", fake_network):
        client = PinnedAskTfy("https://cp.example/", "acme", "pat-1", SHA, timeout=10, model=model)
        try:
            client.sessions.create(agent=AGENT)
        except Exception as exc:  # noqa: BLE001 - the test inspects it
            return seen, exc
    return seen, None


seen, error = create_with({"skillsRef": SHA})
request = seen[0] if seen else None
check("SDK parses sfy's create response", error is None)
check("create is a POST to sfy's sessions route", request is not None and request.method == "POST"
      and str(request.url) == f"https://cp.example{SESSIONS}")
check("asks sfy for the commit", request is not None and request.headers.get("x-ask-tfy-skills-ref") == SHA)
check("authenticates with the PAT", request is not None and request.headers.get("authorization") == "Bearer pat-1")
_, error = create_with({"skillsRef": "platform"})
check("a session on another ref raises PinMismatch", isinstance(error, PinMismatch))
_, error = create_with({"skillsRef": SHA, "modelIdentifier": "other"}, model="m1")
check("a session on another model raises PinMismatch", isinstance(error, PinMismatch))

# --- cases
case = case_from_eval({"id": 74, "prompt": "Q?", "expected_output": "A.", "files": [], "expectations": ["c1"]})
check("old-format case maps to the harness format", case.id == "s74" and case.question == "Q?" and case.expected == "A."
      and case.expectations == [{"claim": "c1", "importance": "normal"}] and case.tags == [])
new = case_from_eval({
    "id": 5, "prompt": "Q?", "expected_output": "A.", "files": [],
    "expectations": [{"text": "names the cause", "critical": True}, "c2"],
    "tags": {"area": "traces", "kind": "diagnose"}, "clarification_reply": "workspace a2a",
})
check("critical expectations map to importance", new.expectations == [
    {"claim": "names the cause", "importance": "critical"}, {"claim": "c2", "importance": "normal"}])
check("tag objects become area:/kind: tags", new.tags == ["area:traces", "kind:diagnose"])
check("clarification reply is carried", new.clarification_reply == "workspace a2a")
edited = case_from_eval({"id": 5, "prompt": "Q?", "expected_output": "A.", "expectations": ["c2"]})
check("editing a case changes its hash", case_hash(new) != case_hash(edited))
check("an edited case is a new LangSmith example", example_id("d", new) != example_id("d", edited))
check("example ids are scoped to the dataset", example_id("d1", new) != example_id("d2", new))
gated = case_from_eval({"id": 6, "prompt": "Q?", "expected_output": "A.", "expectations": [
    {"text": "If the apply succeeds, links the policy", "critical": True}, "If denied, says so"]})
check("a critical claim written as a condition is flagged",
      conditional_critical_claims(gated) == ["If the apply succeeds, links the policy"])
check("a normal conditional claim is fine", conditional_critical_claims(new) == [])
dataset = json.loads((Path(__file__).resolve().parents[1] / "evals.json").read_text())["evals"]
check("no case in evals.json has a conditional critical claim",
      not [e["id"] for e in dataset if conditional_critical_claims(case_from_eval(e))])

# --- write check
def call(call_id: str, name: str, kind: str | None, arguments: dict | None = None) -> dict:
    return {"id": call_id, "name": name, "type": kind, "arguments": json.dumps(arguments or {})}


def agent_run(calls: list[dict], approved: list[str] = (), results: dict | None = None,
              sandbox: list[str] = (), earlier: list | None = None) -> agent_mod.AgentRun:
    transcript = [{"type": "message", "tool_calls": calls}] + [
        {"type": "tool.response", "tool_call_id": cid, "content": content} for cid, content in (results or {}).items()]
    return agent_mod.AgentRun(question_id="s1", trial=0, transcript=transcript,
                              approval_call_ids=list(approved), sandbox_tool_calls=list(sandbox),
                              earlier_attempts=earlier or [])


wrapped = {"server_name": "tfy-platform-mcp", "tool_name": "create_grants"}
check("platform writes are writes", is_write("tfy-platform-mcp/create_grants") and is_write("apply_manifest"))
check("reads are not writes", not is_write("tfy-platform-mcp/list_grants") and not is_write("validate_manifest"))
check("a write put to approval is fine", unapproved_writes(agent_run(
    [call("c1", "call_tool", "truefoundry-system", wrapped), call("c2", "list_users", "mcp")], approved=["c1"])) == [])
check("a write with no approval prompt is caught", unapproved_writes(agent_run(
    [call("c1", "apply_manifest", "mcp"), call("c2", "revoke_grant", "mcp")], approved=["c1"])) == ["revoke_grant"])
check("an approval for one write does not cover another", unapproved_writes(agent_run(
    [call("c1", "apply_manifest", "mcp"), call("c2", "apply_manifest", "mcp")], approved=["c1"])) == ["apply_manifest"])
check("spawning a subagent is not a write", unapproved_writes(agent_run(
    [call("c1", "create_sub_agent", "truefoundry-system")])) == [])
check("schema lookups are not writes", unapproved_writes(agent_run(
    [call("c1", "get_tool_info", "truefoundry-system", wrapped)])) == [])
check("a tool that does not exist ran nothing", unapproved_writes(agent_run(
    [call("c1", "call_tool", "truefoundry-system", wrapped)],
    results={"c1": "Tool create_grants not found in tool mapping"})) == [])
check("sandbox writes are always caught", unapproved_writes(agent_run(
    [], sandbox=["tfy-platform-mcp/list_users", "tfy-platform-mcp/apply_manifest"]))
      == ["sandbox/tfy-platform-mcp/apply_manifest"])
check("a write in a retried attempt is still caught", unapproved_writes(agent_run(
    [], earlier=[agent_run([call("c9", "delete_application", "mcp")])])) == ["delete_application"])
check("reading the eval cases is noticed", answer_key_reads(agent_run(
    [call("c1", "exec", "truefoundry-system", {"command": "cat /opt/tf/skills/x/evals/evals.json"})])) == 1)
check("a search that quotes the eval cases is a read", answer_key_reads(agent_run(
    [call("c1", "exec", "truefoundry-system", {"command": "grep -rn cost /opt/tf/skills"})],
    results={"c1": "/opt/tf/skills/x/evals/evals.json:344:  \"expected_output\": ..."})) == 1)
check("a listing that shows the file name is not", answer_key_reads(agent_run(
    [call("c1", "exec", "truefoundry-system", {"command": "find /opt/tf/skills"})],
    results={"c1": "/opt/tf/skills/x/SKILL.md\n/opt/tf/skills/x/evals/evals.json\n"})) == 0)
skill_read = [call("c1", "exec", "truefoundry-system", {"command": "cat /opt/tf/skills/x/SKILL.md"})]
check("a sandbox that never started is caught", (sandbox_failure(agent_run(skill_read, results={
    "c1": '{"error":[{"text":"Sandbox initialization failed: git -c failed (exit 128)"}]}'})) or "")
      .startswith("Sandbox initialization failed: git -c failed"))
check("a sandbox that started is not", sandbox_failure(agent_run(skill_read, results={"c1": "# Skill"})) is None)


# --- grading failed trials, without LangSmith
def settings(run_dir: Path) -> Settings:
    return Settings(host="h", tenant="t", token="x", judge_base_url="j", judge_token="x", judge_model="m",
                    skills_ref="r", skills_sha=SHA, dataset_name="d", run_dir=run_dir, repeats=1, concurrency=1,
                    judge_repeats=1, pass_threshold=0.7, numeric_tolerance=0.1, timeout=1, max_rounds=1, retries=0,
                    max_reconnects=0, writes_allowed=frozenset(), skipped={})


def graded(exp: Experiment, outputs: dict, error: str | None = None) -> tuple[dict, dict]:
    run = types.SimpleNamespace(outputs=outputs, error=error)
    example = types.SimpleNamespace(inputs={"case_id": "s74"})
    feedback = {r["key"]: r["score"] for r in exp.grade(run, example)["results"]}
    row = json.loads((exp.settings.run_dir / "grades.jsonl").read_text().splitlines()[-1])
    return feedback, row


with tempfile.TemporaryDirectory() as tmp:
    exp = Experiment(settings(Path(tmp)), [case], judge_model="m", model="m1")
    feedback, row = graded(exp, {"trial": 0, "answer": "", "failure": "agent:stalled"})
    check("an agent failure with no answer is a fail", row["verdict"] == "incorrect" and feedback["agent_failure"] == 1
          and feedback["infra_failure"] == 0)
    feedback, row = graded(exp, {"trial": 1, "answer": "", "failure": "infra:turn_error"})
    check("an infra failure with no answer is unmeasured", row["verdict"] == "ungraded" and feedback["infra_failure"] == 1)
    feedback, row = graded(exp, {"trial": 2, "answer": "partial", "failure": "infra:mcp_auth"})
    check("an MCP login pause is unmeasured even with an answer", row["verdict"] == "ungraded")
    feedback, row = graded(exp, {"trial": 3, "answer": "Let me query the traces.", "failure": "infra:poll_timeout"})
    check("an infra failure's interim text is not graded", row["verdict"] == "ungraded")
    feedback, row = graded(exp, {"trial": 4, "answer": "Here is a fine answer.", "failure": "agent:step_limit"})
    check("an agent failure is a fail even with an answer", row["verdict"] == "incorrect")
    feedback, row = graded(exp, {}, error="boom")
    check("a crashed target is unmeasured", row["verdict"] == "ungraded" and feedback["infra_failure"] == 1)
    comments = exp.grade(types.SimpleNamespace(outputs={"trial": 5, "answer": "", "failure": "infra:turn_error",
                                                        "error": "user alice@acme.com hit a 500"}, error=None),
                         types.SimpleNamespace(inputs={"case_id": "s74"}))["results"]
    check("feedback comments are redacted", not any("alice@acme.com" in str(r.get("comment")) for r in comments))

# --- gate statistics
check("3/3 -> 0/3 is significant at 0.05", abs(fisher_less(3, 0, 0, 3) - 0.05) < 1e-12)
check("2/2 -> 0/2 cannot be significant", fisher_less(2, 0, 0, 2) > 0.1)
check("no change is not significant", fisher_less(3, 0, 3, 0) == 1.0)
check("uniform drops are significant overall", sign_flip_p([-1.0] * 6) < 0.05)
check("mixed changes are not", sign_flip_p([-1.0, 1.0, -0.5, 0.5]) > 0.3)
check("no change gives p = 1", sign_flip_p([0.0, 0.0]) == 1.0)
check("Holm stops at the first test over its threshold", holm({"a": 0.001, "b": 0.03, "c": 0.04}, 0.05) == {"a"})
check("Holm keeps a lone significant test", holm({"a": 0.05}, 0.05) == {"a"})
check("Holm's threshold relaxes as it steps down", holm({"a": 0.03, "b": 0.001}, 0.05) == {"b", "a"})


# --- gate
def write_run(root: Path, name: str, verdicts: dict[str, list[str]], repeats: int = 3, hashes: dict | None = None,
              complete: bool = True, answers: list[dict] | None = None, **config) -> Path:
    run = root / name
    run.mkdir()
    base_config = {"skills_sha": name, "repeats": repeats, "judge_model": "j", "judge_version": "v", "model": "m",
                   "harness": "h", "runner": "r", "tenant": "t", "pass_threshold": 0.7, "numeric_tolerance": 0.1,
                   "writes_allowed": [], "case_hashes": hashes or {cid: f"h-{cid}" for cid in verdicts}}
    (run / "config.json").write_text(json.dumps(base_config | config))
    (run / "grades.jsonl").write_text("".join(
        json.dumps({"question_id": cid, "trial": i, "verdict": v}) + "\n"
        for cid, vs in verdicts.items() for i, v in enumerate(vs)
    ))
    (run / "answers.jsonl").write_text("".join(json.dumps(a) + "\n" for a in answers or []))
    if complete:
        (run / "summary.json").write_text("{}")
    return run


P, F, U = "correct", "incorrect", "ungraded"
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    cases_all = {f"s{i}": [P, P, P] for i in range(1, 9)}
    base = write_run(root, "base", cases_all | {"s3": [F, F, F]})
    cand = write_run(root, "cand", cases_all | {"s1": [F, F, F], "s2": [P, F, F], "s3": [P, P, P]})
    result = compare([base], [cand])
    check("among 8 cases, one 3/3 -> 0/3 is not significant after correction", result.regressions == []
          and sorted(r[0] for r in result.watch) == ["s1", "s2"])
    single = compare([write_run(root, "b1", {"s1": [P, P, P]})], [write_run(root, "c1", {"s1": [F, F, F]})])
    check("a lone 3/3 -> 0/3 case is a regression and fails the gate",
          [r[0] for r in single.regressions] == ["s1"] and not single.passed)
    check("0/3 -> 3/3 is not called fixed among 8 cases either", result.fixed == [])

    same = write_run(root, "same", cases_all | {"s3": [F, F, F]})
    check("an identical run passes", compare([base], [same]).passed)

    back = compare([base], [write_run(root, "back", cases_all | {"s3": [F, F, F], "s4": [P, F, F]},
                                      regression_cases=["s4"])])
    check("a regression case failed 2 of 3 fails the gate on its own", not back.passed
          and [cid for cid, _ in back.issues_back] == ["s4"] and back.regressions == [])
    check("a regression case failed 1 of 3 does not", compare([base], [write_run(
        root, "once", cases_all | {"s3": [F, F, F], "s4": [P, P, F]}, regression_cases=["s4"])]).passed)

    partial = write_run(root, "partial", {"s1": [P, P, P]}, hashes={"s1": "h-s1"})
    removed = compare([base], [partial])
    check("cases missing from the candidate fail the gate", not removed.passed and "s2" in removed.removed)
    check("an accepted removal passes", compare(
        [base], [partial], accept=frozenset(f"s{i}" for i in range(2, 9))).passed)

    short = write_run(root, "short", {"s1": [P]}, hashes={f"s{i}": f"h-s{i}" for i in range(1, 9)})
    check("missing trials count as unmeasured", compare([base], [short]).unmeasured["candidate"] > 0.9)

    check("an incomplete run is refused", raises(GateError, lambda: compare(
        [base], [write_run(root, "crashed", cases_all, complete=False)])))
    aborted = write_run(root, "aborted", cases_all)
    (aborted / "ABORTED").write_text("wrong commit")
    check("an aborted run is refused", raises(GateError, lambda: compare([base], [aborted])))

    changed = write_run(root, "changed", cases_all | {"s3": [P, P, P]}, hashes={
        **{f"s{i}": f"h-s{i}" for i in range(1, 9)}, "s3": "edited"})
    changed_result = compare([base], [changed])
    check("an edited case is not compared and fails the gate", changed_result.changed == ["s3"]
          and not changed_result.passed and not changed_result.fixed)

    for key, value in (("model", "other"), ("judge_version", "v2"), ("harness", "h2"), ("runner", "r2")):
        drifted = compare([base], [write_run(root, f"drift-{key}", cases_all, **{key: value})])
        check(f"a different {key} is not comparable", key in drifted.drift and not drifted.passed)

    unsafe = write_run(root, "unsafe", cases_all | {"s3": [F, F, F]}, answers=[
        {"question_id": "s4", "trial": 0, "unapproved_writes": ["tfy-platform-mcp/revoke_grant"]}])
    check("an unapproved write fails the gate", not compare([base], [unsafe]).passed)
    peeked = write_run(root, "peeked", cases_all | {"s3": [F, F, F]}, answers=[
        {"question_id": "s4", "trial": 0, "answer_key_reads": 1}])
    check("reading the eval cases fails the gate", not compare([base], [peeked]).passed)
    check("so does a baseline that read them", not compare([peeked], [same]).passed)
    dodged = write_run(root, "dodged", cases_all | {"s3": [F, F, F], "s5": [P, U, U]})
    lost = compare([base], [dodged])
    check("a case mostly unmeasured on the candidate only fails the gate",
          [c[0] for c in lost.lost] == ["s5"] and not lost.passed)

    worse = write_run(root, "worse", {f"s{i}": [P, F, F] for i in range(1, 9)} | {"s3": [F, F, F]})
    overall = compare([base], [worse])
    check("a broad small drop fails on the overall test", overall.aggregate_regression and not overall.passed
          and not overall.regressions)

    again = write_run(root, "again", cases_all | {"s1": [F, F, F], "s3": [F, F, F]}, skills_sha="cand")
    pooled = compare([base], [cand, again])
    check("pooled runs add their trials", next(r for r in pooled.watch if r[0] == "s1")[2].measured == 6)
    check("runs on different commits cannot be pooled", raises(GateError, lambda: compare([base], [cand, same])))

    every_case = {f"s{i}": f"h-s{i}" for i in range(1, 9)}
    subset = write_run(root, "subset", {"s1": [P, P, P], "s3": [P, P, P]}, all_case_hashes=every_case)
    subset_result = compare([base], [subset])
    check("a subset run compares only its cases and does not remove the rest",
          subset_result.passed and subset_result.aggregate_cases == 2 and len(subset_result.not_run) == 6)
    skipped_edit = write_run(root, "skipped-edit", {"s1": [P, P, P]}, all_case_hashes=every_case | {"s4": "edited"})
    check("a subset run that skipped an edited case is refused",
          raises(GateError, lambda: compare([base], [skipped_edit])))
    skipped_new = write_run(root, "skipped-new", {"s1": [P, P, P]}, all_case_hashes=every_case | {"s9": "h-s9"})
    check("so is one that skipped a new case", raises(GateError, lambda: compare([base], [skipped_new])))
    base_subset = write_run(root, "base-subset", {"s1": [P, P, P]}, all_case_hashes=every_case)
    check("two subset runs of the same case compare it alone",
          compare([base_subset], [subset]).aggregate_cases == 1)


# --- affected cases
def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


def commit(repo: Path, files: dict[str, str], message: str) -> str:
    for name, text in files.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(text)
    git(repo, "add", "-A")
    git(repo, "-c", "user.email=e@example.com", "-c", "user.name=e", "commit", "-qm", message)
    return git(repo, "rev-parse", "HEAD")


def evals(*prompts: str) -> str:
    return json.dumps({"evals": [{"id": i, "prompt": p, "expected_output": "x", "expectations": ["x"]}
                                 for i, p in enumerate(prompts, 1)]})


def baseline_run(root: Path, sha: str, repo: Path, reads: dict[str, str]) -> Path:
    run = root / f"nightly-{sha[:7]}"
    (run / "transcripts").mkdir(parents=True)
    cases, _ = load_cases(repo, sha)
    (run / "config.json").write_text(json.dumps({"skills_sha": sha, "case_hashes": {c.id: case_hash(c) for c in cases}}))
    for case_id, command in reads.items():
        (run / "transcripts" / f"{case_id}-0.json").write_text(json.dumps([
            {"tool_calls": [{"name": "exec", "arguments": {"command": command}}]},
            {"type": "tool.response", "content": "SKILL.md names metrics.md, users.md and models.md"},
        ]))
    return run


with tempfile.TemporaryDirectory() as tmp:
    root, repo = Path(tmp), Path(tmp) / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "platform")
    files = {"skills/SKILL.md": "s", "skills/ai-gateway/references/metrics.md": "m",
             "skills/ai-gateway/references/users.md": "u", "evals/evals.json": evals("cost?", "users?", "hi")}
    base_sha = commit(repo, files, "base")
    nightly = baseline_run(root, base_sha, repo, {
        "s1": "cat /opt/tf/skills/x/ai-gateway/references/metrics.md", "s2": "cat references/users.md", "s3": "ls"})

    git(repo, "checkout", "-q", "-b", "pr")
    metrics_sha = commit(repo, {"skills/ai-gateway/references/metrics.md": "m2"}, "metrics")
    picked = affected(repo, nightly, metrics_sha)
    check("a reference change runs the cases whose trials read it, not those that only saw its name",
          picked.mode == "cases" and picked.cases == ["s1"])
    case_sha = commit(repo, {"evals/evals.json": evals("cost?", "users?", "hello")}, "case")
    check("an edited case is run too", affected(repo, nightly, case_sha).cases == ["s1", "s3"])
    check("SKILL.md runs every case", affected(repo, nightly, commit(repo, {"skills/SKILL.md": "s2"}, "skill")).mode == "all")
    check("a runner change needs a full A/B", affected(repo, nightly, commit(
        repo, {"evals/runner/gate.py": "g"}, "runner")).mode == "ab")

    git(repo, "checkout", "-q", "platform")
    moved_sha = commit(repo, {"skills/ai-gateway/references/users.md": "u2"}, "platform moved on")
    newer = baseline_run(root, moved_sha, repo, {"s1": "cat metrics.md"})
    check("a branch missing platform's skill changes is stale", affected(repo, newer, metrics_sha).mode == "stale")
    git(repo, "checkout", "-q", "-b", "docs", base_sha)
    check("a change outside skills and cases runs nothing",
          affected(repo, nightly, commit(repo, {"README.md": "r"}, "docs")).mode == "none")

# --- fixture placeholders
template = case_from_eval({"id": 9, "prompt": "Why did trace {{trace.x.id}} fail?", "expected_output": "at {{trace.x.time}}",
                           "expectations": ["covers {{ trace.x.time }}"]})
filled = fill(template, {"trace.x.id": "01ab", "trace.x.time": "2026-11-05 07:16"})
check("placeholders are filled in the question, expected answer and checklist",
      (filled.question, filled.expected, filled.expectations[0]["claim"])
      == ("Why did trace 01ab fail?", "at 2026-11-05 07:16", "covers 2026-11-05 07:16"))
check("a case missing a fixture value is refused", raises(SystemExit, lambda: fill(template, {"trace.x.id": "01ab"})))
check("a case without placeholders is unchanged", fill(case_from_eval(
    {"id": 1, "prompt": "hi", "expected_output": "x"}), {}).question == "hi")
with tempfile.TemporaryDirectory() as tmp:
    path = Path(tmp) / "fixtures.json"
    path.write_text(json.dumps({"seeded_at": "2026-01-01T00:00:00+00:00", "values": {"trace.x.id": "old"}}))
    check("fixtures old enough to have expired are ignored", load_fixtures(path) == {})
    path.write_text(json.dumps({"seeded_at": datetime.now(timezone.utc).isoformat(), "values": {"trace.x.id": "new"}}))
    check("fresh fixtures are read", load_fixtures(path) == {"trace.x.id": "new"})
    check("no fixtures file means no values", load_fixtures(Path(tmp) / "none.json") == {})
    path.write_text(json.dumps({"seeded_at": datetime.now(timezone.utc).isoformat(), "values": {"trace.x.id": "1"},
                                "unavailable": {"trace.y": "not queryable"}}))
    check("unavailable fixtures are read", unavailable_fixtures(path) == {"trace.y": "not queryable"})
    on_y = case_from_eval({"id": 65, "prompt": "Why did {{trace.y.id}} fail?", "expected_output": "x"})
    on_x = case_from_eval({"id": 66, "prompt": "Why did {{trace.x.id}} fail?", "expected_output": "x"})
    kept, unseeded = skip_unseeded([on_y, on_x], unavailable_fixtures(path))
    check("a case naming an unseeded trace is skipped, with why",
          [c.id for c in kept] == ["s66"] and "trace.y" in unseeded["s65"] and "not queryable" in unseeded["s65"])
seeded = {f"trace.{trace.name}.{key}" for trace in TRACES for key in ("id", "time", "epoch_ms", "sender", "error")}
used = set(PLACEHOLDER.findall((Path(__file__).resolve().parents[1] / "evals.json").read_text()))
check("every placeholder in evals.json is a value seed_fixtures writes", used and used <= seeded)

print(f"\n{len(failures)} failure(s)" if failures else "\nall checks passed")
raise SystemExit(1 if failures else 0)
