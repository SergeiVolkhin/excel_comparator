"""Internal helpers shared between BasicComparator and AdvancedComparator.

Extracted to remove duplication of _preprocess_dataframe and
_create_differences_mask logic. Not part of the public API.
"""

from __future__ import annotations

import pandas as pd


def preprocess_dataframe(
    df: pd.DataFrame,
    ignore_case: bool = False,
    ignore_whitespace: bool = False,
) -> pd.DataFrame:
    """Apply ignore_case / ignore_whitespace to object-dtype columns.

    Returns a copy; numeric columns are left untouched.
    """
    result = df.copy()
    if not (ignore_case or ignore_whitespace):
        return result

    for col in result.columns:
        if result[col].dtype != "object":
            continue
        mask = result[col].notna()
        if not mask.any():
            continue
        strings = result.loc[mask, col].astype(str)
        if ignore_case:
            strings = strings.str.lower()
        if ignore_whitespace:
            strings = strings.str.strip()
        result.loc[mask, col] = strings
    return result


def build_differences_mask(
    df1: pd.DataFrame, df2: pd.DataFrame, na_marker: object | None = None
) -> pd.DataFrame:
    """Build a boolean DataFrame indicating cell-by-cell differences.

    NaN vs NaN is treated as equal (not a difference), matching the
    original object-sentinel behaviour without triggering pandas'
    FutureWarning from ``fillna(object_sentinel)``. The ``na_marker``
    parameter is accepted but ignored; kept for backward compatibility
    with callers that passed the old sentinel.
    """
    del na_marker  # legacy API param; no longer needed
    both_na = df1.isna().values & df2.isna().values
    values_differ = df1.values != df2.values
    mask_values = values_differ & ~both_na
    return pd.DataFrame(mask_values, columns=df1.columns, index=df1.index)
