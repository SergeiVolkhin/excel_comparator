"""Property-based tests for value comparison and preprocessing.

Uses hypothesis to generate random DataFrames and assert invariants
that must hold for any input: idempotency, symmetry, zero-diff on equal
inputs, etc. Goal is to catch edge cases the characterization tests miss.
"""

from __future__ import annotations

import pandas as pd
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from src.comparators.basic_comparator import BasicComparator

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_cell = st.one_of(
    st.integers(min_value=-10_000, max_value=10_000),
    st.floats(allow_nan=False, allow_infinity=False, width=32),
    st.text(min_size=0, max_size=20),
    st.none(),
)


@st.composite
def _small_df(draw: st.DrawFn) -> pd.DataFrame:
    ncols = draw(st.integers(min_value=1, max_value=4))
    nrows = draw(st.integers(min_value=1, max_value=8))
    cols = [f"c{i}" for i in range(ncols)]
    data = {c: draw(st.lists(_cell, min_size=nrows, max_size=nrows)) for c in cols}
    return pd.DataFrame(data)


_settings = settings(
    max_examples=40,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)


# ---------------------------------------------------------------------------
# Properties of BasicComparator.compare
# ---------------------------------------------------------------------------


@_settings
@given(_small_df())
def test_equal_dataframes_have_zero_diffs(df: pd.DataFrame) -> None:
    comp = BasicComparator()
    result = comp.compare(df, df.copy())
    assert result.differences_mask.sum().sum() == 0
    assert result.metadata["similarity_percentage"] == 100.0


@_settings
@given(_small_df())
def test_comparison_is_symmetric_in_diff_count(df: pd.DataFrame) -> None:
    comp = BasicComparator()
    if df.size == 0:
        return
    df2 = df.copy().astype(object)
    df2.iloc[0, 0] = "__sentinel_unique_value__"
    df_obj = df.astype(object)
    a = comp.compare(df_obj, df2).differences_mask.sum().sum()
    b = comp.compare(df2, df_obj).differences_mask.sum().sum()
    assert a == b


@_settings
@given(_small_df())
def test_preprocess_is_idempotent(df: pd.DataFrame) -> None:
    comp = BasicComparator()
    once = comp._preprocess_dataframe(df, ignore_case=True, ignore_whitespace=True)
    twice = comp._preprocess_dataframe(once, ignore_case=True, ignore_whitespace=True)
    # After one application, a second application must not change anything.
    comp2 = BasicComparator()
    result = comp2.compare(once, twice)
    assert result.differences_mask.sum().sum() == 0


@_settings
@given(st.text(min_size=0, max_size=10), st.text(min_size=0, max_size=10))
def test_ignore_case_collapses_case_only_differences(a: str, b: str) -> None:
    if a.lower() != b.lower():
        return  # only meaningful when case-insensitive-equal
    df1 = pd.DataFrame({"x": [a, "anchor"]})
    df2 = pd.DataFrame({"x": [b, "anchor"]})
    comp = BasicComparator()
    result = comp.compare(df1, df2, ignore_case=True)
    assert result.differences_mask.loc[0, "x"] == False  # noqa: E712
