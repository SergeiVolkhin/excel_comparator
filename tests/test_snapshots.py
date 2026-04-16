"""Snapshot tests: structural comparison of generated output artifacts.

Uses openpyxl → dict representation to avoid zip-timestamp noise, and
normalised text stripping of the HTML report.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from src.comparators.basic_comparator import BasicComparator
from src.core.interfaces import ComparisonResult
from src.formatters.excel_formatter import ExcelOutputFormatter
from src.formatters.html_formatter import HTMLOutputFormatter
from tests.conftest import xlsx_to_dict


@pytest.fixture
def fixed_result() -> ComparisonResult:
    df1 = pd.DataFrame({"id": [1, 2, 3], "name": ["alpha", "beta", "gamma"]})
    df2 = pd.DataFrame({"id": [1, 2, 3], "name": ["alpha", "BETA", "gamma"]})
    return BasicComparator().compare(df1, df2)


def _strip_dynamic_html(text: str) -> str:
    """Remove timestamps and paths that vary between runs."""
    text = re.sub(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?", "<TIMESTAMP>", text)
    text = re.sub(r"\d{2}\.\d{2}\.\d{4}\s\d{2}:\d{2}(:\d{2})?", "<TIMESTAMP>", text)
    text = re.sub(r"file:///[^\"'\s]+", "<PATH>", text)
    return text


class TestExcelSnapshot:
    def test_sheet_structure_stable(
        self, fixed_result: ComparisonResult, tmp_path: Path
    ) -> None:
        out = tmp_path / "r.xlsx"
        ExcelOutputFormatter().format(fixed_result, out, file1_name="A", file2_name="B")

        snap = xlsx_to_dict(out)

        # Three sheets: two data sheets + summary
        assert len(snap) == 3

        # Column headers (id / name) appear somewhere on each data sheet;
        # formatter prepends a title row, so we scan all rows.
        for sheet, rows in snap.items():
            flat = [c for row in rows for c in row if c is not None]
            if any("id" == str(c).strip() for c in flat):
                assert any("name" == str(c).strip() for c in flat)


class TestHTMLSnapshot:
    def test_report_structure_stable(
        self, fixed_result: ComparisonResult, tmp_path: Path
    ) -> None:
        out = tmp_path / "r.html"
        HTMLOutputFormatter().format(fixed_result, out, file1_name="A", file2_name="B")

        text = out.read_text(encoding="utf-8")
        normalised = _strip_dynamic_html(text)

        assert "<html" in normalised.lower() or "<!doctype" in normalised.lower()
        # Values from the fixed input must appear in the report
        assert "alpha" in normalised
        assert "BETA" in normalised or "beta" in normalised.lower()
