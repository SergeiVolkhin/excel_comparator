"""Plain-language summary of a comparison for the GUI result panel.

Turns ``ComparisonResult.metadata`` into a verdict plus one line of numbers,
picks a report file name that never overwrites an earlier report, and
formats file sizes for the file cards.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: Default report name; the report is saved next to the first compared file.
DEFAULT_REPORT_NAME = "Сравнение.xlsx"

#: Separator between the numbers in the details line.
_SEPARATOR = " · "


@dataclass(frozen=True)
class ResultSummary:
    """Verdict of a comparison: ``ok`` drives the colour of the result panel."""

    ok: bool
    headline: str
    details: str


def summarize(metadata: dict[str, Any]) -> ResultSummary:
    """Build the verdict from comparator metadata.

    With ``row_match`` (comparison without regard to row order) the verdict is
    about rows; otherwise it is about differing cells of a positional
    comparison.
    """
    row_match = metadata.get("row_match")
    if row_match:
        return _summarize_rows(row_match)
    return _summarize_cells(metadata)


def _summarize_rows(row_match: dict[str, Any]) -> ResultSummary:
    equal = _number(row_match["equal"])
    if row_match["identical"]:
        parts = [f"Совпало строк: {equal} из {_number(row_match['rows_file1'])}"]
        if row_match["order_changed"]:
            parts.append("порядок строк другой")
        return ResultSummary(True, "Данные совпадают", _SEPARATOR.join(parts))

    parts = [f"Совпало строк: {equal}"]
    if row_match["key_columns"] or row_match["modified"]:
        parts.append(f"с отличиями: {_number(row_match['modified'])}")
    parts.append(f"только в первом: {_number(row_match['only_in_file1'])}")
    parts.append(f"только во втором: {_number(row_match['only_in_file2'])}")
    return ResultSummary(False, "Есть расхождения", _SEPARATOR.join(parts))


def _summarize_cells(metadata: dict[str, Any]) -> ResultSummary:
    total = int(metadata.get("total_cells", 0))
    different = int(metadata.get("different_cells", 0))
    if different == 0:
        return ResultSummary(True, "Файлы совпадают", f"Сравнено ячеек: {_number(total)}")

    # Round down: a single differing cell among tens of thousands must not
    # show up as "100,00 %".
    similarity = math.floor(float(metadata.get("similarity_percentage", 0.0)) * 100) / 100
    details = (
        f"Различается ячеек: {_number(different)} из {_number(total)}"
        f"{_SEPARATOR}схожесть {f'{similarity:.2f}'.replace('.', ',')} %"
    )
    return ResultSummary(False, "Есть расхождения", details)


def next_free_path(folder: Path, name: str = DEFAULT_REPORT_NAME) -> Path:
    """``folder / name``, or ``name (2)``, ``name (3)``… if that file already exists."""
    candidate = folder / name
    stem, suffix = candidate.stem, candidate.suffix
    number = 2
    while candidate.exists():
        candidate = folder / f"{stem} ({number}){suffix}"
        number += 1
    return candidate


def human_size(size: int) -> str:
    """File size the way Explorer shows it: ``512 Б``, ``94 КБ``, ``1,5 МБ``."""
    value = float(size)
    unit = "Б"
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if value < 1024 or unit == "ГБ":
            break
        value /= 1024
    if unit in ("Б", "КБ") or value >= 100:
        return f"{value:.0f} {unit}"
    return f"{value:.1f}".replace(".", ",") + f" {unit}"


def _number(value: Any) -> str:
    """Digits grouped by thousands with a non-breaking space: ``1 967``."""
    return f"{int(value):,}".replace(",", " ")
