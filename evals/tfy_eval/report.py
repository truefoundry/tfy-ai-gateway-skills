"""Aggregate answers and grades into a summary plus a readable markdown report."""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from typing import Any

from .dataset import Question

VERDICT_ORDER = ("correct", "partially_correct", "incorrect", "ungraded")


def _mean(values: list[float]) -> float:
    return statistics.fmean(values) if values else 0.0


def build_summary(
    questions: list[Question],
    answers: list[dict],
    grades: list[dict],
    *,
    meta: dict[str, Any] | None = None,
) -> dict:
    """Roll per-trial records up to per-question, then to suite level.

    A question with repeats > 1 is scored by its mean score, but counts as a
    contradiction if *any* trial contradicted the reference — an agent that
    sometimes gives a confidently wrong answer is not safe to ship.
    """
    by_id = {q.id: q for q in questions}
    answers_by_key = {(a["question_id"], a["trial"]): a for a in answers}
    grades_by_question: dict[str, list[dict]] = defaultdict(list)
    for grade in grades:
        grades_by_question[grade["question_id"]].append(grade)

    per_question = []
    for question in questions:
        trials = sorted(grades_by_question.get(question.id, []), key=lambda g: g["trial"])
        scores = [g["score"] for g in trials if g["verdict"] != "ungraded"]
        verdicts = [g["verdict"] for g in trials]
        trial_answers = [
            answers_by_key.get((question.id, g["trial"]), {}) for g in trials
        ]
        worst = min(
            trials,
            key=lambda g: (g["score"], -g.get("contradictions", 0)),
            default=None,
        )
        per_question.append(
            {
                "id": question.id,
                "question": question.question,
                "tags": question.tags,
                "expected": question.expected,
                "trials": len(trials),
                "score": _mean(scores),
                "score_spread": (max(scores) - min(scores)) if len(scores) > 1 else 0.0,
                "verdict": _consensus_verdict(verdicts),
                "contradictions": sum(g.get("contradictions", 0) for g in trials),
                "high_risk_additions": sum(g.get("high_risk_additions", 0) for g in trials),
                "asked_clarification": any(
                    a.get("clarifications_asked") for a in trial_answers
                ),
                "run_errors": [
                    a.get("error") for a in trial_answers if a.get("status") != "done"
                ],
                "worst_trial": worst,
                "answers": trial_answers,
                "grades": trials,
            }
        )

    graded = [q for q in per_question if q["verdict"] != "ungraded"]
    verdict_counts = Counter(q["verdict"] for q in per_question)
    claim_counts: Counter = Counter()
    for grade in grades:
        claim_counts.update(grade.get("counts", {}))

    total_claims = sum(claim_counts.values())
    run_statuses = Counter(a.get("status", "unknown") for a in answers)

    summary = {
        "meta": meta or {},
        "totals": {
            "questions": len(questions),
            "agent_runs": len(answers),
            "graded_questions": len(graded),
            # Answered vs graded-correct are reported separately: a question the
            # agent never got to answer says nothing about its accuracy.
            "answered": len(graded),
            "unanswered": len(per_question) - len(graded),
            "completion_rate": (len(graded) / len(per_question)) if per_question else 0.0,
            "mean_score": _mean([q["score"] for q in graded]),
            "pass_rate": (verdict_counts["correct"] / len(graded)) if graded else 0.0,
            "contradiction_rate": (
                sum(1 for q in graded if q["contradictions"]) / len(graded) if graded else 0.0
            ),
            "clarification_rate": (
                sum(1 for q in per_question if q["asked_clarification"]) / len(per_question)
                if per_question
                else 0.0
            ),
            "verdicts": {v: verdict_counts.get(v, 0) for v in VERDICT_ORDER},
            "claims": dict(claim_counts),
            "claim_coverage": (
                (claim_counts.get("supported", 0) + 0.5 * claim_counts.get("partial", 0))
                / total_claims
                if total_claims
                else 0.0
            ),
            "run_statuses": dict(run_statuses),
            "total_cost_usd": sum(
                (a.get("metrics") or {}).get("total_cost_in_usd") or 0.0 for a in answers
            ),
            "total_tokens": sum(
                (a.get("metrics") or {}).get("total_tokens") or 0 for a in answers
            ),
            "mean_duration_s": _mean([a.get("duration_s", 0.0) for a in answers]),
        },
        "by_tag": _by_tag(per_question),
        "questions": per_question,
    }
    return summary


def _consensus_verdict(verdicts: list[str]) -> str:
    """Worst verdict across trials, so instability shows up as a failure."""
    if not verdicts:
        return "ungraded"
    real = [v for v in verdicts if v != "ungraded"]
    if not real:
        return "ungraded"
    for verdict in ("incorrect", "partially_correct", "correct"):
        if verdict in real:
            return verdict
    return "ungraded"


def _by_tag(per_question: list[dict]) -> dict:
    buckets: dict[str, list[dict]] = defaultdict(list)
    for question in per_question:
        for tag in question["tags"] or ["untagged"]:
            buckets[tag].append(question)
    return {
        tag: {
            "questions": len(items),
            # Scored over answered questions only, so the count and the mean are
            # not describing different denominators.
            "answered": sum(1 for q in items if q["verdict"] != "ungraded"),
            "mean_score": _mean([q["score"] for q in items if q["verdict"] != "ungraded"]),
            "correct": sum(1 for q in items if q["verdict"] == "correct"),
            "contradictions": sum(1 for q in items if q["contradictions"]),
        }
        for tag, items in sorted(buckets.items())
    }


def _pct(value: float) -> str:
    return f"{value * 100:.0f}%"


def _bar(score: float, width: int = 10) -> str:
    filled = round(score * width)
    return "#" * filled + "." * (width - filled)


def to_markdown(summary: dict) -> str:
    totals = summary["totals"]
    meta = summary.get("meta", {})
    lines = ["# Agent eval report", ""]

    if meta:
        descriptors = [
            f"agent `{meta.get('agent')}`" if meta.get("agent") else "",
            f"judge `{meta.get('judge_model')}`" if meta.get("judge_model") else "",
            f"{meta.get('repeats', 1)} trial(s)/question",
            f"pass threshold {meta.get('pass_threshold')}" if meta.get("pass_threshold") else "",
            meta.get("run_id", ""),
        ]
        lines += [" | ".join(d for d in descriptors if d), ""]

    lines += [
        "## Headline",
        "",
        f"- **Answered**: {totals['answered']}/{totals['questions']} questions "
        f"({_pct(totals['completion_rate'])}). "
        + (
            f"{totals['unanswered']} produced no answer at all and are excluded from "
            "the accuracy numbers below - see 'Never answered'."
            if totals["unanswered"]
            else "Every question produced an answer."
        ),
        f"- **Pass rate**: {_pct(totals['pass_rate'])} "
        f"({totals['verdicts']['correct']}/{totals['answered']} *answered* questions fully correct)",
        f"- **Contradiction rate**: {_pct(totals['contradiction_rate'])} "
        "(answers that assert the opposite of ground truth - the failures to fix first)",
        f"- **Mean score**: {totals['mean_score']:.2f}",
        f"- **Claim coverage**: {_pct(totals['claim_coverage'])} of reference claims "
        f"covered ({totals['claims'].get('supported', 0)} supported, "
        f"{totals['claims'].get('partial', 0)} partial, "
        f"{totals['claims'].get('missing', 0)} missing, "
        f"{totals['claims'].get('contradicted', 0)} contradicted)",
        f"- **Asked for clarification instead of answering**: {_pct(totals['clarification_rate'])}",
        f"- **Cost**: ${totals['total_cost_usd']:.2f} over {totals['agent_runs']} runs, "
        f"{totals['mean_duration_s']:.0f}s mean latency",
        "",
    ]

    failed_runs = {k: v for k, v in totals["run_statuses"].items() if k != "done"}
    if failed_runs:
        detail = ", ".join(f"{count} {status}" for status, count in sorted(failed_runs.items()))
        lines += [f"> Agent runs that did not complete cleanly: {detail}.", ""]

    lines += ["## Verdict by question", "", "| Q | Score | Verdict | Flags | Topic |", "|---|---|---|---|---|"]
    graded_first = sorted(
        summary["questions"], key=lambda q: (q["verdict"] == "ungraded", q["score"], q["id"])
    )
    for question in graded_first:
        if question["verdict"] == "ungraded":
            lines.append(
                f"| {question['id']} | - | no answer | see 'Never answered' "
                f"| {', '.join(question['tags']) or '-'} |"
            )
            continue
        flags = []
        if question["contradictions"]:
            flags.append(f"{question['contradictions']} contradicted")
        if question["high_risk_additions"]:
            flags.append(f"{question['high_risk_additions']} risky claim")
        if question["asked_clarification"]:
            flags.append("asked clarification")
        if question["score_spread"] > 0.25:
            flags.append(f"unstable (spread {question['score_spread']:.2f})")
        if any(question["run_errors"]):
            flags.append("run error")
        lines.append(
            f"| {question['id']} | `{_bar(question['score'])}` {question['score']:.2f} "
            f"| {question['verdict']} | {', '.join(flags) or '-'} "
            f"| {', '.join(question['tags']) or '-'} |"
        )
    lines.append("")

    if summary["by_tag"]:
        lines += [
            "## By topic",
            "",
            "| Topic | Answered / asked | Mean score | Fully correct | With contradictions |",
            "|---|---|---|---|---|",
        ]
        for tag, stats in sorted(summary["by_tag"].items(), key=lambda kv: kv[1]["mean_score"]):
            score = f"{stats['mean_score']:.2f}" if stats["answered"] else "-"
            lines.append(
                f"| {tag} | {stats['answered']}/{stats['questions']} | {score} "
                f"| {stats['correct']} | {stats['contradictions']} |"
            )
        lines.append("")

    unanswered = [q for q in summary["questions"] if q["verdict"] == "ungraded"]
    if unanswered:
        lines += [
            "## Never answered",
            "",
            "These runs failed before the agent produced an answer, so they are not a "
            "measure of its accuracy. Fix these, then re-run with `--retry-failed`.",
            "",
            "| Q | Attempts | Reason |",
            "|---|---|---|",
        ]
        for question in unanswered:
            answers_for_q = question["answers"]
            attempts = max((a.get("attempts") or 1) for a in answers_for_q) if answers_for_q else 1
            reason = next((e for e in question["run_errors"] if e), "unknown")
            lines.append(f"| {question['id']} | {attempts} | {_cell(reason, 300)} |")
        lines.append("")

    worst = [
        q for q in summary["questions"] if q["verdict"] not in ("correct", "ungraded")
    ]
    worst.sort(key=lambda q: (-q["contradictions"], q["score"]))
    if worst:
        lines += ["## What went wrong", ""]
        for question in worst:
            grade = question["worst_trial"] or {}
            lines += [
                f"### {question['id']} - {question['verdict']} (score {question['score']:.2f})",
                "",
                f"**Asked:** {question['question']}",
                "",
            ]
            if grade.get("summary"):
                lines += [f"**Judge:** {grade['summary']}", ""]
            bad = [
                c
                for c in grade.get("claims", [])
                if c.get("verdict") in ("contradicted", "missing", "partial")
            ]
            if bad:
                lines.append("| Reference claim | Verdict | Evidence |")
                lines.append("|---|---|---|")
                for claim in bad:
                    mark = "**contradicted**" if claim["verdict"] == "contradicted" else claim["verdict"]
                    lines.append(
                        f"| {_cell(claim.get('claim'))}"
                        f"{' (critical)' if str(claim.get('importance')) == 'critical' else ''} "
                        f"| {mark} | {_cell(claim.get('evidence'))} |"
                    )
                lines.append("")
            for addition in grade.get("unsupported_additions", []):
                lines.append(
                    f"- Unsupported ({addition.get('risk', 'low')} risk): "
                    f"{_cell(addition.get('statement'))} - {_cell(addition.get('note'))}"
                )
            session_urls = [a.get("session_url") for a in question["answers"] if a.get("session_url")]
            if session_urls:
                lines += ["", f"Session: {session_urls[0]}"]
            lines.append("")

    return "\n".join(lines)


def _cell(text: Any, limit: int = 240) -> str:
    """Flatten text so it survives a markdown table cell."""
    flat = " ".join(str(text or "").split())
    if len(flat) > limit:
        flat = flat[: limit - 1] + "…"
    return flat.replace("|", "\\|")
