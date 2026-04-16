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
    df1: pd.DataFrame, df2: pd.DataFrame, na_marker: object
) -> pd.DataFrame:
    """Build a boolean DataFrame indicating cell-by-cell differences.

    TODO(fix, TODO_bugs.md #2): the object-sentinel fillna pattern emits a
    pandas FutureWarning on modern pandas; replace with
    ``df1.eq(df2) | (df1.isna() & df2.isna())`` once characterization
    tests are extended to cover edge cases.
    """
    df1_filled = df1.fillna(na_marker)  # type: ignore[arg-type]
    df2_filled = df2.fillna(na_marker)  # type: ignore[arg-type]
    mask = df1_filled.values != df2_filled.values
    return pd.DataFrame(mask, columns=df1.columns, index=df1.index)
