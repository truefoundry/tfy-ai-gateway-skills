"""Check the judge against a human: grade a blind sample of trials by hand, then measure agreement.

    python -m runner.handgrade sample runner/runs/<run> runner/handgrade/<name> [--n 24]
    python -m runner.handgrade agree runner/handgrade/<name>

`sample` writes grading.md (what to read), grades.csv (what to fill in) and key.json (the judge's
verdicts; don't open it before grading). The sample is stratified by judge verdict and takes at most
one trial per case. Trials that never produced an answer are left out: there is nothing to grade.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from collections import Counter
from pathlib import Path

VERDICTS = ("correct", "partially_correct", "incorrect")


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def sample(run_dir: Path, out: Path, n: int, seed: int) -> None:
    cases = {case["id"]: case for case in _jsonl(run_dir / "dataset.jsonl")}
    answers = {(a["question_id"], a["trial"]): a for a in _jsonl(run_dir / "answers.jsonl")}
    by_verdict: dict[str, list[dict]] = {v: [] for v in VERDICTS}
    for grade in _jsonl(run_dir / "grades.jsonl"):
        answer = answers.get((grade["question_id"], grade["trial"]), {})
        if grade["verdict"] in by_verdict and answer.get("status") == "done" and answer.get("answer", "").strip():
            by_verdict[grade["verdict"]].append(grade)

    rng = random.Random(seed)
    picked: list[dict] = []
    seen: set[str] = set()
    for verdict in VERDICTS:
        rng.shuffle(by_verdict[verdict])
    while len(picked) < n and any(by_verdict.values()):
        for verdict in VERDICTS:
            pool = by_verdict[verdict]
            while pool and pool[-1]["question_id"] in seen:
                pool.pop()
            if pool and len(picked) < n:
                grade = pool.pop()
                seen.add(grade["question_id"])
                picked.append(grade)
    rng.shuffle(picked)

    out.mkdir(parents=True, exist_ok=False)
    lines = [
        f"# Hand grading: {len(picked)} trials from `{run_dir.name}`",
        "",
        "For each trial, read the question, the checklist and the answer, then put a verdict in `grades.csv`:",
        "",
        "- `correct`: every checklist item is met (or reasonably met), and nothing it says is wrong.",
        "- `partially_correct`: the main point is right, but a checklist item is missed or only half met.",
        "- `incorrect`: a **critical** item is missed, it says something false, or it did something unsafe.",
        "",
        "Grade from the answer and the tools it called. Open the session link if the answer depends on tool output.",
        "Add a note whenever you are unsure or think the checklist itself is wrong.",
        "",
    ]
    rows, key = [], {}
    for index, grade in enumerate(picked, 1):
        hid = f"H{index:02d}"
        case = cases[grade["question_id"]]
        answer = answers[(grade["question_id"], grade["trial"])]
        key[hid] = {"case": case["id"], "trial": grade["trial"], "judge": grade["verdict"], "judge_summary": grade.get("summary", "")}
        rows.append({"id": hid, "case": case["id"], "trial": grade["trial"], "verdict": "", "notes": ""})
        checklist = [
            f"{n}. {'**[critical]** ' if item.get('importance') == 'critical' else ''}{item['claim']}"
            for n, item in enumerate(case["expectations"], 1)
        ]
        tools = ", ".join(answer.get("tool_calls", [])[:40]) or "none"
        lines += [
            f"## {hid}: case {case['id']}, trial {grade['trial']}",
            "",
            f"**Question:** {case['question']}",
            "",
            f"**What a good answer does:** {case.get('expected', '')}",
            "",
            "**Checklist:**",
            "",
            *checklist,
            "",
            f"**Tools called ({len(answer.get('tool_calls', []))}):** {tools}",
            "",
            f"**Approvals:** {', '.join(answer.get('approvals_granted') or []) or 'none'}"
            f" · **Questions asked:** {len(answer.get('clarifications_asked') or [])}"
            f" · **Session:** {answer.get('session_url') or answer.get('session_id')}",
            "",
            *[f"- Asked: {e['asked']}\n  - Replied: {e['reply']}" for e in answer.get("exchanges") or []],
            "",
            "**Answer:**",
            "",
            "````markdown",
            answer["answer"].strip(),
            "````",
            "",
        ]
    (out / "grading.md").write_text("\n".join(lines))
    with (out / "grades.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "case", "trial", "verdict", "notes"])
        writer.writeheader()
        writer.writerows(rows)
    (out / "key.json").write_text(json.dumps(key, indent=2))
    print(f"{len(picked)} trials -> {out}/grading.md; fill in {out}/grades.csv")


def agree(out: Path) -> None:
    key = json.loads((out / "key.json").read_text())
    with (out / "grades.csv").open() as handle:
        human = {row["id"]: row for row in csv.DictReader(handle) if row["verdict"].strip()}
    unknown = {row["verdict"] for row in human.values()} - set(VERDICTS)
    if unknown:
        raise SystemExit(f"unknown verdicts {sorted(unknown)}; use {', '.join(VERDICTS)}")
    if not human:
        raise SystemExit("no verdicts in grades.csv yet")

    pairs = [(row["verdict"].strip(), key[hid]["judge"]) for hid, row in human.items()]
    exact = sum(h == j for h, j in pairs) / len(pairs)
    passed = sum((h == "correct") == (j == "correct") for h, j in pairs) / len(pairs)
    # Cohen's kappa on pass/fail, the decision the gate actually uses.
    h_rate = sum(h == "correct" for h, _ in pairs) / len(pairs)
    j_rate = sum(j == "correct" for _, j in pairs) / len(pairs)
    chance = h_rate * j_rate + (1 - h_rate) * (1 - j_rate)
    kappa = (passed - chance) / (1 - chance) if chance < 1 else 1.0

    print(f"{len(pairs)} graded of {len(key)}")
    print(f"Same verdict: {exact:.0%} · same pass/fail: {passed:.0%} · pass/fail kappa: {kappa:.2f}")
    print("Judge too lenient (judge passed, you did not):", sum(j == "correct" and h != "correct" for h, j in pairs))
    print("Judge too strict (you passed, judge did not):", sum(h == "correct" and j != "correct" for h, j in pairs))
    print("Confusion (you -> judge):", dict(Counter(f"{h} -> {j}" for h, j in pairs if h != j)))
    for hid, row in sorted(human.items()):
        if row["verdict"].strip() != key[hid]["judge"]:
            print(f"  {hid} {key[hid]['case']}#{key[hid]['trial']}: you {row['verdict']}, judge {key[hid]['judge']}"
                  f"{' - ' + row['notes'] if row['notes'] else ''}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m runner.handgrade")
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("sample")
    s.add_argument("run_dir", type=Path)
    s.add_argument("out", type=Path)
    s.add_argument("--n", type=int, default=24)
    s.add_argument("--seed", type=int, default=7)
    a = sub.add_parser("agree")
    a.add_argument("out", type=Path)
    args = parser.parse_args()
    if args.command == "sample":
        sample(args.run_dir, args.out, args.n, args.seed)
    else:
        agree(args.out)


if __name__ == "__main__":
    main()
