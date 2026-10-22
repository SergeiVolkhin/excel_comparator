"""Characterization tests for ExcelOutputFormatter and HTMLOutputFormatter."""

from __future__ import annotations

import gc
import logging
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from openpyxl import load_workbook

from src.comparators.advanced_comparator import AdvancedComparator
from src.comparators.basic_comparator import BasicComparator
from src.core.exceptions import ApplicationError
from src.core.interfaces import ComparisonResult
from src.formatters import excel_formatter
from src.formatters.excel_formatter import (
    COLUMN_WIDTH_SAMPLE_ROWS,
    EXCEL_LARGE_ROW_THRESHOLD,
    ExcelOutputFormatter,
)
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
            # Summary, the differences-only sheet, then the two data sheets
            # (file stems, possibly truncated)
            assert wb.sheetnames == ["Сводка", "Расхождения", "FileA", "FileB"]
        finally:
            wb.close()

    def test_supported_formats(self) -> None:
        assert ExcelOutputFormatter().get_supported_formats() == [".xlsx"]

    def test_different_row_counts_writes_na_as_empty(self, tmp_path: Path) -> None:
        # Advanced alignment pads the shorter frame with pd.NA, which openpyxl
        # cannot write ("Cannot convert <NA> to Excel"). The formatter must
        # turn those cells into empty (None) cells instead of crashing.
        df1 = pd.DataFrame({"id": [1, 2, 3], "name": ["a", "b", "c"]})
        df2 = pd.DataFrame({"id": [1, 2], "name": ["a", "b"]})
        result = AdvancedComparator().compare(df1, df2)

        out = tmp_path / "padded.xlsx"
        ExcelOutputFormatter().format(result, out, file1_name="A", file2_name="B")

        wb = load_workbook(out, read_only=True)
        try:
            sheet_b = wb["B"]  # the shorter file2 sheet, padded with NA
            # Header + 3 rows (padded to the longer frame's length).
            rows = list(sheet_b.iter_rows(values_only=True))
        finally:
            wb.close()
        # The 3rd data row was padding: its source cells (id, name) must be
        # empty (None), not <NA>. A trailing "Различия" column describes the diff.
        assert rows[3][0] is None
        assert rows[3][1] is None

    def test_column_width_samples_only_first_rows(self, tmp_path: Path) -> None:
        # A very long value placed BEYOND the sampled window must not widen
        # the column — proves _auto_adjust_columns no longer scans every row.
        n = COLUMN_WIDTH_SAMPLE_ROWS + 10
        names = ["a"] * n
        names[-1] = "X" * 100  # outside header + first COLUMN_WIDTH_SAMPLE_ROWS
        df = pd.DataFrame({"id": range(n), "name": names})
        result = BasicComparator().compare(df, df.copy())

        out = tmp_path / "wide.xlsx"
        ExcelOutputFormatter().format(result, out, file1_name="A", file2_name="B")

        wb = load_workbook(out)
        try:
            width_b = wb["A"].column_dimensions["B"].width  # the "name" column
        finally:
            wb.close()
        # Sampled width reflects "name"/"a" (~6). A full scan would cap at 50.
        assert width_b is not None
        assert width_b < 20

    def test_large_row_count_logs_html_suggestion(
        self, simple_result: ComparisonResult, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        simple_result.metadata["shape"] = (EXCEL_LARGE_ROW_THRESHOLD + 1, 2)
        out = tmp_path / "big.xlsx"
        with caplog.at_level(logging.WARNING, logger="ExcelOutputFormatter"):
            ExcelOutputFormatter().format(simple_result, out, file1_name="A", file2_name="B")
        assert any(".html" in r.message for r in caplog.records)


class TestRowMatchReport:
    """Summary blocks for comparisons made with ignore_row_order=True."""

    @pytest.fixture
    def unordered_result(self) -> ComparisonResult:
        df1 = pd.DataFrame({"id": ["a", "b", "c"], "sum": [1.5, 2.0, 3.25]})
        df2 = pd.DataFrame({"id": ["c", "a", "b"], "sum": [3.25, 1.5, 2.0]})
        return AdvancedComparator().compare(df1, df2, ignore_row_order=True)

    def test_excel_summary_has_row_match_block(
        self, unordered_result: ComparisonResult, tmp_path: Path
    ) -> None:
        out = tmp_path / "r.xlsx"
        ExcelOutputFormatter().format(unordered_result, out, file1_name="A", file2_name="B")
        wb = load_workbook(out, read_only=True)
        try:
            rows = [list(r) for r in wb["Сводка"].iter_rows(values_only=True)]
        finally:
            wb.close()
        labels = {row[0]: row[1] for row in rows if row and row[0]}
        assert "Сопоставление строк (без учёта порядка):" in labels
        assert labels["Итог:"] == "Совпадают"
        assert labels["Ключевые столбцы:"] == "вся строка"
        assert labels["Совпало строк:"] == 3
        assert labels["Порядок строк отличается:"] == "да"
        totals_row = next(row for row in rows if row[0] == "sum")
        assert totals_row[1:4] == [6.75, 6.75, 0]

    def test_excel_summary_unchanged_without_option(
        self, simple_result: ComparisonResult, tmp_path: Path
    ) -> None:
        out = tmp_path / "r.xlsx"
        ExcelOutputFormatter().format(simple_result, out, file1_name="A", file2_name="B")
        wb = load_workbook(out, read_only=True)
        try:
            cells = [c for r in wb["Сводка"].iter_rows(values_only=True) for c in r if c]
        finally:
            wb.close()
        assert "Сопоставление строк (без учёта порядка):" not in cells

    def test_html_has_row_match_cards(
        self, unordered_result: ComparisonResult, tmp_path: Path
    ) -> None:
        out = tmp_path / "r.html"
        HTMLOutputFormatter().format(unordered_result, out, file1_name="A", file2_name="B")
        content = out.read_text(encoding="utf-8")
        assert "Совпало строк" in content
        assert "Совпадают" in content


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


def _sheet_rows(path: Path, sheet: str) -> list[list[object]]:
    wb = load_workbook(path, read_only=True)
    try:
        return [list(r) for r in wb[sheet].iter_rows(values_only=True)]
    finally:
        wb.close()


class TestDifferencesSheet:
    """The «Расхождения» sheet lists only the rows with differences."""

    @pytest.fixture
    def similar_result(self) -> ComparisonResult:
        # «b» changed its sum, «d» exists only in file 2, the order differs.
        df1 = pd.DataFrame({"id": ["a", "b", "c"], "sum": [1.5, 2.0, 3.25]})
        df2 = pd.DataFrame({"id": ["c", "d", "a", "b"], "sum": [3.25, 9.0, 1.5, 2.5]})
        return AdvancedComparator().compare(df1, df2, ignore_row_order=True)

    def _format(self, result: ComparisonResult, tmp_path: Path, **options: object) -> Path:
        out = tmp_path / "r.xlsx"
        ExcelOutputFormatter().format(result, out, file1_name="A", file2_name="B", **options)
        return out

    def test_pair_takes_two_lines_and_only_row_one(
        self, similar_result: ComparisonResult, tmp_path: Path
    ) -> None:
        rows = _sheet_rows(self._format(similar_result, tmp_path), "Расхождения")
        assert rows == [
            ["№", "Статус", "Файл", "Строка в файле", "id", "sum", "Что изменилось"],
            # Source row numbers: header is row 1, so position + 2.
            [1, "Изменена (по сходству)", 1, 3, "b", 2, "sum: 2 → 2.5 (+0.5)"],
            [1, "Изменена (по сходству)", 2, 5, "b", 2.5, None],
            [2, "Только в файле 2", 2, 3, "d", 9, None],
        ]

    def test_only_changed_cells_are_highlighted(
        self, similar_result: ComparisonResult, tmp_path: Path
    ) -> None:
        wb = load_workbook(self._format(similar_result, tmp_path))
        try:
            sheet = wb["Расхождения"]
            for row in (2, 3):  # both lines of the pair
                # ARGB; the alpha byte differs between writers, the colour must not
                assert sheet.cell(row=row, column=6).fill.fgColor.rgb[-6:] == "FFFF00"  # sum
                assert sheet.cell(row=row, column=5).fill.fill_type is None  # id
            assert sheet.cell(row=4, column=6).fill.fill_type is None  # only in file 2
            assert sheet.freeze_panes == "A2"
        finally:
            wb.close()

    def test_first_data_row_option_shifts_row_numbers(
        self, similar_result: ComparisonResult, tmp_path: Path
    ) -> None:
        rows = _sheet_rows(self._format(similar_result, tmp_path, first_data_row=5), "Расхождения")
        assert [row[3] for row in rows[1:]] == [6, 8, 6]

    def test_data_sheets_describe_file1_to_file2(
        self, similar_result: ComparisonResult, tmp_path: Path
    ) -> None:
        out = self._format(similar_result, tmp_path)
        for sheet in ("A", "B"):
            rows = _sheet_rows(out, sheet)
            assert rows[2][2] == "sum: 2 → 2.5 (+0.5)"  # the same direction on both sheets
            assert rows[4][2] == "Только в файле 2"  # not «NULL → d | NULL → 9»

    def test_no_differences(self, tmp_path: Path) -> None:
        df = pd.DataFrame({"id": [1, 2], "name": ["a", "b"]})
        rows = _sheet_rows(
            self._format(BasicComparator().compare(df, df.copy()), tmp_path), "Расхождения"
        )
        assert len(rows) == 2
        assert rows[1][1] == "Расхождений нет"

    def test_positional_comparison(self, simple_result: ComparisonResult, tmp_path: Path) -> None:
        rows = _sheet_rows(self._format(simple_result, tmp_path), "Расхождения")
        assert rows[1:] == [
            [1, "Изменена", 1, 3, 2, "b", "name: b → B"],
            [1, "Изменена", 2, 3, 2, "B", None],
        ]

    def test_key_pair_label(self, tmp_path: Path) -> None:
        df1 = pd.DataFrame({"id": ["a", "b"], "sum": [1.0, 2.0]})
        df2 = pd.DataFrame({"id": ["b", "a"], "sum": [2.5, 1.0]})
        result = AdvancedComparator().compare(df1, df2, ignore_row_order=True, key_columns=["id"])
        rows = _sheet_rows(self._format(result, tmp_path), "Расхождения")
        assert rows[1][1] == "Изменена (по ключу)"

    def test_item_limit_adds_a_note(
        self,
        similar_result: ComparisonResult,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(excel_formatter, "DIFFERENCES_SHEET_MAX_ITEMS", 1)
        rows = _sheet_rows(self._format(similar_result, tmp_path), "Расхождения")
        assert len(rows) == 4  # header, the pair (two lines), the note
        assert str(rows[3][1]).startswith("Показаны первые 1 расхождений из 2")

    def test_summary_row_match_block(
        self, similar_result: ComparisonResult, tmp_path: Path
    ) -> None:
        rows = _sheet_rows(self._format(similar_result, tmp_path), "Сводка")
        labels = {row[0]: row[1] for row in rows if row and row[0]}
        assert labels["Изменённые строки (пара найдена):"] == 1
        assert labels["из них по сходству:"] == 1
        assert str(labels["Примечание:"]).startswith("Пары найдены по совпадению")
        assert labels["Только в файле 2:"] == 1

    def test_similarity_is_rounded_down(
        self, simple_result: ComparisonResult, tmp_path: Path
    ) -> None:
        # 99.9999 % must not be shown as 100.00 % while there are differences.
        simple_result.metadata["similarity_percentage"] = 99.9999
        rows = _sheet_rows(self._format(simple_result, tmp_path), "Сводка")
        labels = {row[0]: row[1] for row in rows if row and row[0]}
        assert labels["Процент схожести:"] == "99.99%"

    def test_html_row_match_cards_show_similar(
        self, similar_result: ComparisonResult, tmp_path: Path
    ) -> None:
        out = tmp_path / "r.html"
        HTMLOutputFormatter().format(similar_result, out, file1_name="A", file2_name="B")
        content = out.read_text(encoding="utf-8")
        assert "Изменённые строки (пара найдена)" in content
        assert "из них по сходству" in content


class TestReportWriting:
    """XlsxWriter-based writing: thresholds, progress, names, cell types."""

    @staticmethod
    def _sheets(path: Path) -> list[str]:
        wb = load_workbook(path, read_only=True)
        try:
            return list(wb.sheetnames)
        finally:
            wb.close()

    def test_large_table_skips_full_data_sheets(
        self,
        simple_result: ComparisonResult,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(excel_formatter, "DATA_SHEETS_MAX_ROWS", 2)  # 3 rows > 2
        out = tmp_path / "r.xlsx"
        ExcelOutputFormatter().format(simple_result, out, file1_name="A", file2_name="B")
        assert self._sheets(out) == ["Сводка", "Расхождения"]
        labels = {row[0]: row[1] for row in _sheet_rows(out, "Сводка") if row and row[0]}
        assert str(labels["Полные листы данных:"]).startswith("не записаны: 3 строк больше 2")
        # The differences sheet still lists the changed row
        assert _sheet_rows(out, "Расхождения")[1][-1] == "name: b → B"

    def test_full_data_sheets_option_forces_them(
        self,
        simple_result: ComparisonResult,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(excel_formatter, "DATA_SHEETS_MAX_ROWS", 2)
        out = tmp_path / "r.xlsx"
        ExcelOutputFormatter().format(
            simple_result, out, file1_name="A", file2_name="B", full_data_sheets=True
        )
        assert self._sheets(out) == ["Сводка", "Расхождения", "A", "B"]
        labels = {row[0] for row in _sheet_rows(out, "Сводка") if row and row[0]}
        assert "Полные листы данных:" not in labels

    def test_progress_goes_forward_to_the_end(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(excel_formatter, "PROGRESS_CHUNK_ROWS", 2)
        df1 = pd.DataFrame({"id": range(7), "v": range(7)})
        df2 = df1.assign(v=[0, 1, 2, 30, 4, 5, 60])
        calls: list[tuple[float, str]] = []
        ExcelOutputFormatter().format(
            BasicComparator().compare(df1, df2),
            tmp_path / "r.xlsx",
            progress=lambda share, message: calls.append((share, message)),
        )
        shares = [share for share, _ in calls]
        assert shares == sorted(shares)
        assert shares[-1] == 1.0
        assert len(calls) > 4  # row chunks of the sheets, not just start and end
        assert any("из 7 строк" in message for _, message in calls)

    @pytest.mark.parametrize(
        ("name1", "name2", "expected"),
        [
            ("data", "data", ["data", "data (2)"]),
            ("DATA", "data", ["DATA", "data (2)"]),
            ("a[1]:b", "c*?/d", ["a_1__b", "c___d"]),
            ("Сводка", "Расхождения", ["Сводка (2)", "Расхождения (2)"]),
            ("x" * 40, "x" * 40, ["x" * 30, "x" * 26 + " (2)"]),
        ],
    )
    def test_sheet_names_are_valid_and_unique(
        self,
        simple_result: ComparisonResult,
        tmp_path: Path,
        name1: str,
        name2: str,
        expected: list[str],
    ) -> None:
        out = tmp_path / "r.xlsx"
        ExcelOutputFormatter().format(simple_result, out, file1_name=name1, file2_name=name2)
        assert self._sheets(out)[2:] == expected

    def test_cell_values_keep_their_type(self, tmp_path: Path) -> None:
        df = pd.DataFrame(
            {
                "text": ["=1+1", "http://example.com"],
                "day": pd.to_datetime(["2026-09-01", "2026-09-02"]),
                "moment": pd.to_datetime(["2026-09-01 12:30", None]),
                "n": [1.5, None],
            }
        )
        out = tmp_path / "r.xlsx"
        ExcelOutputFormatter().format(BasicComparator().compare(df, df.copy()), out)
        wb = load_workbook(out)
        try:
            sheet = wb["Файл 1"]
            assert sheet["A2"].value == "=1+1"  # text, not a formula
            assert sheet["A2"].data_type == "s"
            assert sheet["A3"].value == "http://example.com"
            assert sheet["A3"].hyperlink is None
            assert sheet["B2"].value == datetime(2026, 9, 1)
            assert sheet["B2"].number_format == "yyyy-mm-dd"
            assert sheet["C2"].number_format == "yyyy-mm-dd hh:mm:ss"
            assert sheet["C3"].value is None  # NaT
            assert sheet["D3"].value is None  # NaN
        finally:
            wb.close()

    def test_failure_leaves_no_half_written_report(
        self,
        simple_result: ComparisonResult,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def boom(*args: object, **kwargs: object) -> None:
            raise RuntimeError("disk full")

        temp_files: list[str] = []
        real_mkstemp = tempfile.mkstemp

        def recording_mkstemp(*args: Any, **kwargs: Any) -> tuple[int, str]:
            descriptor, name = real_mkstemp(*args, **kwargs)
            temp_files.append(name)
            return descriptor, name

        monkeypatch.setattr(tempfile, "mkstemp", recording_mkstemp)
        monkeypatch.setattr(ExcelOutputFormatter, "_write_differences_sheet", boom)
        out = tmp_path / "r.xlsx"
        with pytest.raises(ApplicationError, match="disk full"):
            ExcelOutputFormatter().format(simple_result, out)
        gc.collect()  # XlsxWriter would close (and write) the workbook here
        assert not out.exists()
        # constant_memory row files of the sheets written so far are gone too
        assert temp_files
        assert not any(Path(name).exists() for name in temp_files)
