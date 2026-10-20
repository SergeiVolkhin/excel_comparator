"""Tests for order-independent row matching (src/comparators/row_matching.py)."""

from __future__ import annotations

import math
from datetime import date, datetime

import numpy as np
import pandas as pd
import pytest

from src.comparators.row_matching import align_unordered, parse_key_columns
from src.core.exceptions import ComparisonError


@pytest.fixture
def df_base() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "dt": ["2026-09-01", "2026-09-01", "2026-09-02"],
            "idUser": ["101", "102", "101"],
            "Sum_bets": [8000.0, 1300.5, 42.25],
        }
    )


class TestRowOrder:
    def test_identical_order(self, df_base: pd.DataFrame) -> None:
        alignment = align_unordered(df_base, df_base.copy(), list(df_base.columns))
        match = alignment.row_match
        assert alignment.differences_mask.sum().sum() == 0
        assert match["matched"] == 3
        assert match["identical"] is True
        assert match["order_changed"] is False

    def test_shuffled_rows_are_equal(self, df_base: pd.DataFrame) -> None:
        shuffled = df_base.iloc[[2, 0, 1]].reset_index(drop=True)
        alignment = align_unordered(df_base, shuffled, list(df_base.columns))
        match = alignment.row_match
        assert alignment.differences_mask.sum().sum() == 0
        assert match["equal"] == 3
        assert match["only_in_file1"] == 0
        assert match["only_in_file2"] == 0
        assert match["order_changed"] is True
        assert match["identical"] is True

    def test_aligned_rows_follow_file1_order(self, df_base: pd.DataFrame) -> None:
        shuffled = df_base.iloc[[2, 0, 1]].reset_index(drop=True)
        alignment = align_unordered(df_base, shuffled, list(df_base.columns))
        pd.testing.assert_frame_equal(alignment.file1_data, df_base)
        pd.testing.assert_frame_equal(alignment.file2_data, df_base)


class TestUnmatchedRows:
    def test_duplicates_pair_once(self) -> None:
        df1 = pd.DataFrame({"a": [1, 1, 2]})
        df2 = pd.DataFrame({"a": [1, 2]})
        match = align_unordered(df1, df2, ["a"]).row_match
        assert match["matched"] == 2
        assert match["only_in_file1"] == 1
        assert match["only_in_file2"] == 0
        assert match["identical"] is False

    def test_row_only_in_file2_is_appended_with_padding(self) -> None:
        df1 = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
        df2 = pd.DataFrame({"a": [2, 3, 1], "b": ["y", "z", "x"]})
        alignment = align_unordered(df1, df2, ["a", "b"])
        assert alignment.row_match["only_in_file2"] == 1
        assert alignment.file1_data.shape == (3, 2)
        # The extra file-2 row comes last; the file-1 side is an all-NA pad.
        assert alignment.file1_data.iloc[2].isna().all()
        assert alignment.file2_data.iloc[2].tolist() == [3, "z"]
        assert alignment.differences_mask.iloc[2].all()
        assert not alignment.differences_mask.iloc[:2].to_numpy().any()

    def test_changed_value_without_keys_is_two_unmatched_rows(self, df_base: pd.DataFrame) -> None:
        changed = df_base.copy()
        changed.loc[1, "Sum_bets"] = 1300.75
        match = align_unordered(df_base, changed, list(df_base.columns)).row_match
        assert match["only_in_file1"] == 1
        assert match["only_in_file2"] == 1
        assert match["modified"] == 0


class TestKeyColumns:
    def test_changed_value_with_keys_is_modified(self, df_base: pd.DataFrame) -> None:
        changed = df_base.iloc[[2, 1, 0]].reset_index(drop=True)
        changed.loc[1, "Sum_bets"] = 1300.75  # row dt=2026-09-01, idUser=102
        alignment = align_unordered(
            df_base, changed, list(df_base.columns), key_columns=["dt", "idUser"]
        )
        match = alignment.row_match
        assert match["matched"] == 3
        assert match["modified"] == 1
        assert match["equal"] == 2
        assert match["key_columns"] == ["dt", "idUser"]
        assert alignment.differences_mask.sum().sum() == 1
        assert bool(alignment.differences_mask.loc[1, "Sum_bets"]) is True

    def test_missing_key_column_raises(self, df_base: pd.DataFrame) -> None:
        with pytest.raises(ComparisonError, match="Ключевые"):
            align_unordered(df_base, df_base, list(df_base.columns), key_columns=["nope"])


class TestValueNormalisation:
    def test_int_equals_float(self) -> None:
        df1 = pd.DataFrame({"a": [8000, 2]})
        df2 = pd.DataFrame({"a": [2.0, 8000.0]})
        assert align_unordered(df1, df2, ["a"]).row_match["identical"] is True

    def test_midnight_datetime_equals_iso_date_string(self) -> None:
        df1 = pd.DataFrame({"dt": [datetime(2026, 9, 1), datetime(2026, 9, 2)]})
        df2 = pd.DataFrame({"dt": ["2026-09-02", "2026-09-01"]})
        alignment = align_unordered(df1, df2, ["dt"])
        assert alignment.row_match["identical"] is True
        assert alignment.differences_mask.sum().sum() == 0

    def test_nan_equals_none(self) -> None:
        df1 = pd.DataFrame({"a": [1.0, float("nan")], "b": ["x", None]})
        df2 = pd.DataFrame({"a": [None, 1.0], "b": [None, "x"]})
        assert align_unordered(df1, df2, ["a", "b"]).row_match["identical"] is True

    def test_numeric_string_is_not_a_number(self) -> None:
        df1 = pd.DataFrame({"a": [8000]})
        df2 = pd.DataFrame({"a": ["8000"]})
        assert align_unordered(df1, df2, ["a"]).row_match["identical"] is False

    def test_ignore_case(self) -> None:
        df1 = pd.DataFrame({"a": ["XOF", "UGX"]})
        df2 = pd.DataFrame({"a": ["ugx", "xof"]})
        assert align_unordered(df1, df2, ["a"]).row_match["identical"] is False
        assert align_unordered(df1, df2, ["a"], ignore_case=True).row_match["identical"] is True


class TestValueNormalisationEdgeCases:
    """Cells that reach the general (non-numpy-dtype) normalisation path."""

    @staticmethod
    def _identical(values1: list[object], values2: list[object]) -> bool:
        df1 = pd.DataFrame({"a": pd.Series(values1, dtype=object)})
        df2 = pd.DataFrame({"a": pd.Series(values2, dtype=object)})
        return bool(align_unordered(df1, df2, ["a"]).row_match["identical"])

    def test_nan_in_text_column_equals_none(self) -> None:
        assert self._identical(["x", float("nan")], [None, "x"])

    def test_datetime_with_time_equals_iso_string(self) -> None:
        assert self._identical([datetime(2026, 9, 1, 12, 30)], ["2026-09-01 12:30:00"])
        assert not self._identical([datetime(2026, 9, 1, 12, 30)], ["2026-09-01"])

    def test_date_equals_iso_string(self) -> None:
        assert self._identical([date(2026, 9, 1)], ["2026-09-01"])

    def test_numpy_scalar_in_object_column(self) -> None:
        assert self._identical([np.int64(5), np.float64(1.5)], [1.5, 5])

    def test_nullable_integer_na(self) -> None:
        df1 = pd.DataFrame({"a": pd.array([1, None], dtype="Int64")})
        df2 = pd.DataFrame({"a": [float("nan"), 1.0]})
        assert align_unordered(df1, df2, ["a"]).row_match["identical"] is True

    def test_non_scalar_cell_is_compared_as_text(self) -> None:
        assert self._identical([["a", "b"]], ["['a', 'b']"])


class TestColumnTotals:
    def test_totals_ignore_row_order(self, df_base: pd.DataFrame) -> None:
        shuffled = df_base.iloc[[2, 1, 0]].reset_index(drop=True)
        totals = align_unordered(df_base, shuffled, list(df_base.columns)).row_match[
            "column_totals"
        ]
        # Only the numeric column is summed; text columns are skipped.
        assert list(totals) == ["Sum_bets"]
        assert totals["Sum_bets"]["file1"] == totals["Sum_bets"]["file2"]
        assert totals["Sum_bets"]["file1"] == math.fsum([8000.0, 1300.5, 42.25])

    def test_integer_totals_are_exact_ints(self) -> None:
        df = pd.DataFrame({"n": [2**62, 2**62, 1]})
        totals = align_unordered(df, df.copy(), ["n"]).row_match["column_totals"]
        assert totals["n"]["file1"] == 2**63 + 1

    def test_all_empty_numeric_column_is_skipped(self) -> None:
        df = pd.DataFrame({"dt": [None, None], "n": [1, 2]}).astype({"dt": float})
        totals = align_unordered(df, df.copy(), ["dt", "n"]).row_match["column_totals"]
        assert list(totals) == ["n"]


class TestEmpty:
    def test_both_empty(self) -> None:
        df = pd.DataFrame({"a": []})
        alignment = align_unordered(df, df.copy(), ["a"])
        assert alignment.row_match["identical"] is True
        assert alignment.file1_data.shape == (0, 1)
        assert alignment.to_result({}).metadata["similarity_percentage"] == 0.0


class TestParseKeyColumns:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("dt, idUser", ["dt", "idUser"]),
            ("dt;idUser", ["dt", "idUser"]),
            (" dt ,, idUser ;", ["dt", "idUser"]),
            ("", []),
            (None, []),
        ],
    )
    def test_parse(self, text: str | None, expected: list[str]) -> None:
        assert parse_key_columns(text) == expected
