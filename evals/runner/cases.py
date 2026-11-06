"""Eval cases, read from the skills commit under test.

Cases live in `evals/evals.json` in tfy-ai-gateway-skills and change with the skills, so they are
read from the same commit the agent runs. A dataset generated once goes stale: by Nov 4 the copy
in tfy-agent-eval-tenant lacked three cases and had two out of date. Older commits kept the file
at `skills/evals/evals.json`, inside the directory mounted into the agent's sandbox.

Each case may carry:
- `expectations`: strings, or {"text": ..., "critical": true} for the claims a pass needs;
- `tags`: {"area": ..., "kind": ...}, plus "regression": the issue link for a case that reproduces a
  confirmed production issue. The gate fails a candidate that fails such a case in 2 of 3 trials;
- `clarification_reply`: what the user answers when the agent asks;
- `skip`: why the case cannot be measured right now. Skipped cases are reported, never run.

Text may hold `{{trace.<name>.<field>}}` placeholders for fixtures that change every seeding, like
trace ids. A case is hashed and stored with its placeholders; only the agent and judge see the values.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tfy_eval.dataset import Question, normalize_expectations
from tfy_eval.judge import CONDITIONAL_CLAIM

EVALS_PATHS = ("evals/evals.json", "skills/evals/evals.json")
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
FIXTURES_FILE = Path(__file__).resolve().parent / "runs" / "fixtures.json"
# Devtest keeps traces for about a week; older values may name traces that are gone.
FIXTURES_MAX_AGE = timedelta(days=2)
PLACEHOLDER = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout


def resolve_commit(repo: Path, ref: str) -> str:
    """The full SHA for `ref`, which the sandbox must be able to fetch from GitHub."""
    try:
        _git(repo, "fetch", "--quiet", "origin")
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"git fetch origin failed in {repo}: {exc.stderr.strip()}") from None
    try:
        sha = _git(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}").strip()
    except subprocess.CalledProcessError:
        raise SystemExit(f"{ref} is not a commit in {repo}") from None
    if not FULL_SHA.match(sha):
        raise SystemExit(f"{ref} resolved to {sha!r}, not a full commit SHA")
    if not _git(repo, "branch", "--remotes", "--list", "origin/*", "--contains", sha).strip():
        raise SystemExit(f"{sha} is on no branch of origin; push it first, or the sandbox cannot fetch it")
    return sha


def _expectations(raw: object) -> list[dict]:
    if not isinstance(raw, list):
        return normalize_expectations(raw)
    return normalize_expectations([
        {"claim": entry.get("text", ""), "importance": "critical" if entry.get("critical") else "normal"}
        if isinstance(entry, dict) and "text" in entry else entry
        for entry in raw
    ])


def _tags(raw: object) -> list[str]:
    if isinstance(raw, dict):
        return [f"{key}:{value}" for key, value in sorted(raw.items())]
    return [str(tag) for tag in raw or []]


def conditional_critical_claims(case: Question) -> list[str]:
    """Critical claims written as a condition. The judge cannot rule a critical claim not
    applicable, so one whose condition never occurs fails every run of its case."""
    return [
        e["claim"] for e in case.expectations
        if e["importance"] == "critical" and CONDITIONAL_CLAIM.match(e["claim"])
    ]


def case_from_eval(entry: dict) -> Question:
    return Question(
        id=f"s{entry['id']}",
        question=entry["prompt"],
        expected=entry["expected_output"],
        expectations=_expectations(entry.get("expectations")),
        tags=_tags(entry.get("tags")),
        clarification_reply=entry.get("clarification_reply"),
    )


def is_regression(case: Question) -> bool:
    return any(tag.startswith("regression:") for tag in case.tags)


def case_hash(case: Question) -> str:
    """Identifies what a case asks and how it is graded; a changed case is a different case."""
    content = json.dumps(
        [case.question, case.expected, case.expectations, case.clarification_reply], sort_keys=True
    )
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def load_fixtures(path: Path = FIXTURES_FILE) -> dict[str, str]:
    """The values seed_fixtures recorded, or none if they are missing or old enough to have expired."""
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    if datetime.now(timezone.utc) - datetime.fromisoformat(data["seeded_at"]) > FIXTURES_MAX_AGE:
        return {}
    return data["values"]


def fill(case: Question, values: dict[str, str]) -> Question:
    """The case as the agent and judge see it, with its placeholders replaced."""
    texts = [case.question, case.expected, case.clarification_reply or ""]
    texts += [expectation["claim"] for expectation in case.expectations]
    missing = sorted({key for text in texts for key in PLACEHOLDER.findall(text)} - values.keys())
    if missing:
        raise SystemExit(f"case {case.id} needs {', '.join(missing)}; run `python -m runner.seed_fixtures` first")

    def sub(text: str) -> str:
        return PLACEHOLDER.sub(lambda match: values[match.group(1)], text)

    return replace(
        case,
        question=sub(case.question),
        expected=sub(case.expected),
        expectations=[{**expectation, "claim": sub(expectation["claim"])} for expectation in case.expectations],
        clarification_reply=sub(case.clarification_reply) if case.clarification_reply else None,
    )


def read_evals(repo: Path, sha: str) -> list[dict]:
    for path in EVALS_PATHS:
        try:
            return json.loads(_git(repo, "show", f"{sha}:{path}"))["evals"]
        except subprocess.CalledProcessError:
            continue
    raise SystemExit(f"no eval cases at {sha[:12]} (looked in {', '.join(EVALS_PATHS)})")


def load_cases(repo: Path, sha: str, only: set[str] | None = None) -> tuple[list[Question], dict[str, str]]:
    """The cases to run, and the skipped ones with their reasons."""
    entries = read_evals(repo, sha)
    ids = [f"s{entry['id']}" for entry in entries]
    duplicates = sorted({case_id for case_id in ids if ids.count(case_id) > 1})
    if duplicates:
        raise SystemExit(f"duplicate case ids at {sha[:12]}: {', '.join(duplicates)}")
    if only:
        unknown = only - set(ids)
        if unknown:
            raise SystemExit(f"no such case(s) at {sha[:12]}: {', '.join(sorted(unknown))}")
        entries = [entry for entry in entries if f"s{entry['id']}" in only]
    skipped = {f"s{entry['id']}": str(entry["skip"]) for entry in entries if entry.get("skip")}
    cases = [case_from_eval(entry) for entry in entries if not entry.get("skip")]
    for case in cases:
        if bad := conditional_critical_claims(case):
            raise SystemExit(f"case {case.id} has a critical claim that starts with a condition; make it "
                             f"normal or state what always applies: {bad[0]!r}")
    return cases, skipped
