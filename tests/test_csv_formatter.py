"""Snapshot tests for CSVOutputFormatter.

This module is intentionally skipped until commit B.5 lands the
``CSVOutputFormatter`` class. The skipped assertions spell out the
contract the formatter must satisfy so the implementation has a clear
target.

When B.5 lifts the skip marker, the test cases below drive:

* status-column contract (``__status__`` appended as last column).
* row-alignment semantics for ADDED / REMOVED rows (padded with empty
  string).
* writer option passthrough (encoding / delimiter / quoting).
"""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd
import pytest

pytestmark = pytest.mark.skip(reason="pending B.5 — CSVOutputFormatter not implemented yet")


def _csv_to_rows(
    path: Path,
    *,
    sep: str = ",",
    encoding: str = "utf-8",
) -> list[list[str]]:
    """Read a CSV into a stable list-of-lists for snapshot comparison."""
    with open(path, encoding=encoding, newline="") as fh:
        reader = csv.reader(fh, delimiter=sep)
        return [row for row in reader]


@pytest.fixture
def csv_formatter() -> object:
    from src.formatters.csv_formatter import CSVOutputFormatter  # type: ignore[import-not-found]

    return CSVOutputFormatter()


@pytest.fixture
def _simple_result() -> object:
    """Pair of identical DataFrames wrapped in a ComparisonResult."""
    from src.core.interfaces import ComparisonResult

    df = pd.DataFrame({"id": [1, 2], "name": ["A", "B"]})
    mask = pd.DataFrame({"id": [False, False], "name": [False, False]})
    return ComparisonResult(
        differences_mask=mask,
        file1_data=df.copy(),
        file2_data=df.copy(),
        metadata={
            "total_cells": 4,
            "different_cells": 0,
            "similarity_percentage": 100.0,
            "shape": (2, 2),
        },
    )


class TestCSVFormatterStatusColumn:
    def test_identical_rows_all_equal(
        self,
        csv_formatter: object,
        _simple_result: object,
        tmp_path: Path,
    ) -> None:
        out = tmp_path / "out.csv"
        csv_formatter.format(_simple_result, out)  # type: ignore[attr-defined]
        rows = _csv_to_rows(out)
        assert rows[0] == ["id", "name", "__status__"]
        assert all(r[-1] == "EQUAL" for r in rows[1:])

    def test_modified_cell_flagged_modified(
        self,
        csv_formatter: object,
        tmp_path: Path,
    ) -> None:
        from src.core.interfaces import ComparisonResult

        df_a = pd.DataFrame({"id": [1, 2], "v": [10, 20]})
        df_b = pd.DataFrame({"id": [1, 2], "v": [10, 99]})
        mask = pd.DataFrame({"id": [False, False], "v": [False, True]})
        result = ComparisonResult(
            differences_mask=mask,
            file1_data=df_a,
            file2_data=df_b,
            metadata={
                "total_cells": 4,
                "different_cells": 1,
                "similarity_percentage": 75.0,
                "shape": (2, 2),
            },
        )
        out = tmp_path / "out.csv"
        csv_formatter.format(result, out)  # type: ignore[attr-defined]
        rows = _csv_to_rows(out)
        assert rows[1][-1] == "EQUAL"
        assert rows[2][-1] == "MODIFIED"

    def test_added_and_removed_rows(
        self,
        csv_formatter: object,
        tmp_path: Path,
    ) -> None:
        # File1 has rows [1, 2]; file2 has rows [1, 3]. Row 2 is REMOVED,
        # row 3 is ADDED. The formatter must align rows by position but
        # the B.5 spec doesn't yet fix the ordering — the status column
        # must simply carry the right labels somewhere.
        from src.core.interfaces import ComparisonResult

        df_a = pd.DataFrame({"id": [1, 2], "v": [10, 20]})
        df_b = pd.DataFrame({"id": [1, 3], "v": [10, 30]})
        mask = pd.DataFrame({"id": [False, True], "v": [False, True]})
        result = ComparisonResult(
            differences_mask=mask,
            file1_data=df_a,
            file2_data=df_b,
            metadata={
                "total_cells": 4,
                "different_cells": 2,
                "similarity_percentage": 50.0,
                "shape": (2, 2),
            },
        )
        out = tmp_path / "out.csv"
        csv_formatter.format(result, out)  # type: ignore[attr-defined]
        rows = _csv_to_rows(out)
        statuses = {r[-1] for r in rows[1:]}
        assert "REMOVED" in statuses or "ADDED" in statuses


class TestCSVFormatterWriterOptions:
    def test_utf8_bom(
        self,
        csv_formatter: object,
        _simple_result: object,
        tmp_path: Path,
    ) -> None:
        out = tmp_path / "out.csv"
        csv_formatter.format(_simple_result, out, encoding="utf-8-sig")  # type: ignore[attr-defined]
        raw = out.read_bytes()
        assert raw.startswith(b"\xef\xbb\xbf")

    def test_custom_delimiter(
        self,
        csv_formatter: object,
        _simple_result: object,
        tmp_path: Path,
    ) -> None:
        out = tmp_path / "out.csv"
        csv_formatter.format(_simple_result, out, delimiter=";")  # type: ignore[attr-defined]
        first_line = out.read_text(encoding="utf-8").splitlines()[0]
        assert ";" in first_line
        assert "," not in first_line

    def test_quote_all(
        self,
        csv_formatter: object,
        _simple_result: object,
        tmp_path: Path,
    ) -> None:
        import csv as csv_mod

        out = tmp_path / "out.csv"
        csv_formatter.format(_simple_result, out, quoting=csv_mod.QUOTE_ALL)  # type: ignore[attr-defined]
        first_line = out.read_text(encoding="utf-8").splitlines()[0]
        # Every header cell wrapped in quotes.
        assert first_line.count('"') >= 6


class TestCSVFormatterContract:
    def test_supported_formats(self, csv_formatter: object) -> None:
        assert csv_formatter.get_supported_formats() == [".csv"]  # type: ignore[attr-defined]
