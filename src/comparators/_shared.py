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

    NA-safe across object columns containing ``pd.NA``, ``numpy.nan`` in
    float columns, and pandas nullable dtypes (``Int64``/``Float64``/
    ``boolean``/``string``). ``NA vs NA`` is treated as equal; exactly
    one NA on one side counts as a difference.

    Uses a fast numpy path for the common case (no ``pd.NA`` present),
    falling back to an NA-aware pandas path only when numpy raises
    ``TypeError: boolean value of NA is ambiguous`` — which happens when
    object columns contain ``pd.NA`` (e.g. after
    ``AdvancedComparator.align_dataframes`` calls
    ``reindex(..., fill_value=pd.NA)`` on mismatched row counts). The
    fallback uses ``DataFrame.ne`` + ``.where(both_present, False)`` and
    does **not** reintroduce the forbidden ``fillna(object_sentinel)``
    pattern.

    The legacy ``na_marker`` parameter is accepted but ignored; kept for
    backward compatibility with callers that passed the old sentinel.
    """
    del na_marker
    try:
        both_na = df1.isna().values & df2.isna().values
        values_differ = df1.values != df2.values
        mask_values = values_differ & ~both_na
        return pd.DataFrame(mask_values, columns=df1.columns, index=df1.index)
    except TypeError:
        # Object column contains pd.NA — numpy cannot reduce it to bool.
        # NA-aware pandas path: exactly-one-side-NA is always a difference;
        # both-NA is equal; otherwise compare normally.
        mask1_na = df1.isna()
        mask2_na = df2.isna()
        one_side_na = mask1_na ^ mask2_na
        both_present = ~(mask1_na | mask2_na)
        ne = df1.ne(df2)
        differ = ne.where(both_present, other=False).astype(bool)
        result = differ | one_side_na
        result.index = df1.index
        result.columns = df1.columns
        return result
