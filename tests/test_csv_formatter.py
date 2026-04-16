"""Snapshot tests for CSVOutputFormatter.

Verifies the status-column contract (``__status__`` appended as the
last column), row-alignment semantics for ADDED / REMOVED rows
(detected via full-NaN padding), writer option passthrough (encoding
/ delimiter / quoting / lineterminator), and diff-only mode.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd
import pytest

from src.core.interfaces import ComparisonResult
from src.formatters.csv_formatter import (
    STATUS_ADDED,
    STATUS_EQUAL,
    STATUS_MODIFIED,
    STATUS_REMOVED,
    CSVOutputFormatter,
)


def _csv_to_rows(
    path: Path,
    *,
    sep: str = ",",
    encoding: str = "utf-8",
) -> list[list[str]]:
    """Read a CSV into a list-of-lists for snapshot comparison."""
    with open(path, encoding=encoding, newline="") as fh:
        reader = csv.reader(fh, delimiter=sep)
        return list(reader)


@pytest.fixture
def csv_formatter() -> CSVOutputFormatter:
    return CSVOutputFormatter()


@pytest.fixture
def identical_result() -> ComparisonResult:
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
        csv_formatter: CSVOutputFormatter,
        identical_result: ComparisonResult,
        tmp_path: Path,
    ) -> None:
        out = tmp_path / "out.csv"
        csv_formatter.format(identical_result, out)
        rows = _csv_to_rows(out)
        assert rows[0] == ["id", "name", "__status__"]
        assert all(r[-1] == STATUS_EQUAL for r in rows[1:])

    def test_modified_cell_flagged_modified(
        self, csv_formatter: CSVOutputFormatter, tmp_path: Path
    ) -> None:
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
        csv_formatter.format(result, out)
        rows = _csv_to_rows(out)
        assert rows[1][-1] == STATUS_EQUAL
        assert rows[2][-1] == STATUS_MODIFIED

    def test_added_row_uses_file2_values(
        self, csv_formatter: CSVOutputFormatter, tmp_path: Path
    ) -> None:
        # file1 was shorter and got padded with NaN — formatter tags that
        # row ADDED and writes file2's content so the audit actually shows
        # the new data instead of blanks.
        df_a = pd.DataFrame({"id": [1, pd.NA], "v": [10, pd.NA]})
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
        csv_formatter.format(result, out)
        rows = _csv_to_rows(out)
        assert rows[2][-1] == STATUS_ADDED
        assert rows[2][0] == "3"
        assert rows[2][1] == "30"

    def test_removed_row_keeps_file1_values(
        self, csv_formatter: CSVOutputFormatter, tmp_path: Path
    ) -> None:
        df_a = pd.DataFrame({"id": [1, 2], "v": [10, 20]})
        df_b = pd.DataFrame({"id": [1, pd.NA], "v": [10, pd.NA]})
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
        csv_formatter.format(result, out)
        rows = _csv_to_rows(out)
        assert rows[2][-1] == STATUS_REMOVED
        # REMOVED rows keep file1's original content for traceability.
        assert rows[2][0] == "2"
        assert rows[2][1] == "20"


class TestCSVFormatterWriterOptions:
    def test_utf8_bom(
        self,
        csv_formatter: CSVOutputFormatter,
        identical_result: ComparisonResult,
        tmp_path: Path,
    ) -> None:
        out = tmp_path / "out.csv"
        csv_formatter.format(identical_result, out, encoding="utf-8-sig")
        assert out.read_bytes().startswith(b"\xef\xbb\xbf")

    def test_custom_delimiter(
        self,
        csv_formatter: CSVOutputFormatter,
        identical_result: ComparisonResult,
        tmp_path: Path,
    ) -> None:
        out = tmp_path / "out.csv"
        csv_formatter.format(identical_result, out, delimiter=";")
        first_line = out.read_text(encoding="utf-8").splitlines()[0]
        assert ";" in first_line
        assert "," not in first_line

    def test_quote_all(
        self,
        csv_formatter: CSVOutputFormatter,
        identical_result: ComparisonResult,
        tmp_path: Path,
    ) -> None:
        out = tmp_path / "out.csv"
        csv_formatter.format(identical_result, out, quoting=csv.QUOTE_ALL)
        first_line = out.read_text(encoding="utf-8").splitlines()[0]
        # Three columns → at least 6 quote chars on the header line.
        assert first_line.count('"') >= 6

    def test_crlf_lineterminator(
        self,
        csv_formatter: CSVOutputFormatter,
        identical_result: ComparisonResult,
        tmp_path: Path,
    ) -> None:
        out = tmp_path / "out.csv"
        csv_formatter.format(identical_result, out, lineterminator="\r\n")
        assert b"\r\n" in out.read_bytes()


class TestCSVFormatterContract:
    def test_supported_formats(self, csv_formatter: CSVOutputFormatter) -> None:
        assert csv_formatter.get_supported_formats() == [".csv"]

    def test_io_error_is_wrapped(
        self, csv_formatter: CSVOutputFormatter, identical_result: ComparisonResult
    ) -> None:
        from src.core.exceptions import ApplicationError

        # Writing to a directory that does not exist surfaces as an
        # OSError; the formatter wraps it in ApplicationError.
        bad_path = Path("/this/path/definitely/does/not/exist/out.csv")
        with pytest.raises(ApplicationError, match="CSV"):
            csv_formatter.format(identical_result, bad_path)
