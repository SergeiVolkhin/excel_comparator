"""Tests for _shared.build_differences_mask — NA-safety regression guard."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.comparators._shared import build_differences_mask


class TestBuildDifferencesMaskNASafety:
    def test_object_column_with_pd_na_does_not_crash(self) -> None:
        df1 = pd.DataFrame({"a": ["x", pd.NA, "y", pd.NA]}, dtype=object)
        df2 = pd.DataFrame({"a": ["x", "q", pd.NA, pd.NA]}, dtype=object)
        m = build_differences_mask(df1, df2)
        assert m["a"].tolist() == [False, True, True, False]

    def test_nullable_int64_with_pd_na(self) -> None:
        df1 = pd.DataFrame({"x": pd.array([1, 2, pd.NA, 4], dtype="Int64")})
        df2 = pd.DataFrame({"x": pd.array([1, 9, pd.NA, pd.NA], dtype="Int64")})
        m = build_differences_mask(df1, df2)
        assert m["x"].tolist() == [False, True, False, True]

    def test_float64_nan_both_sides_is_equal(self) -> None:
        df1 = pd.DataFrame({"x": [1.0, np.nan, 3.0]})
        df2 = pd.DataFrame({"x": [1.0, np.nan, 4.0]})
        m = build_differences_mask(df1, df2)
        assert m["x"].tolist() == [False, False, True]

    def test_reindex_padding_scenario_matches_advanced_comparator(self) -> None:
        df1 = pd.DataFrame({"a": ["x", "y", "z"]})
        df2 = pd.DataFrame({"a": ["x", "y"]}).reindex(range(3), fill_value=pd.NA)
        m = build_differences_mask(df1, df2)
        assert m["a"].tolist() == [False, False, True]

    def test_identical_frames_all_false(self) -> None:
        df = pd.DataFrame({"a": [1, 2, 3], "b": ["x", None, "z"]})
        m = build_differences_mask(df, df.copy())
        assert not m.values.any()

    def test_shape_and_index_preserved(self) -> None:
        df1 = pd.DataFrame({"a": [1, 2]}, index=pd.Index([10, 20], name="row"))
        df2 = pd.DataFrame({"a": [1, 9]}, index=pd.Index([10, 20], name="row"))
        m = build_differences_mask(df1, df2)
        assert m.index.equals(df1.index)
        assert list(m.columns) == ["a"]

    def test_legacy_na_marker_kwarg_ignored(self) -> None:
        df1 = pd.DataFrame({"a": [1, 2]})
        df2 = pd.DataFrame({"a": [1, 3]})
        m = build_differences_mask(df1, df2, na_marker="__NA__")
        assert m["a"].tolist() == [False, True]
