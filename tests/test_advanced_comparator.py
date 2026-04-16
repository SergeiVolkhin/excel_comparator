"""Characterization tests for AdvancedComparator."""

from __future__ import annotations

import pandas as pd
import pytest

from src.comparators.advanced_comparator import AdvancedComparator
from src.core.exceptions import ComparisonError


@pytest.fixture
def comp() -> AdvancedComparator:
    return AdvancedComparator()


class TestCompareSameShape:
    def test_identical(self, comp: AdvancedComparator) -> None:
        df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
        result = comp.compare(df, df.copy())
        assert result.differences_mask.sum().sum() == 0
        assert result.metadata["similarity_percentage"] == 100.0

    def test_single_diff(self, comp: AdvancedComparator) -> None:
        df1 = pd.DataFrame({"a": [1, 2, 3]})
        df2 = pd.DataFrame({"a": [1, 9, 3]})
        result = comp.compare(df1, df2)
        assert result.differences_mask.sum().sum() == 1


class TestCompareDifferentRowCounts:
    def test_df1_longer(self, comp: AdvancedComparator) -> None:
        df1 = pd.DataFrame({"a": [1, 2, 3, 4]})
        df2 = pd.DataFrame({"a": [1, 2]})
        result = comp.compare(df1, df2)
        assert result.metadata["row_stats"]["only_in_df1"] == 2
        assert result.metadata["row_stats"]["common"] == 2
        assert result.metadata["shape"] == (4, 1)

    def test_df2_longer(self, comp: AdvancedComparator) -> None:
        df1 = pd.DataFrame({"a": [1, 2]})
        df2 = pd.DataFrame({"a": [1, 2, 3, 4]})
        result = comp.compare(df1, df2)
        assert result.metadata["row_stats"]["only_in_df2"] == 2


class TestCompareDifferentColumns:
    def test_common_cols_intersection(self, comp: AdvancedComparator) -> None:
        df1 = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
        df2 = pd.DataFrame({"a": [1, 2], "c": [9, 9]})
        result = comp.compare(df1, df2)
        col_stats = result.metadata["column_stats"]
        assert col_stats["common"] == ["a"]
        assert col_stats["only_in_df1"] == ["b"]
        assert col_stats["only_in_df2"] == ["c"]

    def test_no_common_columns_raises(self, comp: AdvancedComparator) -> None:
        df1 = pd.DataFrame({"a": [1]})
        df2 = pd.DataFrame({"b": [1]})
        with pytest.raises(ComparisonError, match="общих столбцов"):
            comp.compare(df1, df2)


class TestKeyColumns:
    def test_missing_key_column_raises(self, comp: AdvancedComparator) -> None:
        df1 = pd.DataFrame({"a": [1]})
        df2 = pd.DataFrame({"a": [1]})
        with pytest.raises(ComparisonError, match="Ключевые"):
            comp.compare(df1, df2, key_columns=["missing"])


class TestSummary:
    def test_summary_includes_structural(self, comp: AdvancedComparator) -> None:
        df1 = pd.DataFrame({"a": [1, 2, 3], "extra": [0, 0, 0]})
        df2 = pd.DataFrame({"a": [1, 9, 3]})
        result = comp.compare(df1, df2)
        summary = comp.get_differences_summary(result)
        assert summary["structural_differences"]["only_in_df1_columns"] == ["extra"]
        assert summary["total_different_cells"] == 1


def test_get_name(comp: AdvancedComparator) -> None:
    assert comp.get_name() == "Улучшенное сравнение"


class TestPreprocess:
    def test_ignore_case(self, comp: AdvancedComparator) -> None:
        df1 = pd.DataFrame({"x": ["ABC"]})
        df2 = pd.DataFrame({"x": ["abc"]})
        result = comp.compare(df1, df2, ignore_case=True)
        assert result.differences_mask.sum().sum() == 0

    def test_ignore_whitespace(self, comp: AdvancedComparator) -> None:
        df1 = pd.DataFrame({"x": [" abc "]})
        df2 = pd.DataFrame({"x": ["abc"]})
        result = comp.compare(df1, df2, ignore_whitespace=True)
        assert result.differences_mask.sum().sum() == 0


class TestEmptyAligned:
    def test_zero_rows_after_alignment(self, comp: AdvancedComparator) -> None:
        df1 = pd.DataFrame({"a": []})
        df2 = pd.DataFrame({"a": []})
        result = comp.compare(df1, df2)
        assert result.metadata["similarity_percentage"] == 0.0
