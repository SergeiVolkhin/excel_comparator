"""Order-independent row matching shared by BasicComparator and AdvancedComparator.

Used when the ``ignore_row_order`` option is on: rows of the two tables are
paired by content (or by ``key_columns``) instead of by position, so a
different row order alone is not a difference. The aligned frames keep the
positional contract every formatter relies on: row ``i`` of ``file1_data``
is compared with row ``i`` of ``file2_data``, and a row present in only one
file is paired with an all-NA row, the same padding AdvancedComparator uses
for tables of different length.

Not part of the public API, except :func:`parse_key_columns`, which the GUI
and CLI use to read the key-columns field.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict, deque
from collections.abc import Hashable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd

from ..core.exceptions import ComparisonError
from ..core.interfaces import ComparisonResult
from ._shared import preprocess_dataframe

ObjectMatrix = npt.NDArray[np.object_]
RowKey = tuple[Hashable, ...]

#: Separators accepted between column names in the key-columns field.
_KEY_COLUMNS_SEPARATORS = re.compile(r"[,;]")


def parse_key_columns(text: str | None) -> list[str]:
    """Split a user-entered list like ``"dt, idUser"`` into column names."""
    if not text:
        return []
    return [part.strip() for part in _KEY_COLUMNS_SEPARATORS.split(text) if part.strip()]


@dataclass
class RowAlignment:
    """Two frames aligned row by row, plus the matching statistics."""

    file1_data: pd.DataFrame
    file2_data: pd.DataFrame
    differences_mask: pd.DataFrame
    row_match: dict[str, Any]

    def to_result(self, options: dict[str, Any], **extra_metadata: Any) -> ComparisonResult:
        """Wrap the alignment into a ``ComparisonResult`` with standard metadata."""
        total_cells = self.file1_data.size
        different_cells = self.differences_mask.sum().sum()
        if total_cells > 0:
            similarity_percentage = ((total_cells - different_cells) / total_cells) * 100
        else:
            similarity_percentage = 0.0

        metadata: dict[str, Any] = {
            "total_cells": total_cells,
            "different_cells": different_cells,
            "similarity_percentage": similarity_percentage,
            "comparison_options": options,
            "shape": self.file1_data.shape,
            "row_match": self.row_match,
            **extra_metadata,
        }
        return ComparisonResult(
            differences_mask=self.differences_mask,
            file1_data=self.file1_data,
            file2_data=self.file2_data,
            metadata=metadata,
        )


def align_unordered(
    df1: pd.DataFrame,
    df2: pd.DataFrame,
    columns: list[str],
    key_columns: Sequence[str] | None = None,
    ignore_case: bool = False,
    ignore_whitespace: bool = False,
) -> RowAlignment:
    """Pair the rows of ``df1`` and ``df2`` regardless of their order.

    Rows are matched by ``key_columns`` or, when none are given, by every
    compared column (the whole row). Duplicate keys are paired in order of
    appearance, so two equal rows against one count as one match plus one
    unmatched row. Output order: the rows of ``df1`` in their original order
    (each with its match or an all-NA row), then the rows found only in
    ``df2``. Cells are compared after the same normalisation that is used
    for matching, so "matched" and "equal cells" never disagree.
    """
    keys = list(key_columns or [])
    missing = [key for key in keys if key not in columns]
    if missing:
        raise ComparisonError(f"Ключевые столбцы {missing} отсутствуют в общих столбцах")

    left = df1[columns].reset_index(drop=True)
    right = df2[columns].reset_index(drop=True)

    canonical1 = _canonical_matrix(preprocess_dataframe(left, ignore_case, ignore_whitespace))
    canonical2 = _canonical_matrix(preprocess_dataframe(right, ignore_case, ignore_whitespace))

    key_positions = [columns.index(key) for key in keys] or list(range(len(columns)))
    positions1, positions2 = _match_rows(
        _row_keys(canonical1, key_positions), _row_keys(canonical2, key_positions)
    )

    differs = np.not_equal(
        _take_canonical(canonical1, positions1), _take_canonical(canonical2, positions2)
    )
    mask = pd.DataFrame(differs, columns=left.columns)

    row_match = _row_match_stats(positions1, positions2, differs, keys, len(left), len(right))
    row_match["column_totals"] = _column_totals(left, right)

    return RowAlignment(
        file1_data=_take_rows(left, positions1),
        file2_data=_take_rows(right, positions2),
        differences_mask=mask,
        row_match=row_match,
    )


def _canonical_scalar(value: Any) -> Any:
    """Map a cell value to the form used for matching and cell comparison.

    Any flavour of NA (None, NaN, NaT, pd.NA) becomes ``None``; a datetime at
    midnight becomes an ISO date string, so a date written as a date by one
    export equals the same date written as text by another; other datetimes
    become ISO strings. Numbers stay numbers (``8000 == 8000.0`` already
    holds in Python); numeric-looking strings are *not* converted.
    """
    if value is None or isinstance(value, str):
        return value
    if not pd.api.types.is_scalar(value):
        return str(value)
    if pd.isna(value):
        return None
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, datetime):
        if (value.hour, value.minute, value.second, value.microsecond) == (0, 0, 0, 0):
            return value.date().isoformat()
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    return value


def _canonical_column(values: pd.Series) -> list[Any]:
    """Normalised values of one column (see :func:`_canonical_scalar`)."""
    items = values.astype(object).tolist()
    # Fast paths for plain numpy dtypes: their Python values need no
    # conversion beyond NaN → None. Nullable extension dtypes (Int64,
    # boolean) can hold pd.NA, so they take the general path.
    if isinstance(values.dtype, np.dtype):
        if values.dtype.kind in "iub":
            return items
        if values.dtype.kind == "f":
            return [None if item != item else item for item in items]
    return [_canonical_scalar(item) for item in items]


def _canonical_matrix(df: pd.DataFrame) -> ObjectMatrix:
    """Normalise every cell of ``df`` into an object matrix of the same shape."""
    matrix: ObjectMatrix = np.empty(df.shape, dtype=object)
    for position in range(df.shape[1]):
        matrix[:, position] = _canonical_column(df.iloc[:, position])
    return matrix


def _row_keys(matrix: ObjectMatrix, key_positions: list[int]) -> list[RowKey]:
    """Hashable key of every row built from the ``key_positions`` columns."""
    return [tuple(row) for row in matrix[:, key_positions].tolist()]


def _match_rows(keys1: list[RowKey], keys2: list[RowKey]) -> tuple[list[int], list[int]]:
    """Pair equal keys; returns aligned row positions, ``-1`` = no row on that side."""
    pending: defaultdict[RowKey, deque[int]] = defaultdict(deque)
    for position, key in enumerate(keys2):
        pending[key].append(position)

    positions1: list[int] = []
    positions2: list[int] = []
    used2 = [False] * len(keys2)
    for position, key in enumerate(keys1):
        candidates = pending.get(key)
        match = candidates.popleft() if candidates else -1
        if match >= 0:
            used2[match] = True
        positions1.append(position)
        positions2.append(match)

    only_in_2 = [position for position, used in enumerate(used2) if not used]
    positions1.extend([-1] * len(only_in_2))
    positions2.extend(only_in_2)
    return positions1, positions2


def _take_canonical(matrix: ObjectMatrix, positions: list[int]) -> ObjectMatrix:
    """Rows of ``matrix`` at ``positions``; ``-1`` becomes a row of ``None``."""
    padding = np.full((1, matrix.shape[1]), None, dtype=object)
    padded: ObjectMatrix = np.vstack([matrix, padding])
    index = np.asarray(positions, dtype=np.intp)
    index[index < 0] = matrix.shape[0]
    taken: ObjectMatrix = padded[index]
    return taken


def _take_rows(df: pd.DataFrame, positions: list[int]) -> pd.DataFrame:
    """Rows of ``df`` at ``positions``; ``-1`` becomes an all-NA padding row."""
    return df.reindex(positions, fill_value=pd.NA).reset_index(drop=True)  # type: ignore[arg-type]


def _row_match_stats(
    positions1: list[int],
    positions2: list[int],
    differs: npt.NDArray[np.bool_],
    key_columns: list[str],
    rows_file1: int,
    rows_file2: int,
) -> dict[str, Any]:
    """Counts of matched / modified / unmatched rows and whether order changed."""
    side1 = np.asarray(positions1, dtype=np.intp)
    side2 = np.asarray(positions2, dtype=np.intp)
    paired = (side1 >= 0) & (side2 >= 0)

    matched = int(paired.sum())
    modified = int((paired & differs.any(axis=1)).sum())
    only_in_file1 = int(((side1 >= 0) & (side2 < 0)).sum())
    only_in_file2 = int((side1 < 0).sum())
    # Pairs are listed in file 1 order; any step back in file 2 positions
    # means the second file had these rows in a different order.
    order_changed = bool((np.diff(side2[paired]) < 0).any())

    return {
        "key_columns": key_columns,
        "rows_file1": rows_file1,
        "rows_file2": rows_file2,
        "matched": matched,
        "equal": matched - modified,
        "modified": modified,
        "only_in_file1": only_in_file1,
        "only_in_file2": only_in_file2,
        "order_changed": order_changed,
        "identical": only_in_file1 == 0 and only_in_file2 == 0 and modified == 0,
    }


def _column_totals(df1: pd.DataFrame, df2: pd.DataFrame) -> dict[str, dict[str, float | int]]:
    """Exact per-column sums of the numeric columns present in both frames.

    ``math.fsum`` is used for floats: it is correctly rounded, so the total
    does not depend on row order and two orderings of the same rows give
    exactly the same number.
    """
    totals: dict[str, dict[str, float | int]] = {}
    for position, column in enumerate(df1.columns):
        values1 = df1.iloc[:, position]
        values2 = df2.iloc[:, position]
        if not (_is_summable(values1) and _is_summable(values2)):
            continue
        if values1.isna().all() and values2.isna().all():
            continue
        totals[str(column)] = {"file1": _exact_sum(values1), "file2": _exact_sum(values2)}
    return totals


def _is_summable(values: pd.Series) -> bool:
    return pd.api.types.is_numeric_dtype(values) and not pd.api.types.is_bool_dtype(values)


def _exact_sum(values: pd.Series) -> float | int:
    present = values.dropna()
    if pd.api.types.is_integer_dtype(present):
        return sum(int(value) for value in present.tolist())
    return math.fsum(float(value) for value in present.tolist())
