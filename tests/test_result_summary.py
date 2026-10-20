"""Tests for the GUI result summary helpers (src/core/result_summary.py)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from src.comparators.advanced_comparator import AdvancedComparator
from src.core.result_summary import human_size, next_free_path, summarize

NBSP = " "


def _row_match(**overrides: Any) -> dict[str, Any]:
    row_match: dict[str, Any] = {
        "key_columns": [],
        "rows_file1": 1967,
        "rows_file2": 1967,
        "matched": 1967,
        "equal": 1967,
        "modified": 0,
        "only_in_file1": 0,
        "only_in_file2": 0,
        "order_changed": True,
        "identical": True,
    }
    row_match.update(overrides)
    return row_match


class TestRowSummary:
    def test_identical(self) -> None:
        summary = summarize({"row_match": _row_match()})
        assert summary.ok is True
        assert summary.headline == "Данные совпадают"
        assert summary.details == f"Совпало строк: 1{NBSP}967 из 1{NBSP}967 · порядок строк другой"

    def test_identical_same_order(self) -> None:
        summary = summarize({"row_match": _row_match(order_changed=False)})
        assert "порядок" not in summary.details

    def test_differences_with_keys(self) -> None:
        row_match = _row_match(
            key_columns=["dt", "idUser"], equal=1966, modified=1, identical=False
        )
        summary = summarize({"row_match": row_match})
        assert summary.ok is False
        assert summary.headline == "Есть расхождения"
        assert summary.details == (
            f"Совпало строк: 1{NBSP}966 · с отличиями: 1 · только в первом: 0 · только во втором: 0"
        )

    def test_differences_without_keys_skip_modified(self) -> None:
        row_match = _row_match(equal=1966, only_in_file1=1, only_in_file2=1, identical=False)
        summary = summarize({"row_match": row_match})
        assert "с отличиями" not in summary.details
        assert "только в первом: 1" in summary.details

    def test_real_comparison_metadata(self) -> None:
        df1 = pd.DataFrame({"id": [1, 2, 3], "v": [10, 20, 30]})
        df2 = pd.DataFrame({"id": [3, 1, 2], "v": [30, 10, 20]})
        result = AdvancedComparator().compare(df1, df2, ignore_row_order=True)
        assert summarize(result.metadata).ok is True


class TestCellSummary:
    def test_no_differences(self) -> None:
        summary = summarize({"total_cells": 17703, "different_cells": 0})
        assert summary.ok is True
        assert summary.headline == "Файлы совпадают"
        assert summary.details == f"Сравнено ячеек: 17{NBSP}703"

    def test_one_cell_never_shows_100_percent(self) -> None:
        metadata = {"total_cells": 63909, "different_cells": 1, "similarity_percentage": 99.9984}
        summary = summarize(metadata)
        assert summary.ok is False
        assert summary.details == f"Различается ячеек: 1 из 63{NBSP}909 · схожесть 99,99 %"


class TestNextFreePath:
    def test_free_name(self, tmp_path: Path) -> None:
        assert next_free_path(tmp_path) == tmp_path / "Сравнение.xlsx"

    def test_existing_names_are_skipped(self, tmp_path: Path) -> None:
        (tmp_path / "Сравнение.xlsx").write_bytes(b"")
        (tmp_path / "Сравнение (2).xlsx").write_bytes(b"")
        assert next_free_path(tmp_path) == tmp_path / "Сравнение (3).xlsx"

    def test_custom_name(self, tmp_path: Path) -> None:
        (tmp_path / "diff.html").write_bytes(b"")
        assert next_free_path(tmp_path, "diff.html") == tmp_path / "diff (2).html"


class TestHumanSize:
    @pytest.mark.parametrize(
        ("size", "expected"),
        [
            (0, "0 Б"),
            (512, "512 Б"),
            (96620, "94 КБ"),
            (1572864, "1,5 МБ"),
            (157286400, "150 МБ"),
            (3 * 1024**3, "3,0 ГБ"),
        ],
    )
    def test_sizes(self, size: int, expected: str) -> None:
        assert human_size(size) == expected
