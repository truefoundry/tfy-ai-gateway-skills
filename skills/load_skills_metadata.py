#!/usr/bin/env python3
"""Load YAML frontmatter from all SKILL.md files under a skills directory and print one YAML document."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover
    sys.exit("This script requires PyYAML. Install with: pip install pyyaml")


class HelpFormatter(
    argparse.ArgumentDefaultsHelpFormatter,
    argparse.RawDescriptionHelpFormatter,
):
    """Show defaults in help and preserve epilog formatting."""


def parse_frontmatter(text: str) -> dict[str, object] | None:
    """Parse the first YAML frontmatter block (--- ... ---) at the start of a markdown file."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    body: list[str] = []
    i = 1
    while i < len(lines):
        if lines[i].strip() == "---":
            block = "\n".join(body)
            if not block.strip():
                return {}
            data = yaml.safe_load(block)
            if data is None:
                return {}
            if not isinstance(data, dict):
                raise ValueError(f"frontmatter must be a mapping, got {type(data).__name__}")
            return data
        body.append(lines[i])
        i += 1
    return None


def find_skill_markdown_files(skills_root: Path) -> list[Path]:
    """Return all skill.md / SKILL.md files under skills_root (case-insensitive basename)."""
    found: list[Path] = []
    if not skills_root.is_dir():
        return found
    for path in skills_root.rglob("*"):
        if path.is_file() and path.name.lower() == "skill.md":
            found.append(path)
    return sorted(found)


def load_metadata(skills_root: Path) -> list[dict[str, object]]:
    """Parse each skill file and return a list of records including relative path."""
    skills_root = skills_root.resolve()
    records: list[dict[str, object]] = []
    for path in find_skill_markdown_files(skills_root):
        text = path.read_text(encoding="utf-8")
        try:
            meta = parse_frontmatter(text)
        except yaml.YAMLError as e:
            raise SystemExit(f"YAML error in {path}: {e}") from e
        except ValueError as e:
            raise SystemExit(f"{path}: {e}") from e
        if meta is None:
            print(f"warning: no valid frontmatter in {path}", file=sys.stderr)
            continue
        row: dict[str, object] = dict(meta)
        row["path"] = str(path.parent.as_posix())
        records.append(row)
    return records


def main() -> None:
    default_root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description=(
            "Scan a skills directory for skill markdown files (SKILL.md or skill.md), "
            "read YAML frontmatter from the top of each file, and print a single YAML document."
        ),
        epilog=(
            "Example:\n"
            "  %(prog)s\n"
            "  %(prog)s --skills-dir /path/to/skills\n"
            "Frontmatter must start at the first line with --- and end at the closing ---."
        ),
        formatter_class=HelpFormatter,
    )
    parser.add_argument(
        "--skills-dir",
        nargs="?",
        type=Path,
        default=default_root,
        metavar="SKILLS_DIR",
        help="Root folder to search recursively for skill markdown files",
    )
    args = parser.parse_args()
    root: Path = args.skills_dir
    if not root.is_dir():
        raise SystemExit(f"not a directory: {root}")

    skills = load_metadata(root)
    document = {"skills": skills}
    out = yaml.dump(
        document,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
        width=120,
    )
    sys.stdout.write(out)


if __name__ == "__main__":
    main()
