"""Checks that the skill bundle will upload and that its internal file references resolve.

The 20,000 limit is enforced server-side by `tfy apply`; checking both characters and UTF-8 bytes
keeps us under it whichever the server counts.
"""

import re
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[2] / "skills"
SKILL_MD_LIMIT = 20_000
DESCRIPTION_LIMIT = 1_024

# A backticked path ending in .md, e.g. `failure-modes/jobs.md` or `references/support-tickets.md`.
MD_REFERENCE = re.compile(r"`([A-Za-z0-9_./-]+\.md)`")

# Where a bare reference may point, by the referencing file's location. AI Engineering files are
# written relative to ai-engineering/references/ (as SKILL.md tells the reader), never to their own
# directory, so `failure-modes/x.md` must carry its prefix even from inside failure-modes/.
ROOTS = {
    "ai-engineering": ["", "ai-engineering/references"],
    "ai-gateway": ["", "ai-gateway/references", "<own>"],
    "": ["", "ai-gateway/references", "ai-engineering/references", "<own>"],
}


def roots_for(path: Path) -> list[Path]:
    rel = path.relative_to(SKILL_DIR)
    area = rel.parts[0] if len(rel.parts) > 1 and rel.parts[0] in ROOTS else ""
    return [path.parent if r == "<own>" else SKILL_DIR / r for r in ROOTS[area]]


def check_skill_md(errors: list[str]) -> None:
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    chars, size = len(text), len(text.encode("utf-8"))
    print(f"SKILL.md: {chars} characters, {size} bytes (limit {SKILL_MD_LIMIT})")
    if max(chars, size) > SKILL_MD_LIMIT:
        errors.append(f"SKILL.md is {chars} characters / {size} bytes; the limit is {SKILL_MD_LIMIT}")
    match = re.search(r"^description:\s*(.+)$", text, re.MULTILINE)
    if not match or len(match.group(1)) > DESCRIPTION_LIMIT:
        errors.append(f"SKILL.md frontmatter description is missing or over {DESCRIPTION_LIMIT} characters")


def check_references(errors: list[str]) -> None:
    for path in sorted(SKILL_DIR.rglob("*.md")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for ref in MD_REFERENCE.findall(line):
                if ref == "SKILL.md" or "<" in ref:
                    continue
                if not any((root / ref).is_file() for root in roots_for(path)):
                    errors.append(f"{path.relative_to(SKILL_DIR)}:{lineno}: `{ref}` does not resolve")


def main() -> int:
    errors: list[str] = []
    check_skill_md(errors)
    check_references(errors)
    for error in errors:
        print(f"ERROR: {error}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
