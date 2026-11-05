"""Static checks on the skills: no agent run, no credentials.

    python scripts/check_skills.py [--no-links]

- Every file under skills/ is at most 12,000 bytes, the skill loader's per-file cap. Files over
  11,500 are listed so the PR that crosses the line splits them.
- Every tool a skill names in backticks exists in tool-schemas/tfy-platform-mcp.json, or is one of
  OTHER_TOOLS, and skills/references/tool-inputs-*.md match that snapshot.
- Every URL a skill links to resolves. Only 404 and 410 fail: a 403 or a timeout from bot
  protection says nothing about whether the page exists, so those are reported, not failed.

Exits 1 on any failure. In GitHub Actions it also writes annotations and a job summary.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

import tool_schemas

SKILLS = Path(__file__).resolve().parent.parent / "skills"
CAP = 12_000
NEAR_CAP = 11_500
URL = re.compile(r"https?://[^\s)>\]\"'`]+")
PLACEHOLDER = re.compile(r"[<>{}]|example\.(com|org)|localhost|127\.0\.0\.1")
GONE = {404, 410}
TOOL_VERBS = ("list|get|create|update|delete|apply|validate|query|register|revoke|generate|search|cancel|"
              "pause|resume|sync|redeploy|check|add|remove|activate|deactivate|reset|resend")
TOOL_NAME = re.compile(rf"`((?:{TOOL_VERBS})_[a-z0-9_]+)`")
# Tools from the docs server, the Ask TFY harness, and Pylon - not in the platform snapshot.
OTHER_TOOLS = {"search_docs", "get_page_layout", "get_section_content", "get_current_datetime", "get_tool_info",
               "create_issue"}


def sizes() -> tuple[list[str], list[str]]:
    over, near = [], []
    for path in sorted(p for p in SKILLS.rglob("*") if p.is_file()):
        size = path.stat().st_size
        rel = path.relative_to(SKILLS.parent)
        if size > CAP:
            over.append(f"{rel}: {size:,} bytes, over the {CAP:,}-byte cap")
        elif size > NEAR_CAP:
            near.append(f"{rel}: {size:,} bytes")
    return over, near


def unknown_tools() -> list[str]:
    known = tool_schemas.tool_names() | OTHER_TOOLS
    found: dict[str, set[str]] = {}
    for path in sorted(SKILLS.rglob("*.md")):
        for name in TOOL_NAME.findall(path.read_text(errors="replace")):
            if name not in known:
                found.setdefault(name, set()).add(str(path.relative_to(SKILLS.parent)))
    return [f"`{name}` in {', '.join(sorted(where))} is not a tool in tool-schemas/tfy-platform-mcp.json"
            for name, where in sorted(found.items())]


def links() -> dict[str, list[str]]:
    """Each checkable URL and the files that link to it."""
    found: dict[str, list[str]] = {}
    for path in sorted(SKILLS.rglob("*.md")):
        for url in URL.findall(path.read_text(errors="replace")):
            url = url.rstrip(".,;:")
            if not PLACEHOLDER.search(url):
                found.setdefault(url, []).append(str(path.relative_to(SKILLS.parent)))
    return found


def status(client: httpx.Client, url: str) -> int | str:
    try:
        response = client.head(url)
        if response.status_code in (405, 403) or response.status_code >= 500:
            response = client.get(url)
        return response.status_code
    except httpx.HTTPError as exc:
        return type(exc).__name__


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-links", action="store_true", help="skip the network check")
    args = parser.parse_args()

    over, near = sizes()
    broken, unchecked = [], []
    if not args.no_links:
        found = links()
        headers = {"User-Agent": "tfy-ai-gateway-skills link check (+https://github.com/truefoundry/tfy-ai-gateway-skills)"}
        with httpx.Client(follow_redirects=True, timeout=20, headers=headers) as client, ThreadPoolExecutor(8) as pool:
            results = dict(zip(found, pool.map(lambda url: status(client, url), found)))
        for url, code in results.items():
            where = ", ".join(sorted(set(found[url])))
            if code in GONE:
                broken.append(f"{url} ({code}) in {where}")
            elif not isinstance(code, int) or code >= 400:
                unchecked.append(f"{url} ({code}) in {where}")

    tools = unknown_tools()
    generated = [f"{problem}: run `python scripts/tool_schemas.py render`" for problem in tool_schemas.stale()]
    failures = over + tools + generated + broken
    lines = ["## Skill checks", ""]
    for title, items in (("Over the size cap", over), ("Unknown tools", tools), ("Stale generated files", generated),
                         ("Broken links", broken),
                         ("Near the size cap (split in the PR that crosses 12,000)", near),
                         ("Links that could not be checked", unchecked)):
        if items:
            lines += [f"**{title}**", "", *[f"- {item}" for item in items], ""]
    if len(lines) == 2:
        lines.append("All files under the cap; every tool exists; all links resolve.")
    report = "\n".join(lines)
    print(report)

    if os.environ.get("GITHUB_ACTIONS"):
        for item in failures:
            print(f"::error::{item}")
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as summary:
            summary.write(report + "\n")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
