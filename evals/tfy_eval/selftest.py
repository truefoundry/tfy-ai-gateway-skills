#!/usr/bin/env python3
"""Offline checks for the parts that do not need a TrueForge server.

Covers dataset parsing, judge-output parsing, the deterministic scoring rules,
and report rendering. Run after touching any of them:

    python selftest.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from tfy_eval import agent as agent_mod
from tfy_eval import dataset as dataset_mod
from tfy_eval import judge, report

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        failures.append(name)


print("dataset")
questions = dataset_mod.load(Path(__file__).parent / "datasets" / "example.jsonl")
check("example dataset loads 7 questions", len(questions) == 7, f"got {len(questions)}")
check("ids are unique", len({q.id for q in questions}) == len(questions))
check("comment lines are skipped", all(not q.id.startswith("//") for q in questions))
check("every question has ground truth", all(q.expected.strip() for q in questions))
check("every question is tagged", all(q.tags for q in questions))
check("every question has a checklist", all(q.expectations for q in questions))
check(
    "no question repeats a claim",
    all(len({c["claim"] for c in q.expectations}) == len(q.expectations) for q in questions),
)
check("a baseline answer is shipped for the judge sanity check", any(q.baseline for q in questions))
# A checklist that demands a write and also forbids it cannot be satisfied, and the
# contradiction gate would then mark a correct refusal `incorrect`.
for q in questions:
    claims = " ".join(c["claim"].lower() for c in q.expectations)
    check(
        f"{q.id} does not both require and forbid apply_manifest",
        not ("does not call apply_manifest" in claims and "calls apply_manifest" in claims),
    )

print("\njudge output parsing")
check(
    "bare json",
    judge._extract_json('{"claims": [], "summary": "x"}')["summary"] == "x",
)
check(
    "fenced json",
    judge._extract_json('Here you go:\n```json\n{"claims": [], "summary": "y"}\n```\n')["summary"] == "y",
)
check(
    "json with trailing prose",
    judge._extract_json('{"claims": [], "summary": "z"}\n\nHope that helps!')["summary"] == "z",
)
check(
    "a lone claim object after prose is not taken for the verdict",
    judge._extract_json(
        'Verdict:\n{"claims": [{"claim": "a", "verdict": "supported", "evidence": "WHERE x IN (}"}], "summary": "s"}'
    )["claims"][0]["verdict"] == "supported",
)
try:
    judge._extract_json('{"claim": "a", "verdict": "supported"}')
    check("an object without claims raises, so the judge retries", False)
except ValueError:
    check("an object without claims raises, so the judge retries", True)
check(
    "nested braces",
    judge._extract_json('{"claims": [{"claim": "a"}], "summary": "n"}')["claims"][0]["claim"] == "a",
)
try:
    judge._extract_json("no json at all")
    check("unparseable raises", False)
except ValueError:
    check("unparseable raises", True)

print("\nscoring")
all_supported = [{"claim": "a", "verdict": "supported", "importance": "normal"}] * 3
score, counts = judge.score_claims(list(all_supported), 0)
check("all supported scores 1.0", score == 1.0, f"got {score}")
check("counts tally", counts["supported"] == 3)

score, _ = judge.score_claims(
    [
        {"claim": "a", "verdict": "supported", "importance": "normal"},
        {"claim": "b", "verdict": "missing", "importance": "normal"},
    ],
    0,
)
check("half missing scores 0.5", score == 0.5, f"got {score}")

# A wrong critical claim must hurt more than a wrong peripheral one.
critical_wrong, _ = judge.score_claims(
    [
        {"claim": "crux", "verdict": "contradicted", "importance": "critical"},
        {"claim": "detail", "verdict": "supported", "importance": "normal"},
    ],
    0,
)
normal_wrong, _ = judge.score_claims(
    [
        {"claim": "crux", "verdict": "supported", "importance": "critical"},
        {"claim": "detail", "verdict": "contradicted", "importance": "normal"},
    ],
    0,
)
check("critical claims weigh double", critical_wrong < normal_wrong, f"{critical_wrong} vs {normal_wrong}")

penalised, _ = judge.score_claims(list(all_supported), 2)
check("high-risk additions penalised", penalised == 0.8, f"got {penalised}")

score, counts = judge.score_claims([{"claim": "a", "verdict": "nonsense"}], 0)
check("unknown verdict treated as missing", counts["missing"] == 1 and score == 0.0)
check("no claims does not divide by zero", judge.score_claims([], 0)[0] == 0.0)

print("\nverdicts")
check("contradiction forces incorrect", judge.decide_verdict(0.95, 1, 0.7) == "incorrect")
check("above threshold is correct", judge.decide_verdict(0.7, 0, 0.7) == "correct")
check("mid is partial", judge.decide_verdict(0.5, 0, 0.7) == "partially_correct")
check("low is incorrect", judge.decide_verdict(0.1, 0, 0.7) == "incorrect")

print("\nreport")
sample = questions[:3]
answers = [
    {"question_id": "q1", "trial": 0, "answer": "a", "status": "done", "duration_s": 4.0,
     "metrics": {"total_cost_in_usd": 0.01, "total_tokens": 100}, "clarifications_asked": []},
    {"question_id": "q2", "trial": 0, "answer": "b", "status": "done", "duration_s": 6.0,
     "metrics": {"total_cost_in_usd": 0.02, "total_tokens": 200}, "clarifications_asked": ["which cluster?"]},
    {"question_id": "q3", "trial": 0, "answer": "c", "status": "error", "error": "boom",
     "duration_s": 1.0, "metrics": {}, "clarifications_asked": []},
]
grades = [
    {"question_id": "q1", "trial": 0, "score": 1.0, "verdict": "correct", "contradictions": 0,
     "high_risk_additions": 0, "counts": {"supported": 4, "partial": 0, "missing": 0, "contradicted": 0},
     "claims": [], "unsupported_additions": [], "summary": "spot on"},
    {"question_id": "q2", "trial": 0, "score": 0.4, "verdict": "incorrect", "contradictions": 1,
     "high_risk_additions": 1, "counts": {"supported": 1, "partial": 1, "missing": 1, "contradicted": 1},
     "claims": [{"claim": "member role is editable", "verdict": "contradicted",
                 "importance": "critical", "evidence": "said it was fixed | with a pipe"}],
     "unsupported_additions": [{"statement": "invented env var", "risk": "high", "note": "no such var"}],
     "summary": "inverted the key fact"},
    {"question_id": "q3", "trial": 0, "score": 0.0, "verdict": "ungraded", "contradictions": 0,
     "high_risk_additions": 0, "counts": {}, "claims": [], "unsupported_additions": [],
     "summary": "", "error": "candidate answer was empty"},
]
summary = report.build_summary(sample, answers, grades, meta={"agent": "demo-agent", "repeats": 1})
totals = summary["totals"]
check("ungraded excluded from pass rate", totals["graded_questions"] == 2, f"got {totals['graded_questions']}")
check("pass rate is 1/2", abs(totals["pass_rate"] - 0.5) < 1e-9, f"got {totals['pass_rate']}")
check("contradiction rate is 1/2", abs(totals["contradiction_rate"] - 0.5) < 1e-9)
check("clarification rate is 1/3", abs(totals["clarification_rate"] - 1 / 3) < 1e-9)
check("cost summed", abs(totals["total_cost_usd"] - 0.03) < 1e-9)
check("run statuses counted", totals["run_statuses"].get("error") == 1)
check("tag breakdown present", bool(summary["by_tag"]))

check("unanswered counted separately", totals["unanswered"] == 1, f"got {totals['unanswered']}")
check("completion rate is 2/3", abs(totals["completion_rate"] - 2 / 3) < 1e-9)

# An empty answer must not be scored as a wrong answer: it means the run failed
# before the agent said anything, which is an infra problem, not an accuracy one.
# Passing None as the client proves no model call is made on this path.
empty_grade = judge.grade_one(
    None,
    "irrelevant-model",
    question_id="qx",
    trial=0,
    question="q",
    expected="e",
    candidate="   ",
)
check("empty candidate is ungraded, not incorrect", empty_grade.verdict == "ungraded",
      f"got {empty_grade.verdict}")
check("empty candidate scores 0", empty_grade.score == 0.0)
check("empty candidate records why", "did not produce" in (empty_grade.error or ""))

markdown = report.to_markdown(summary)
check("markdown renders", "# Agent eval report" in markdown)
check("never-answered section present", "## Never answered" in markdown)
check("pass rate scoped to answered", "*answered*" in markdown)
check(
    "unanswered row shows no score",
    any(line.startswith("| q3 |") and "no answer" in line for line in markdown.splitlines()),
)
check(
    "unanswered excluded from what-went-wrong",
    "### q3 -" not in markdown,
)
check("failures section present", "## What went wrong" in markdown)
check("contradiction highlighted", "**contradicted**" in markdown)
check("pipe escaped in table cell", "\\| with a pipe" in markdown)
check("no raw newlines inside table rows", all(
    line.count("|") >= 2 for line in markdown.splitlines() if line.startswith("| q")
))

# Worst-trial selection across repeats: an agent that is sometimes confidently
# wrong must not be reported as correct.
flaky_grades = [
    {"question_id": "q1", "trial": 0, "score": 1.0, "verdict": "correct", "contradictions": 0,
     "high_risk_additions": 0, "counts": {}, "claims": [], "unsupported_additions": [], "summary": ""},
    {"question_id": "q1", "trial": 1, "score": 0.2, "verdict": "incorrect", "contradictions": 1,
     "high_risk_additions": 0, "counts": {}, "claims": [], "unsupported_additions": [], "summary": ""},
]
flaky_answers = [
    {"question_id": "q1", "trial": t, "answer": "x", "status": "done", "duration_s": 1.0,
     "metrics": {}, "clarifications_asked": []} for t in (0, 1)
]
flaky = report.build_summary(questions[:1], flaky_answers, flaky_grades)
q1 = flaky["questions"][0]
check("worst verdict wins across trials", q1["verdict"] == "incorrect", f"got {q1['verdict']}")
check("score spread surfaced", abs(q1["score_spread"] - 0.8) < 1e-9, f"got {q1['score_spread']}")
check("mean score across trials", abs(q1["score"] - 0.6) < 1e-9, f"got {q1['score']}")
check("instability flagged in markdown", "unstable" in report.to_markdown(flaky))

# --- hand-written checklists -------------------------------------------------
# A dataset can supply the claims itself. The judge then grades against that list
# and nothing else, so the score denominator is fixed run to run.

mixed = dataset_mod.normalize_expectations(["plain string claim", {"claim": "c2", "importance": "critical"}])
check("expectation strings default to normal", mixed[0] == {"claim": "plain string claim", "importance": "normal"})
check("expectation objects keep importance", mixed[1]["importance"] == "critical")
check("empty expectations normalise to []", dataset_mod.normalize_expectations(None) == [])
for bad, label in (
    ([{"claim": "", "importance": "normal"}], "blank claim"),
    ([{"claim": "c", "importance": "vital"}], "bad importance"),
    ([123], "wrong type"),
    ("not a list", "not a list"),
):
    try:
        dataset_mod.normalize_expectations(bad)
        check(f"rejects {label}", False, "no error raised")
    except ValueError:
        check(f"rejects {label}", True)

checklist = [
    {"claim": "Filters IsFailure = true", "importance": "critical"},
    {"claim": "Groups by ErrorType", "importance": "normal"},
    {"claim": "Includes LIMIT 20", "importance": "normal"},
]
# Reordered, reworded, one dropped and one invented - the shapes a model actually
# returns when told to echo a checklist back.
judge_returned = [
    {"claim": "groups by the ErrorType column", "verdict": "supported", "evidence": "GROUP BY"},
    {"claim": "filters on IsFailure being true", "verdict": "contradicted", "evidence": "used status code"},
    {"claim": "a claim nobody asked for", "verdict": "supported", "evidence": "-"},
]
aligned = judge.align_claims(checklist, judge_returned)
check("aligned length matches the checklist", len(aligned) == len(checklist), f"got {len(aligned)}")
check("aligned claims keep dataset wording", [c["claim"] for c in aligned] == [c["claim"] for c in checklist])
check("aligned claims keep dataset importance", aligned[0]["importance"] == "critical")
check("reworded claim still matches", aligned[0]["verdict"] == "contradicted", f"got {aligned[0]['verdict']}")
check("out-of-order claim matches", aligned[1]["verdict"] == "supported", f"got {aligned[1]['verdict']}")
check("unruled claim counts as missing", aligned[2]["verdict"] == "missing", f"got {aligned[2]['verdict']}")
check("unruled claim says why", "did not rule" in aligned[2]["evidence"])
by_number = judge.align_claims(checklist, [
    {"n": 3, "claim": "caps output", "verdict": "supported", "evidence": "LIMIT 20"},
    {"n": 1, "claim": "boolean column check", "verdict": "partial", "evidence": "-"},
])
check("the echoed number aligns a paraphrase overlap misses",
      [c["verdict"] for c in by_number] == ["partial", "missing", "supported"])
check("critical claims are matched case-insensitively",
      judge.decide_verdict(1.0, 0, 0.7, [{"importance": "Critical", "verdict": "Missing"}]) == "incorrect")
check("invented claim is dropped", all("nobody asked" not in c["claim"] for c in aligned))

no_tol = judge.JUDGE_INSTRUCTIONS_FIXED.replace("{tolerance}", judge._tolerance_rule(None))
with_tol = judge.JUDGE_INSTRUCTIONS_FIXED.replace("{tolerance}", judge._tolerance_rule(0.10))
check("tolerance placeholder is substituted", "{tolerance}" not in with_tol)
check(
    "tolerance band is rendered",
    "within 10%" in with_tol.lower() and "within 25%" in with_tol.lower(),
)
check("zero tolerance demands exact match", "no tolerance band" in no_tol)
check(
    "tolerance cannot excuse a missing or misattributed row",
    "never excuses" in with_tol and "wrong user" in with_tol,
)
check(
    "judge JSON schema survives substitution",
    '"verdict": "supported|partial|missing|contradicted|not_applicable"' in with_tol,
)

conditional = [
    {"claim": "If register_user returns 409, explains it", "importance": "normal"},
    {"claim": "Uses register_user", "importance": "normal"},
    {"claim": "After the denied apply, does not retry", "importance": "normal"},
    {"claim": "If several apps match, asks which one", "importance": "critical"},
]
ruled = judge.align_claims(conditional, [
    {"n": 1, "verdict": "not_applicable", "evidence": "the call was denied"},
    {"n": 2, "verdict": "not_applicable", "evidence": "-"},
    {"n": 3, "verdict": "supported", "evidence": "-"},
    {"n": 4, "verdict": "not_applicable", "evidence": "-"},
])
check("a conditional claim can be not applicable", ruled[0]["verdict"] == "not_applicable")
check("an unconditional claim cannot", ruled[1]["verdict"] == "missing" and "no condition" in ruled[1]["evidence"])
check("a critical claim cannot", ruled[3]["verdict"] == "missing" and "critical" in ruled[3]["evidence"])
score, counts = judge.score_claims([ruled[0], ruled[2]], 0)
check("not applicable claims are left out of the score", score == 1.0 and counts["not_applicable"] == 1)
check("all claims not applicable is not a fail", judge.score_claims([dict(ruled[0])], 0)[0] == 1.0)
check("no claims still scores zero", judge.score_claims([], 0)[0] == 0.0)

with_replies = judge.build_prompt(
    question="q", expected="e", candidate="a",
    exchanges=[{"asked": "Which RPS target?", "reply": "10 per replica", "via": "ask_user_question"}],
)
check("the judge sees what the user replied", "USER REPLIES" in with_replies and "Replied: 10 per replica" in with_replies)
check("no replies, no section", "USER REPLIES" not in judge.build_prompt(question="q", expected="e", candidate="a"))
for template in (judge.JUDGE_INSTRUCTIONS, judge.JUDGE_INSTRUCTIONS_FIXED):
    check(
        "both judge prompts carry the tolerance slot",
        "{tolerance}" in template,
    )

prompt = judge.build_prompt(
    question="q", expected="e", candidate="a",
    expectations=checklist,
    tool_calls=["get_me", "validate_manifest", "get_me"],
)
check("prompt carries the checklist", "REQUIRED CLAIMS" in prompt and "Filters IsFailure = true" in prompt)
check("prompt marks critical claims", "[critical]" in prompt)
check("prompt carries observed tool calls", "OBSERVED TOOL CALLS" in prompt and "validate_manifest" in prompt)
check("repeated tool calls folded with a count", prompt.count("- get_me") == 1 and "(called 2 times)" in prompt)
bare = judge.build_prompt(question="q", expected="e", candidate="a")
check("no checklist section without expectations", "REQUIRED CLAIMS" not in bare)
check("no tool section without tool calls", "OBSERVED TOOL CALLS" not in bare)

# --- tool-call unwrapping ----------------------------------------------------
# An agent that reaches its MCP tools through a generic wrapper would otherwise
# record every call as `call_tool`, and every process claim would grade `missing`.

check(
    "plain tool name passes through",
    agent_mod._effective_tool_names("get_me", "") == ["get_me"],
)
check(
    "wrapped MCP call is unwrapped to the real tool",
    agent_mod._effective_tool_names(
        "call_tool", '{"mcp_server": "gateway", "tool_name": "apply_manifest"}'
    )
    == ["gateway/apply_manifest"],
)
check(
    "wrapped call without a server still names the tool",
    agent_mod._effective_tool_names("call_tool", '{"tool_name": "validate_manifest"}')
    == ["validate_manifest"],
)
check(
    "schema lookups stay distinguishable from invocations",
    "schema lookup" in agent_mod._effective_tool_names(
        "get_tool_info", '{"tool_name": "apply_manifest"}'
    )[0],
)
check(
    "exec keeps the command so file reads stay checkable",
    agent_mod._effective_tool_names("exec", '{"command": "cat references/models.md"}')
    == ["exec: cat references/models.md"],
)
check(
    "direct call keeps its arguments",
    agent_mod._effective_tool_names("list_providers", '{"providerType": "provider-account/openai"}')
    == ['list_providers {"providerType":"provider-account/openai"}'],
)
check(
    "wrapped call keeps its input",
    agent_mod._effective_tool_names(
        "call_tool", '{"mcp_server": "gateway", "tool_name": "list_roles", "input": {"limit": 5}}'
    )
    == ['gateway/list_roles {"limit":5}'],
)
check(
    "long arguments are truncated",
    len(agent_mod._effective_tool_names("gateway_execute_sql", json.dumps({"q": "x" * 5000}))[0])
    == len("gateway_execute_sql ") + agent_mod.TOOL_ARGS_LABEL_LIMIT,
)
check(
    "manifest arguments are kept whole, direct or wrapped",
    agent_mod._effective_tool_names("apply_manifest", json.dumps({"m": "x" * 5000}))[0]
    == "apply_manifest " + json.dumps({"m": "x" * 5000}, separators=(",", ":"))
    and len(agent_mod._effective_tool_names(
        "call_tool", json.dumps({"mcp_server": "p", "tool_name": "validate_manifest", "input": {"m": "x" * 5000}})
    )[0]) > 5000,
)
check(
    "unparseable arguments fall back to the wrapper name",
    agent_mod._effective_tool_names("call_tool", "not json") == ["call_tool"],
)

# --- tool labels carry results; sandbox MCP calls are seen -------------------

long_input = {"manifest": "x" * 3000}
transcript = [
    {"type": "model.message", "tool_calls": [
        {"id": "c1", "name": "call_tool", "arguments": json.dumps(
            {"mcp_server": "tfy-platform-mcp", "tool_name": "create_grants", "input": long_input})},
        {"id": "c2", "name": "exec", "arguments": json.dumps({"command": (
            "mcp-client call-tool tfy-platform-mcp list_users '{}' | jq .; "
            "python3 -c 'call_tool(\"tfy-platform-mcp\", \"apply_manifest\", m)'")})},
        {"id": "c3", "name": "get_me", "arguments": "{}"},
    ]},
    {"type": "tool.response", "tool_call_id": "c1", "content": '{"error":"User denied tool call: denied by eval harness"}'},
    {"type": "tool.response", "tool_call_id": "c2", "content": "line one\n  line two"},
]
labels, sandbox = agent_mod.tool_labels(transcript)
check("a wrapped call with long arguments still unwraps", labels[0].startswith("tfy-platform-mcp/create_grants {"))
check("label carries the start of its result", labels[0].endswith('-> {"error":"User denied tool call: denied by eval harness"}'))
check("results are flattened to one line", labels[1].endswith("-> line one line two"))
check("a call with no result has no arrow", labels[2] == "get_me")
check("a short result is whole and unmarked", not labels[1].endswith(agent_mod.RESULT_CUT_MARKER))
row = '{"model":"gpt-4o","requests":12345}'
cut_label = agent_mod.tool_labels([
    {"type": "model.message", "tool_calls": [{"id": "r", "name": "query", "arguments": "{}"}]},
    {"type": "tool.response", "tool_call_id": "r",
     "content": (row * 200)[:agent_mod.TRANSCRIPT_RESULT_LIMIT]},
])[0][0]
check("a long result is kept far past its first rows", cut_label.count("12345") > 50, cut_label[:80])
check("a result the transcript cut is marked as cut", cut_label.endswith(agent_mod.RESULT_CUT_MARKER))

said = [
    {"type": "model.message", "thread_id": "main", "content": "Checking the app first."},
    {"type": "model.message", "thread_id": "sub", "content": "subagent notes"},
    {"type": "model.message", "thread_id": "main", "content": "", "tool_calls": []},
    {"type": "model.message", "thread_id": "main", "content": "It is paused, so no pods start."},
    {"type": "model.message", "thread_id": "main", "content": "Final answer."},
]
check("interim messages are the root agent's, before the answer",
      agent_mod.interim_messages(said, "Final answer.") == ["Checking the app first.", "It is paused, so no pods start."])
interim_prompt = judge.build_prompt(question="q", expected="e", candidate="a", interim=["It is paused."])
check("the judge sees interim messages", "EARLIER AGENT MESSAGES" in interim_prompt and "- It is paused." in interim_prompt)
check("no interim section without messages", "EARLIER AGENT MESSAGES" not in judge.build_prompt(
    question="q", expected="e", candidate="a"))
check("sandbox MCP calls are extracted in order",
      sandbox == ["tfy-platform-mcp/list_users", "tfy-platform-mcp/apply_manifest"])
check("tool_label_name strips args and result", agent_mod.tool_label_name(labels[0]) == "tfy-platform-mcp/create_grants")
check("tool_label_name on exec", agent_mod.tool_label_name("exec: cat x -> y") == "exec")

# --- the harness's own replies are part of the record -------------------------


class _Event:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _Call:
    def __init__(self, call_id, name, arguments):
        self.id = call_id
        self.function = _Event(name=name, arguments=arguments)
        self.tool_info = _Event(name=name, type="truefoundry-system")


ask = _Call("q1", "ask_user_question", json.dumps({"question": "Which RPS target?"}))
events = {"m1": _Event(type="model.message", thread_id="main", content="", tool_calls=[ask])}
pending = _Event(thread_id="main", tool_calls=[_Event(id="q1", source_event_id="m1")])
run = agent_mod.AgentRun(question_id="q", trial=0)
resume = agent_mod._resume_input(run, events, [], [pending], "deny", "10 per replica")
check("the scripted reply is sent", resume[0]["content"] == "10 per replica")
check("the exchange is recorded", run.exchanges == [
    {"asked": "Which RPS target?", "reply": "10 per replica", "via": "ask_user_question"}])
labels, _ = agent_mod.tool_labels(agent_mod._transcript(run, events, ["m1"]))
check("the reply shows as the question's result", labels[0].endswith("-> 10 per replica"), labels[0])

check("an answer ending on a question asks in text",
      agent_mod.asks_in_text("I can retry it.\n\nWhich model and workspace is it?") == "Which model and workspace is it?")
check("an answer with no question does not", agent_mod.asks_in_text("Done. The service is scaled.") is None)
check("a question early in a long answer does not count",
      agent_mod.asks_in_text("Why did it fail? " + "x" * 2000 + " Done.") is None)
check("a request without a question mark asks in text",
      agent_mod.asks_in_text("Steps below.\n\nPlease send the HF URL, the workspace, and the exact error text.")
      == "Please send the HF URL, the workspace, and the exact error text.")
check("questions listed before a closing plan still count",
      agent_mod.asks_in_text("1. **The workspace.**\n2. **Gated?** If so, the HF token.\n\n" + "y" * 600
                             + "\n\nOnce I have these, I'll retry the spec call.") is not None)
check("an answer that only reports what it did does not ask",
      agent_mod.asks_in_text("I sent the manifest to apply_manifest and it was denied, so nothing changed.") is None)

# --- critical claims decide the verdict ---------------------------------------

crit = lambda v: [{"importance": "critical", "verdict": v}, {"importance": "normal", "verdict": "supported"}]
check("missing critical claim fails", judge.decide_verdict(0.9, 0, 0.7, crit("missing")) == "incorrect")
check("partial critical claim cannot pass", judge.decide_verdict(0.9, 0, 0.7, crit("partial")) == "partially_correct")
check("supported critical claim passes", judge.decide_verdict(0.9, 0, 0.7, crit("supported")) == "correct")

# --- judge JSON is read whole before any fence inside it ----------------------

payload = {"claims": [{"claim": "c", "verdict": "supported", "evidence": "```yaml\nname: x\n```"}]}
check("whole JSON wins over a fence quoted inside it", judge._extract_json(json.dumps(payload)) == payload)
check("fenced reply still parses", judge._extract_json("```json\n" + json.dumps(payload) + "\n```") == payload)
check("judge version is a short hash", len(judge.JUDGE_VERSION) == 12)

# --- failure classification and retries --------------------------------------


class _FakeRunClient:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0


def _fake_run(outcome):
    def run(client, agent, question, on_progress=None, **kwargs):
        client.calls += 1
        status, failure = client.outcomes.pop(0)
        r = agent_mod.AgentRun(question_id="q", trial=0, status=status)
        r.failure = failure
        r.metrics = {"total_cost_in_usd": 0.5}
        return r
    return run


real_run, real_sleep = agent_mod.run_question, agent_mod.time.sleep
agent_mod.time.sleep = lambda _s: None
try:
    agent_mod.run_question = _fake_run(None)
    c = _FakeRunClient([("error", "infra:turn_error"), ("done", None)])
    r = agent_mod.run_question_with_retries(c, {}, "q", retries=2)
    check("infra failure is retried", c.calls == 2 and r.status == "done" and r.attempts == 2)
    check("cost adds up across attempts", r.metrics["total_cost_in_usd"] == 1.0)
    check("the retried attempt is kept", [a.failure for a in r.earlier_attempts] == ["infra:turn_error"]
          and r.to_json()["earlier_attempts"][0]["failure"] == "infra:turn_error")
    c = _FakeRunClient([("done", "agent:step_limit"), ("done", None)])
    r = agent_mod.run_question_with_retries(c, {}, "q", retries=2)
    check("agent failure is not retried", c.calls == 1 and r.failure == "agent:step_limit")
    c = _FakeRunClient([("paused", "infra:mcp_auth"), ("done", None)])
    agent_mod.run_question_with_retries(c, {}, "q", retries=2)
    check("MCP auth is not retried", c.calls == 1)
finally:
    agent_mod.run_question, agent_mod.time.sleep = real_run, real_sleep


class _Sessions:
    def create(self, **kwargs):
        return _Event(data=_Event(id="s1"))


class _Client:
    sessions = _Sessions()


def _done(content):
    return _Event(status="done", output=_Event(content=content), metrics=None, required_actions=[])


def _scripted_turns(answers):
    sent = []

    def stream(client, session_id, turn_input, **kwargs):
        sent.append(turn_input)
        return _done(answers[len(sent) - 1]), [], []
    return stream, sent


real_stream = agent_mod._stream_turn
try:
    agent_mod._stream_turn, sent = _scripted_turns(["Which workspace should I use?", "Deployed to archit-ws."])
    r = agent_mod.run_question(_Client(), {}, "deploy it", question_id="q", follow_up="archit-ws")
    check("a question asked in text gets the scripted reply",
          r.answer == "Deployed to archit-ws." and sent[1] == [{"type": "user.message", "content": "archit-ws"}])
    check("and is recorded as an exchange", r.exchanges[0]["via"] == "message" and r.clarifications_asked)
    agent_mod._stream_turn, sent = _scripted_turns(["Which one?", "Still: which one?", "unused"])
    r = agent_mod.run_question(_Client(), {}, "q", question_id="q", follow_up="that one")
    check("the reply is sent only once", len(sent) == 2 and r.answer == "Still: which one?")
    agent_mod._stream_turn, sent = _scripted_turns(["Which one?"])
    r = agent_mod.run_question(_Client(), {}, "q", question_id="q")
    check("no scripted reply, no follow-up", len(sent) == 1 and not r.exchanges)
finally:
    agent_mod._stream_turn = real_stream


class _AbortingSessions:
    def create(self, **kwargs):
        raise agent_mod.AbortRun("wrong skills commit")


class _AbortingClient:
    sessions = _AbortingSessions()


try:
    agent_mod.run_question(_AbortingClient(), {}, "q", question_id="q")
    check("AbortRun propagates out of run_question", False)
except agent_mod.AbortRun:
    check("AbortRun propagates out of run_question", True)

print()
if failures:
    print(f"{len(failures)} check(s) failed: {', '.join(failures)}")
    sys.exit(1)
print("all checks passed")
