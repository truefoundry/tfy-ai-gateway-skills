"""Dataset loading, and conversion from a question/answer spreadsheet.

A dataset is a JSONL file with one record per question. Lines starting with `//`
are comments, so a dataset can carry notes about its own provenance:

    {
      "id": "q1",
      "question": "Which column marks a failed model call?",
      "expected": "IsFailure, not HttpStatusCode ...",
      "expectations": [                                    # optional, see below
        {"claim": "Names IsFailure", "importance": "critical"}
      ],
      "baseline": "You should use HttpStatusCode >= 400",   # optional, a previous answer
      "tags": ["observability"]
    }

`expected` is ground truth. `baseline` is only used by `run --source baseline`,
which scores a previously recorded answer without calling the agent at all.

`expectations` is the reference answer already broken into the claims to grade.
Supply it when you know exactly what the answer must contain - the judge then
grades against your list instead of deriving its own, which removes the noisiest
step in grading. Omit it and the judge decomposes `expected` itself.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


@dataclass
class Question:
    id: str
    question: str
    expected: str
    expectations: list[dict] = field(default_factory=list)
    baseline: str | None = None
    tags: list[str] = field(default_factory=list)
    # What the user says when the agent asks a clarifying question; None sends the generic
    # "no human is available" reply.
    clarification_reply: str | None = None

    def to_json(self) -> dict:
        out = {"id": self.id, "question": self.question, "expected": self.expected}
        if self.expectations:
            out["expectations"] = self.expectations
        if self.baseline:
            out["baseline"] = self.baseline
        out["tags"] = self.tags
        if self.clarification_reply:
            out["clarification_reply"] = self.clarification_reply
        return out


def normalize_expectations(raw: object) -> list[dict]:
    """Accept either a list of claim strings or of {claim, importance} objects."""
    if not raw:
        return []
    if not isinstance(raw, list):
        raise ValueError(f"expectations must be a list, got {type(raw).__name__}")
    claims = []
    for entry in raw:
        if isinstance(entry, str):
            claim, importance = entry, "normal"
        elif isinstance(entry, dict):
            claim = str(entry.get("claim", "")).strip()
            importance = str(entry.get("importance", "normal")).lower()
        else:
            raise ValueError(f"expectation must be a string or object, got {entry!r}")
        if not claim:
            raise ValueError("expectation has no claim text")
        if importance not in ("critical", "normal"):
            raise ValueError(f"importance must be 'critical' or 'normal', got {importance!r}")
        claims.append({"claim": claim, "importance": importance})
    return claims


def _cell_text(cell: ET.Element) -> str:
    inline = cell.find(f"{_NS}is")
    if inline is not None:
        return "".join(t.text or "" for t in inline.iter(f"{_NS}t"))
    value = cell.find(f"{_NS}v")
    return (value.text or "") if value is not None else ""


def _sheet_rows(xlsx_path: Path) -> list[dict[str, str]]:
    """Read the first worksheet as a list of column-letter -> text maps.

    Shared strings are not handled because the source file uses inline strings;
    a file exported from a different tool may need openpyxl instead.
    """
    with zipfile.ZipFile(xlsx_path) as archive:
        sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    rows = []
    for row in sheet.findall(f".//{_NS}row"):
        cells = {}
        for cell in row.findall(f"{_NS}c"):
            column = re.match(r"([A-Z]+)", cell.get("r") or "")
            if column:
                cells[column.group(1)] = _cell_text(cell).strip()
        rows.append(cells)
    return rows


def from_xlsx(
    xlsx_path: Path,
    question_col: str = "A",
    baseline_col: str | None = "B",
    expected_col: str = "C",
) -> list[Question]:
    """Convert a question / previous-answer / reference-answer spreadsheet.

    Tags are left empty: they drive the by-topic breakdown in the report and are
    worth writing by hand, since guessing them from keywords gets it wrong often
    enough to make the breakdown misleading.
    """
    questions = []
    for index, cells in enumerate(_sheet_rows(xlsx_path)):
        raw_question = cells.get(question_col, "")
        expected = cells.get(expected_col, "")
        if not raw_question or not expected:
            continue
        if index == 0 and raw_question.lower() == "question":
            continue  # header row

        # Cells are prefixed "Q1. ", "Q2. ", "Q10a. " etc. Use that as the id and
        # drop it from the prompt so the agent is not asked about a question number.
        numbered = re.match(r"^Q\s*(\d+[a-z]?)\s*[.):]\s*(.*)$", raw_question, re.DOTALL)
        if numbered:
            qid = f"q{numbered.group(1)}"
            question = numbered.group(2).strip()
        else:
            qid = f"row{index + 1}"  # distinct namespace, so it cannot collide with qN
            question = raw_question

        baseline = cells.get(baseline_col, "") if baseline_col else ""
        questions.append(
            Question(
                id=qid,
                question=question,
                expected=expected,
                baseline=baseline or None,
            )
        )
    return questions


def load(path: Path) -> list[Question]:
    questions = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        record = json.loads(line)
        try:
            expectations = normalize_expectations(record.get("expectations"))
        except ValueError as exc:
            raise ValueError(f"{record.get('id', '?')}: {exc}") from exc
        questions.append(
            Question(
                id=record["id"],
                question=record["question"],
                expected=record["expected"],
                expectations=expectations,
                baseline=record.get("baseline"),
                tags=record.get("tags", []),
                clarification_reply=record.get("clarification_reply"),
            )
        )
    _assert_unique_ids(questions)
    return questions


def save(questions: list[Question], path: Path) -> None:
    _assert_unique_ids(questions)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as handle:
        for question in questions:
            handle.write(json.dumps(question.to_json(), ensure_ascii=False) + "\n")


def _assert_unique_ids(questions: list[Question]) -> None:
    seen = set()
    for question in questions:
        if question.id in seen:
            raise ValueError(f"duplicate question id: {question.id}")
        seen.add(question.id)
