"""Characterization tests for ExcelOutputFormatter and HTMLOutputFormatter."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from openpyxl import load_workbook

from src.comparators.basic_comparator import BasicComparator
from src.core.interfaces import ComparisonResult
from src.formatters.excel_formatter import ExcelOutputFormatter
from src.formatters.html_formatter import HTMLOutputFormatter


@pytest.fixture
def simple_result() -> ComparisonResult:
    df1 = pd.DataFrame({"id": [1, 2, 3], "name": ["a", "b", "c"]})
    df2 = pd.DataFrame({"id": [1, 2, 3], "name": ["a", "B", "c"]})
    return BasicComparator().compare(df1, df2)


class TestExcelFormatter:
    def test_format_writes_xlsx(self, simple_result: ComparisonResult, tmp_path: Path) -> None:
        out = tmp_path / "r.xlsx"
        ExcelOutputFormatter().format(simple_result, out, file1_name="A", file2_name="B")
        assert out.exists() and out.stat().st_size > 0

    def test_format_produces_expected_sheets(
        self, simple_result: ComparisonResult, tmp_path: Path
    ) -> None:
        out = tmp_path / "r.xlsx"
        ExcelOutputFormatter().format(simple_result, out, file1_name="FileA", file2_name="FileB")
        wb = load_workbook(out, read_only=True)
        try:
            # Two data sheets (file stems, possibly truncated) + a summary sheet
            assert len(wb.sheetnames) == 3
        finally:
            wb.close()

    def test_supported_formats(self) -> None:
        assert ExcelOutputFormatter().get_supported_formats() == [".xlsx"]


class TestHTMLFormatter:
    def test_format_writes_html(self, simple_result: ComparisonResult, tmp_path: Path) -> None:
        out = tmp_path / "r.html"
        HTMLOutputFormatter().format(simple_result, out, file1_name="A", file2_name="B")
        assert out.exists()
        content = out.read_text(encoding="utf-8")
        assert "<html" in content.lower() or "<!doctype" in content.lower()

    def test_supported_formats(self) -> None:
        fmts = HTMLOutputFormatter().get_supported_formats()
        assert ".html" in fmts or ".htm" in fmts

    def test_paginated_report(self, tmp_path: Path) -> None:
        # Force pagination by lowering the page_size to a tiny value.
        formatter = HTMLOutputFormatter()
        formatter.page_size = 10
        df1 = pd.DataFrame({"a": list(range(25))})
        df2 = pd.DataFrame({"a": list(range(25))})
        result = BasicComparator().compare(df1, df2)
        out = tmp_path / "r.html"
        formatter.format(result, out, file1_name="A", file2_name="B")
        # Pagination creates sibling page_*.html files
        pages = list(tmp_path.glob("r_page_*.html"))
        assert len(pages) >= 2
        assert out.exists()
