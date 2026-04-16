"""Characterization tests for BasicComparator — freeze current behavior."""

from __future__ import annotations

import pandas as pd
import pytest

from src.comparators.basic_comparator import BasicComparator
from src.core.exceptions import ComparisonError
from src.core.interfaces import ComparisonResult


@pytest.fixture
def comp() -> BasicComparator:
    return BasicComparator()


@pytest.fixture
def df_base() -> pd.DataFrame:
    return pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})


class TestCompareHappyPaths:
    def test_identical_yields_zero_diffs(
        self, comp: BasicComparator, df_base: pd.DataFrame
    ) -> None:
        result = comp.compare(df_base, df_base.copy())
        assert isinstance(result, ComparisonResult)
        assert result.differences_mask.sum().sum() == 0
        assert result.metadata["similarity_percentage"] == 100.0
        assert result.metadata["total_cells"] == df_base.size
        assert result.metadata["shape"] == df_base.shape

    def test_one_cell_diff_detected(self, comp: BasicComparator, df_base: pd.DataFrame) -> None:
        df2 = df_base.copy()
        df2.loc[1, "a"] = 999
        result = comp.compare(df_base, df2)
        assert result.differences_mask.sum().sum() == 1
        assert bool(result.differences_mask.loc[1, "a"]) is True

    def test_all_cells_diff(self, comp: BasicComparator, df_base: pd.DataFrame) -> None:
        df2 = df_base.copy() * 0 if False else pd.DataFrame({"a": [9, 9, 9], "b": ["p", "p", "p"]})
        result = comp.compare(df_base, df2)
        assert result.differences_mask.sum().sum() == df_base.size
        assert result.metadata["similarity_percentage"] == 0.0


class TestCompareNaN:
    def test_nan_equals_nan(self, comp: BasicComparator) -> None:
        df1 = pd.DataFrame({"a": [1, None, 3]})
        df2 = pd.DataFrame({"a": [1, None, 3]})
        result = comp.compare(df1, df2)
        assert result.differences_mask.sum().sum() == 0

    def test_nan_vs_value_differs(self, comp: BasicComparator) -> None:
        df1 = pd.DataFrame({"a": [1, None, 3]})
        df2 = pd.DataFrame({"a": [1, 2, 3]})
        result = comp.compare(df1, df2)
        assert result.differences_mask.sum().sum() == 1

    def test_no_future_warning_on_object_columns(self, comp: BasicComparator) -> None:
        """Regression for TODO_bugs.md #2: fillna(object_sentinel) used to
        emit FutureWarning on object-dtype NaN handling. The new mask
        builder must not emit any warning."""
        import warnings

        df1 = pd.DataFrame({"s": ["a", None, "c"], "n": [1, None, 3]})
        df2 = pd.DataFrame({"s": ["a", None, "c"], "n": [1, None, 3]})
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            result = comp.compare(df1, df2)
        assert result.differences_mask.sum().sum() == 0


class TestCompareOptions:
    def test_ignore_case(self, comp: BasicComparator) -> None:
        df1 = pd.DataFrame({"x": ["Alpha", "Beta"]})
        df2 = pd.DataFrame({"x": ["alpha", "beta"]})
        result = comp.compare(df1, df2, ignore_case=True)
        assert result.differences_mask.sum().sum() == 0

    def test_ignore_case_preserves_numeric_columns(self, comp: BasicComparator) -> None:
        """Regression for TODO_bugs.md #3: ignore_case must skip numeric
        columns entirely; previously the preprocess mask used
        ``astype(str) != 'nan'`` which touched every cell."""
        df1 = pd.DataFrame({"n": [1, 2, 3], "s": ["A", "B", "C"]})
        df2 = pd.DataFrame({"n": [1, 2, 3], "s": ["a", "b", "c"]})
        preprocessed = comp._preprocess_dataframe(df1, ignore_case=True)
        assert preprocessed["n"].dtype == df1["n"].dtype
        assert list(preprocessed["n"]) == [1, 2, 3]

    def test_ignore_whitespace(self, comp: BasicComparator) -> None:
        df1 = pd.DataFrame({"x": [" a ", "b"]})
        df2 = pd.DataFrame({"x": ["a", "b"]})
        result = comp.compare(df1, df2, ignore_whitespace=True)
        assert result.differences_mask.sum().sum() == 0

    def test_options_stored_in_metadata(self, comp: BasicComparator, df_base: pd.DataFrame) -> None:
        result = comp.compare(df_base, df_base.copy(), ignore_case=True)
        assert result.metadata["comparison_options"] == {"ignore_case": True}


class TestCompareValidation:
    def test_shape_mismatch_raises(self, comp: BasicComparator) -> None:
        df1 = pd.DataFrame({"a": [1, 2]})
        df2 = pd.DataFrame({"a": [1, 2, 3]})
        with pytest.raises(ComparisonError, match="Размеры"):
            comp.compare(df1, df2)

    def test_columns_mismatch_raises(self, comp: BasicComparator) -> None:
        df1 = pd.DataFrame({"a": [1, 2]})
        df2 = pd.DataFrame({"b": [1, 2]})
        with pytest.raises(ComparisonError, match="столбцов"):
            comp.compare(df1, df2)

    def test_empty_raises(self, comp: BasicComparator) -> None:
        df = pd.DataFrame({"a": []})
        with pytest.raises(ComparisonError, match="пустой"):
            comp.compare(df, df.copy())


class TestGetDifferencesSummary:
    def test_summary_structure(self, comp: BasicComparator) -> None:
        df1 = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
        df2 = pd.DataFrame({"a": [1, 2, 9], "b": ["x", "Y", "Z"]})
        result = comp.compare(df1, df2)
        summary = comp.get_differences_summary(result)
        assert summary["total_different_cells"] == 3
        assert summary["rows_with_differences"] == 2
        assert summary["most_different_column"] == "b"
        assert "a" in summary["column_differences"]
        assert "b" in summary["column_differences"]


def test_get_name(comp: BasicComparator) -> None:
    assert comp.get_name() == "Базовое сравнение"
