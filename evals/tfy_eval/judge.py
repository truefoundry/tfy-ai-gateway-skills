"""Claim-level LLM judge.

A single similarity score hides the failure that matters most here: the agent
confidently asserting the opposite of the truth. So instead of one score, the
judge splits the reference answer into atomic claims and rules on each one, and
separately flags confident statements in the candidate that the reference
contradicts. The numeric score is then computed in Python from those verdicts,
which keeps it stable across judge runs.

The judge runs as an inline TrueForge agent with no tools or skills, so it can
only reason about the text it is given.
"""

from __future__ import annotations

import hashlib
import json
import re
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from trueforge_sdk import TrueForge

CLAIM_VERDICTS = ("supported", "partial", "missing", "contradicted", "not_applicable")

# Only a claim written as a condition can be ruled not applicable. Without this a judge could
# excuse any claim it found hard to rule on.
CONDITIONAL_CLAIM = re.compile(r"^\W*(only\s+)?(if|when|unless|after|once)\b", re.IGNORECASE)

# Prompts, alignment and scoring all live in this file, so its hash identifies how a run was
# graded. Runs graded differently are not comparable.
JUDGE_VERSION = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:12]

# Counts and costs measured on a live tenant are boundary-sensitive: "between
# 2026-10-01 and 2026-10-15" can legitimately include or exclude the last day, and
# a sliding window moves under you. Demanding exact equality turns that into a
# wrong answer. The tolerance is deliberately narrow in scope - it forgives the
# magnitude of a number the agent did report, never a row it never found or
# attributed to the wrong entity, which is a different and more serious defect.
DEFAULT_NUMERIC_TOLERANCE = 0.10

NUMERIC_TOLERANCE_RULE = """\
- Numeric tolerance: when a claim states a count, cost, percentage or latency,
  judge it on magnitude, not exact equality. Within {supported:.0%} of the stated value is
  `supported`; within {partial:.0%} is `partial`. This absorbs time-window and boundary
  differences on live data. The tolerance applies ONLY to the size of a value the
  candidate actually reported. It never excuses a value the candidate omitted, a
  row or entity it failed to find, or a figure it attributed to the wrong user,
  model or guardrail - those remain `missing` or `contradicted` however close the
  totals look."""


def _tolerance_rule(tolerance: float | None) -> str:
    if not tolerance:
        return (
            "- Numbers must match the stated value; there is no tolerance band."
        )
    return NUMERIC_TOLERANCE_RULE.format(supported=tolerance, partial=tolerance * 2.5)

# Weight applied to a claim the judge marks as load-bearing, so that getting the
# crux of a multi-part answer wrong cannot be averaged away by peripheral detail.
CRITICAL_WEIGHT = 2.0
NORMAL_WEIGHT = 1.0

JUDGE_INSTRUCTIONS = """\
You grade a support agent's answer against a verified reference answer.

The reference answer is ground truth. It was written by an engineer with access to
the actual product behaviour and source code. When the candidate answer disagrees
with the reference, the candidate is wrong — even if it sounds authoritative, cites
documentation, or is the more plausible reading of the docs. Never use your own
knowledge of the product to overrule the reference.

Work in two passes.

PASS 1 - decompose the reference into atomic claims.
Each claim must be one checkable assertion. Split multi-part answers (a/b/c),
bullet lists, and compound sentences. Keep 3-12 claims; merge trivia rather than
exceeding that. Mark a claim "critical" when it is the direct answer to what was
asked or would change what the reader does; mark supporting detail "normal".

PASS 2 - rule on each claim against the candidate answer.
  supported    - the candidate states this, in any wording. Semantics matter, not phrasing.
  partial      - the candidate gets the direction right but is vague, incomplete,
                 or over-hedged where the reference is definite.
  missing      - the candidate does not address this at all.
  contradicted - the candidate asserts something incompatible with this claim.

Grading rules:
- Extra correct detail is not penalised. Only judge the candidate against the reference.
{tolerance}
- "Not documented" / "I could not confirm" where the reference gives a definite
  answer is `missing`, not `contradicted` — unless the candidate also asserts the
  opposite, which is `contradicted`.
- A confident wrong answer is the worst outcome. Never soften `contradicted` to
  `partial` because the rest of the answer was good.
- Also list, under `unsupported_additions`, confident factual claims the candidate
  makes that the reference contradicts or that would mislead the reader. Mark the
  risk `high` only when acting on the statement would cause a real misconfiguration.

Return ONLY a JSON object, no prose and no code fence:

{
  "claims": [
    {"claim": "...", "importance": "critical|normal",
     "verdict": "supported|partial|missing|contradicted",
     "evidence": "short quote from the candidate, or why nothing matched"}
  ],
  "unsupported_additions": [{"statement": "...", "risk": "high|low", "note": "..."}],
  "summary": "one or two sentences on where the candidate diverged"
}
"""

# When the dataset already lists the claims, Pass 1 is skipped. Letting the judge
# re-derive claims it has been handed is pure variance: the same answer scores
# differently run to run because the denominator moved.
JUDGE_INSTRUCTIONS_FIXED = """\
You grade a support agent's answer against a fixed checklist of required claims.

The checklist is ground truth. It was written by an engineer with access to the
actual product behaviour and source code. When the candidate answer disagrees with
a claim, the candidate is wrong — even if it sounds authoritative, cites
documentation, or is the more plausible reading of the docs. Never use your own
knowledge of the product to overrule the checklist.

Do NOT invent, merge, split, reword or drop claims. Return exactly the claims you
were given, in the same order, with the same `importance`, and add a verdict to each.

Rule on each claim:
  supported    - the candidate satisfies this, in any wording. Semantics matter, not phrasing.
  partial      - the candidate gets the direction right but is vague, incomplete,
                 or over-hedged where the claim is definite.
  missing      - the candidate does not address this at all.
  contradicted - the candidate asserts or does something incompatible with this claim.
  not_applicable - ONLY for a claim that starts with a condition ("If ...", "Only if ...",
                 "When ...", "After ...") whose condition did not occur in this run, for
                 example "If register_user returns 409 ..." when the call was denied, or
                 "If the apply is denied ..." when nothing was applied. Say in the evidence
                 why the condition did not occur. Never use it for a critical claim
                 or for any other claim.

Some claims are about what the agent *did*, not what it said — reading a reference
file, calling a tool, validating before applying. Grade those against the OBSERVED
TOOL CALLS section when it is present. If that section is absent or does not show
the step, the claim is `missing`, never `contradicted`: you cannot see everything
the agent did. A claim about a specific query or snippet is graded on the query or
snippet text in the candidate answer, or on the arguments of the call that ran it.

Reading the OBSERVED TOOL CALLS section:
- Each line is `tool {arguments} -> the result the agent got back`. Long arguments and
  results are cut short; a result that ends in `…[cut]` continues past what you see. A
  cut-off value is unknown, not wrong.
- `(called N times)` means the identical call and result happened N times.
- `sandbox/<server>/<tool>` lines are MCP calls a program in the agent's sandbox made;
  their arguments and results are not shown.
- A result like `{"error":"User denied tool call ...` means the user refused the write:
  nothing changed. An answer that says a denied change was made is contradicted.
- Use results to check what the agent reports. If the answer states a fact, quote or
  number that the results shown contradict, list it under `unsupported_additions`, as
  `high` risk when the user would act on it. A tool error that the answer reports as
  success, with no later successful call that covers it, contradicts any claim that the
  agent reports what it found. A failed call followed by a successful retry is not hidden.
- A denied write was refused by the test harness. The denial is not the agent's fault;
  grade what it prepared before it and what it reported after it.

Reading the USER REPLIES section:
- When the agent asked the user something, the user's answer is listed there. The agent
  did receive it, even where an ask_user_question result looks empty or cut short. A
  value the agent takes from a reply is the user's choice, not the agent's guess.

Grading rules:
- Extra correct detail is not penalised. Only judge the candidate against the checklist.
{tolerance}
- "Not documented" / "I could not confirm" where a claim is definite is `missing`,
  not `contradicted` — unless the candidate also asserts the opposite.
- A confident wrong answer is the worst outcome. Never soften `contradicted` to
  `partial` because the rest of the answer was good.
- Also list, under `unsupported_additions`, confident factual claims the candidate
  makes that the checklist contradicts or that would mislead the reader. Mark the
  risk `high` only when acting on the statement would cause a real misconfiguration.
- An addition needs evidence against it: the checklist, a result shown that says
  otherwise, or a figure, name or row missing from a result shown whole (no `…[cut]`).
  A statement whose source was cut off or not shown is unverifiable, not unsupported;
  leave it out. Facts the agent found that the reference answer did not anticipate
  are not contradicted by it.

Return ONLY a JSON object, no prose and no code fence:

{
  "claims": [
    {"n": <the checklist number>, "claim": "<the claim, verbatim>", "importance": "critical|normal",
     "verdict": "supported|partial|missing|contradicted|not_applicable",
     "evidence": "short quote from the candidate, or why nothing matched"}
  ],
  "unsupported_additions": [{"statement": "...", "risk": "high|low", "note": "..."}],
  "summary": "one or two sentences on where the candidate diverged"
}
"""

PROMPT_TEMPLATE = """\
QUESTION
{question}

REFERENCE ANSWER (ground truth)
{expected}

CANDIDATE ANSWER (to grade)
{candidate}
"""

CHECKLIST_SECTION = """\

REQUIRED CLAIMS (the checklist — grade exactly these)
{checklist}
"""

TOOL_CALLS_SECTION = """\

OBSERVED TOOL CALLS (what the agent actually did, in order)
{tool_calls}
"""

EXCHANGES_SECTION = """\

USER REPLIES (questions the agent asked, and what the user answered)
{exchanges}
"""


@dataclass
class Grade:
    question_id: str
    trial: int
    score: float = 0.0
    verdict: str = "ungraded"  # correct | partially_correct | incorrect | ungraded
    claims: list[dict] = field(default_factory=list)
    unsupported_additions: list[dict] = field(default_factory=list)
    summary: str = ""
    counts: dict[str, int] = field(default_factory=dict)
    contradictions: int = 0
    high_risk_additions: int = 0
    judge_runs: int = 1
    error: str | None = None

    def to_json(self) -> dict:
        return {
            "question_id": self.question_id,
            "trial": self.trial,
            "score": round(self.score, 3),
            "verdict": self.verdict,
            "counts": self.counts,
            "contradictions": self.contradictions,
            "high_risk_additions": self.high_risk_additions,
            "summary": self.summary,
            "claims": self.claims,
            "unsupported_additions": self.unsupported_additions,
            "judge_runs": self.judge_runs,
            "error": self.error,
        }


# A shared tenant can expose thousands of models across personal and throwaway
# provider accounts, so the judge is never chosen implicitly: which model graded a
# run has to be recorded and reproducible. These only shape the suggestions shown
# when the caller has not picked one yet.
PREFERRED_PROVIDER_PREFIXES = ("tfy-ai-",)
SUGGESTED_JUDGES = (
    r"claude-opus-5-5$",
    r"claude-sonnet-5-5$",
    r"claude-opus-5$",
    r"gpt-5\.2$",
)


def list_models(client: TrueForge) -> list[str]:
    models = sorted(m.name for m in client.models.list().data)
    if not models:
        raise RuntimeError("no models are configured on this TrueForge server")
    return models


def suggest_judges(models: list[str], limit: int = 8) -> list[str]:
    preferred = [m for m in models if m.startswith(PREFERRED_PROVIDER_PREFIXES)]
    suggestions: list[str] = []
    for pattern in SUGGESTED_JUDGES:
        for model in preferred:
            if re.search(pattern, model) and model not in suggestions:
                suggestions.append(model)
    return suggestions[:limit]


def pick_model(client: TrueForge, preferred: str | None = None) -> str:
    """Resolve the judge model from an exact name or an unambiguous substring."""
    models = list_models(client)

    if not preferred:
        raise RuntimeError(
            "--judge-model is required (or set TRUEFORGE_JUDGE_MODEL): with "
            f"{len(models)} models on this server, guessing would make grades "
            "irreproducible.\nSuggestions:\n  "
            + "\n  ".join(suggest_judges(models))
            + "\nBrowse others with: python -m tfy_eval models --filter sonnet"
        )

    if preferred in models:
        return preferred

    matches = [m for m in models if preferred in m]
    if not matches:
        raise RuntimeError(
            f"no model matches {preferred!r}. "
            "Browse with: python -m tfy_eval models --filter <substring>"
        )
    if len(matches) == 1:
        return matches[0]

    narrowed = [m for m in matches if m.startswith(PREFERRED_PROVIDER_PREFIXES)]
    if len(narrowed) == 1:
        return narrowed[0]

    shown = narrowed or matches
    raise RuntimeError(
        f"{preferred!r} matches {len(matches)} models - pass a full name. Candidates:\n  "
        + "\n  ".join(sorted(shown)[:12])
    )


def _extract_json(text: str) -> dict:
    """Parse the judge's JSON, tolerating code fences and surrounding prose.

    The whole reply is tried first: evidence quoting a manifest can itself contain a fence, and
    taking that fence's body would grade the quote instead of the verdicts.
    """
    text = text.strip()
    decoder = json.JSONDecoder()
    # Only an object with a `claims` list is a verdict: a claim object quoted on its own would
    # otherwise parse and grade every claim missing.
    start = text.find("{")
    while start != -1:
        try:
            payload, _ = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict) and isinstance(payload.get("claims"), list):
            return payload
        start = text.find("{", start + 1)
    raise ValueError(f"judge did not return a JSON verdict: {text[:300]!r}")


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_]+", str(text).lower()))


def align_claims(expectations: list[dict], returned: list[dict]) -> list[dict]:
    """Force the graded claims back onto the dataset's checklist.

    Models reword, merge and silently drop checklist items however firmly you ask
    them not to. Left alone that changes the score denominator, so a question
    would be graded out of 9 claims one run and 7 the next. Here the checklist is
    authoritative: every expectation appears exactly once, with its own text and
    importance, and anything the judge failed to rule on counts as `missing`.
    """
    # The checklist number the judge echoes is the reliable key; a paraphrase can fall under the
    # word-overlap threshold, which for a critical claim would fail the case.
    numbered = {}
    for candidate in returned:
        number = candidate.get("n")
        if isinstance(number, int) and 1 <= number <= len(expectations):
            numbered.setdefault(number, candidate)
    unused = [candidate for candidate in returned if all(candidate is not c for c in numbered.values())]
    aligned = []
    for index, expectation in enumerate(expectations, start=1):
        wanted = _tokens(expectation["claim"])
        best, best_overlap = None, 0.0
        for candidate in unused:
            got = _tokens(candidate.get("claim", ""))
            if not wanted or not got:
                continue
            overlap = len(wanted & got) / len(wanted | got)
            if overlap > best_overlap:
                best, best_overlap = candidate, overlap
        matched = numbered.get(index)
        if matched is None and best_overlap >= 0.4:
            matched = best
            unused.remove(best)
        verdict = str((matched or {}).get("verdict", "")).lower()
        evidence = str((matched or {}).get("evidence", "")) or "judge did not rule on this claim"
        if verdict == "not_applicable" and expectation["importance"] == "critical":
            verdict, evidence = "missing", f"ruled not applicable, but a critical claim always applies: {evidence}"
        elif verdict == "not_applicable" and not CONDITIONAL_CLAIM.match(expectation["claim"]):
            verdict, evidence = "missing", f"ruled not applicable, but the claim has no condition: {evidence}"
        aligned.append(
            {
                "claim": expectation["claim"],
                "importance": expectation["importance"],
                "verdict": verdict if verdict in CLAIM_VERDICTS else "missing",
                "evidence": evidence,
            }
        )
    return aligned


def score_claims(claims: list[dict], high_risk_additions: int) -> tuple[float, dict[str, int]]:
    """Turn claim verdicts into a 0-1 score, weighting critical claims double.

    Contradicted claims score zero rather than negative; the contradiction count
    is reported separately and gates the pass/fail decision, so a wrong answer
    cannot be rescued by a high score. A claim whose condition never occurred is
    left out of the score entirely.
    """
    credit = {"supported": 1.0, "partial": 0.5, "missing": 0.0, "contradicted": 0.0}
    counts = dict.fromkeys(CLAIM_VERDICTS, 0)
    earned = 0.0
    total = 0.0
    for claim in claims:
        verdict = str(claim.get("verdict", "")).lower()
        if verdict not in CLAIM_VERDICTS:
            verdict = "missing"
            claim["verdict"] = verdict
        counts[verdict] += 1
        if verdict == "not_applicable":
            continue
        weight = (
            CRITICAL_WEIGHT
            if str(claim.get("importance", "")).lower() == "critical"
            else NORMAL_WEIGHT
        )
        earned += credit[verdict] * weight
        total += weight
    score = earned / total if total else float(bool(claims))
    if high_risk_additions:
        # A high-risk fabrication is a real defect even when every claim is covered.
        score = max(0.0, score - 0.1 * high_risk_additions)
    return score, counts


def decide_verdict(
    score: float, contradictions: int, pass_threshold: float, claims: list[dict] | None = None
) -> str:
    """A critical claim is the point of the question: missing it fails the answer, and a
    partial one keeps it from passing, however well the rest scores."""
    critical = [
        str(c.get("verdict")).lower() for c in claims or [] if str(c.get("importance", "")).lower() == "critical"
    ]
    if contradictions or "missing" in critical:
        return "incorrect"
    if score >= pass_threshold and "partial" not in critical:
        return "correct"
    if score >= pass_threshold / 2:
        return "partially_correct"
    return "incorrect"


def build_prompt(
    *,
    question: str,
    expected: str,
    candidate: str,
    expectations: list[dict] | None = None,
    tool_calls: list[str] | None = None,
    exchanges: list[dict] | None = None,
) -> str:
    prompt = PROMPT_TEMPLATE.format(question=question, expected=expected, candidate=candidate)
    if exchanges:
        prompt += EXCHANGES_SECTION.format(
            exchanges="\n".join(f"- Asked: {e['asked']}\n  Replied: {e['reply']}" for e in exchanges)
        )
    if expectations:
        checklist = "\n".join(
            f"{i}. [{c.get('importance', 'normal')}] {c['claim']}"
            for i, c in enumerate(expectations, start=1)
        )
        prompt += CHECKLIST_SECTION.format(checklist=checklist)
    if tool_calls:
        # Identical calls are folded into one line with a count: the repetition itself is
        # evidence (claims like "queries once"), the 40 copies are not.
        counts: dict[str, int] = {}
        for call in tool_calls:
            counts[call] = counts.get(call, 0) + 1
        lines = [f"- {call}" + (f" (called {n} times)" if n > 1 else "") for call, n in counts.items()]
        prompt += TOOL_CALLS_SECTION.format(tool_calls="\n".join(lines))
    return prompt


def grade_one(
    client: TrueForge,
    model: str,
    *,
    question_id: str,
    trial: int,
    question: str,
    expected: str,
    candidate: str,
    expectations: list[dict] | None = None,
    tool_calls: list[str] | None = None,
    exchanges: list[dict] | None = None,
    pass_threshold: float = 0.7,
    repeats: int = 1,
    reasoning_effort: str | None = None,
    temperature: float | None = None,
    numeric_tolerance: float | None = DEFAULT_NUMERIC_TOLERANCE,
) -> Grade:
    """Grade one candidate answer. With repeats > 1, scores are median-aggregated."""
    grade = Grade(question_id=question_id, trial=trial, judge_runs=repeats)

    if not (candidate or "").strip():
        # No answer is not the same as a wrong answer: the run failed before the
        # agent said anything (MCP timeout, iteration cap, dropped turn). Scoring
        # it `incorrect` would blame the agent's accuracy for infrastructure.
        grade.error = "no answer to grade - the agent run did not produce one"
        grade.verdict = "ungraded"
        return grade

    # Nothing is sent unless asked for: the newer Claude models reject
    # `temperature` outright, so pinning it here would break the default judge.
    # Use --judge-repeats for grading stability instead.
    params: dict[str, Any] = {}
    if reasoning_effort:
        params["reasoning_effort"] = reasoning_effort
    if temperature is not None:
        params["temperature"] = temperature
    model_spec: dict[str, Any] = {"name": model}
    if params:
        model_spec["params"] = params

    template = JUDGE_INSTRUCTIONS_FIXED if expectations else JUDGE_INSTRUCTIONS
    # Not .format(): both templates contain a literal JSON schema full of braces.
    instructions = template.replace("{tolerance}", _tolerance_rule(numeric_tolerance))
    prompt = build_prompt(
        question=question,
        expected=expected,
        candidate=candidate,
        expectations=expectations,
        tool_calls=tool_calls,
        exchanges=exchanges,
    )

    attempts: list[dict] = []
    errors: list[str] = []
    # One extra try per run, so a transient gateway error does not leave an expensive agent run
    # unmeasured.
    budget = max(1, repeats) + max(1, repeats)
    while len(attempts) < max(1, repeats) and budget > 0:
        budget -= 1
        try:
            session = client.sessions.create(
                agent={
                    "spec": {
                        "model": model_spec,
                        "instructions": instructions,
                    }
                },
                metadata={"eval": "tfy-agent-eval-judge", "question_id": question_id},
            )
            text = ""
            for event in client.sessions.create_turn_stream(
                session_id=session.data.id,
                input=[{"type": "user.message", "content": prompt}],
            ):
                if event.type == "turn.done":
                    if getattr(event.state, "status", None) != "done":
                        raise RuntimeError(
                            getattr(event.state, "message", None)
                            or getattr(event.state, "reason", None)
                            or "judge turn did not complete"
                        )
                    text = str(getattr(getattr(event.state, "output", None), "content", "") or "")
            attempts.append(_extract_json(text))
        except Exception as exc:  # noqa: BLE001 - keep grading the rest of the suite
            errors.append(f"{type(exc).__name__}: {exc}")

    if not attempts:
        grade.error = "; ".join(errors) or "judge produced no result"
        return grade

    scored = []
    for payload in attempts:
        claims = [c for c in payload.get("claims", []) if isinstance(c, dict)]
        if expectations:
            claims = align_claims(expectations, claims)
        additions = [a for a in payload.get("unsupported_additions", []) if isinstance(a, dict)]
        high_risk = sum(1 for a in additions if str(a.get("risk", "")).lower() == "high")
        score, counts = score_claims(claims, high_risk)
        scored.append(
            {
                "score": score,
                "counts": counts,
                "claims": claims,
                "additions": additions,
                "high_risk": high_risk,
                "summary": str(payload.get("summary", "")),
            }
        )

    # Report the run closest to the median score so the surfaced claim list and
    # the headline number always describe the same judgement.
    median_score = statistics.median(entry["score"] for entry in scored)
    chosen = min(scored, key=lambda entry: abs(entry["score"] - median_score))

    grade.score = median_score
    grade.counts = chosen["counts"]
    grade.claims = chosen["claims"]
    grade.unsupported_additions = chosen["additions"]
    grade.high_risk_additions = chosen["high_risk"]
    grade.summary = chosen["summary"]
    grade.contradictions = chosen["counts"].get("contradicted", 0)
    grade.verdict = decide_verdict(grade.score, grade.contradictions, pass_threshold, grade.claims)
    grade.judge_runs = len(scored)
    if errors:
        grade.error = f"{len(errors)} judge run(s) failed: " + "; ".join(errors[:2])
    return grade
