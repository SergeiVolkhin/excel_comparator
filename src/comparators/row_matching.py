"""Order-independent row matching shared by BasicComparator and AdvancedComparator.

Used when the ``ignore_row_order`` option is on: rows of the two tables are
paired by content (or by ``key_columns``) instead of by position, so a
different row order alone is not a difference. The aligned frames keep the
positional contract every formatter relies on: row ``i`` of ``file1_data``
is compared with row ``i`` of ``file2_data``, and a row present in only one
file is paired with an all-NA row, the same padding AdvancedComparator uses
for tables of different length.

Without key columns rows are paired in two passes: equal rows first, then,
among the rows left over, rows that agree in most columns (see
:func:`_pair_similar_rows`). So a row with one changed cell is reported as
changed, not as one row missing and another one added.

Not part of the public API, except :func:`parse_key_columns`, which the GUI
and CLI use to read the key-columns field, and the row pairs
(:func:`positional_row_pairs`, the ``STATUS_*`` values) read by formatters.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict, deque
from collections.abc import Hashable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, NamedTuple

import numpy as np
import numpy.typing as npt
import pandas as pd

from ..core.exceptions import ComparisonError
from ..core.interfaces import ComparisonResult
from ._shared import preprocess_dataframe

ObjectMatrix = npt.NDArray[np.object_]
IntArray = npt.NDArray[np.intp]
IntMatrix = npt.NDArray[np.intp]
FloatArray = npt.NDArray[np.float64]
BoolArray = npt.NDArray[np.bool_]
RowKey = tuple[Hashable, ...]

#: Separators accepted between column names in the key-columns field.
_KEY_COLUMNS_SEPARATORS = re.compile(r"[,;]")

#: Status of an aligned row in ``row_pairs``: both rows present and equal.
STATUS_EQUAL = "equal"
#: Rows paired by key columns (or by position) with some cells different.
STATUS_MODIFIED = "modified"
#: Rows paired by the similarity pass; some cells always differ.
STATUS_SIMILAR = "similar"
#: The row exists only in file 1 / only in file 2.
STATUS_ONLY_FILE1 = "only_file1"
STATUS_ONLY_FILE2 = "only_file2"

#: Similarity pass: at most this many candidate pairs are scored. Blocks of
#: rows sharing a value are taken from the most selective (fewest pairs) up,
#: so with few leftover rows every pair is scored — an exhaustive search.
_MAX_CANDIDATE_PAIRS = 2_000_000

#: Similarity pass: safety cap on assignment rounds. The first round pairs
#: nearly everything; later ones only resolve ties freed by earlier pairs.
_MAX_SIMILARITY_ROUNDS = 100

#: Scores equal to this many decimals are a tie (float rounding aside).
_SCORE_DECIMALS = 9


def parse_key_columns(text: str | None) -> list[str]:
    """Split a user-entered list like ``"dt, idUser"`` into column names."""
    if not text:
        return []
    return [part.strip() for part in _KEY_COLUMNS_SEPARATORS.split(text) if part.strip()]


@dataclass
class RowAlignment:
    """Two frames aligned row by row, plus the matching statistics.

    ``row_pairs`` has one row per aligned row: ``row_file1`` / ``row_file2``
    are 0-based positions in the loaded tables (``-1`` = no row in that
    file) and ``status`` is one of the ``STATUS_*`` values.
    """

    file1_data: pd.DataFrame
    file2_data: pd.DataFrame
    differences_mask: pd.DataFrame
    row_match: dict[str, Any]
    row_pairs: pd.DataFrame

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
            row_pairs=self.row_pairs,
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
    unmatched row. Without key columns the rows left unmatched get a second
    chance: rows that agree in most columns are paired as one changed row
    (see :func:`_pair_similar_rows`). Output order: the rows of ``df1`` in
    their original order (each with its match or an all-NA row), then the
    rows found only in ``df2``. Cells are compared after the same
    normalisation that is used for matching, so "matched" and "equal cells"
    never disagree.
    """
    keys = list(key_columns or [])
    missing = [key for key in keys if key not in columns]
    if missing:
        raise ComparisonError(f"Ключевые столбцы {missing} отсутствуют в общих столбцах")

    left = df1[columns].reset_index(drop=True)
    right = df2[columns].reset_index(drop=True)

    processed1 = preprocess_dataframe(left, ignore_case, ignore_whitespace)
    processed2 = preprocess_dataframe(right, ignore_case, ignore_whitespace)
    canonical1 = _canonical_matrix(processed1)
    canonical2 = _canonical_matrix(processed2)

    key_positions = [columns.index(key) for key in keys] or list(range(len(columns)))
    match_for_1 = _match_rows(
        _row_keys(canonical1, key_positions), _row_keys(canonical2, key_positions)
    )

    # Key columns say which rows are the same row. Without them a row with a
    # changed cell is looked for among the rows left without an equal one.
    similar_for_1 = np.zeros(len(left), dtype=bool)
    if not keys:
        rest1 = np.flatnonzero(match_for_1 < 0)
        rest2 = _unmatched_in_file2(match_for_1, len(right))
        for position1, position2 in _pair_similar_rows(
            _Side(processed1, canonical1, rest1), _Side(processed2, canonical2, rest2)
        ):
            match_for_1[position1] = position2
            similar_for_1[position1] = True

    positions1, positions2 = _aligned_positions(match_for_1, len(right))
    differs = np.not_equal(
        _take_canonical(canonical1, positions1), _take_canonical(canonical2, positions2)
    )
    mask = pd.DataFrame(differs, columns=left.columns)

    # Aligned rows start with the rows of file 1 in their order.
    similar = np.zeros(len(positions1), dtype=bool)
    similar[: len(left)] = similar_for_1

    row_match = _row_match_stats(
        positions1, positions2, differs, keys, len(left), len(right), int(similar_for_1.sum())
    )
    row_match["column_totals"] = _column_totals(left, right)

    return RowAlignment(
        file1_data=_take_rows(left, positions1),
        file2_data=_take_rows(right, positions2),
        differences_mask=mask,
        row_match=row_match,
        row_pairs=_row_pairs(positions1, positions2, differs, similar),
    )


def positional_row_pairs(mask: pd.DataFrame, rows_file1: int, rows_file2: int) -> pd.DataFrame:
    """``row_pairs`` of a positional comparison: row ``i`` against row ``i``.

    The comparator pads the shorter table, so the rows past its end exist
    in the other file only.
    """
    positions = np.arange(len(mask), dtype=np.intp)
    positions1 = np.where(positions < rows_file1, positions, -1)
    positions2 = np.where(positions < rows_file2, positions, -1)
    differs = mask.to_numpy(dtype=bool)
    return _row_pairs(positions1, positions2, differs, np.zeros(len(mask), dtype=bool))


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


def _match_rows(keys1: list[RowKey], keys2: list[RowKey]) -> IntArray:
    """Position in file 2 of the row with an equal key, for every row of file 1.

    ``-1`` = no such row. Duplicate keys are paired in order of appearance.
    """
    pending: defaultdict[RowKey, deque[int]] = defaultdict(deque)
    for position, key in enumerate(keys2):
        pending[key].append(position)

    matches: list[int] = []
    for key in keys1:
        candidates = pending.get(key)
        matches.append(candidates.popleft() if candidates else -1)
    return np.asarray(matches, dtype=np.intp)


def _unmatched_in_file2(match_for_1: IntArray, rows_file2: int) -> IntArray:
    """Positions of the file 2 rows no file 1 row is paired with, in order."""
    used = np.zeros(rows_file2, dtype=bool)
    used[match_for_1[match_for_1 >= 0]] = True
    return np.flatnonzero(~used)


def _aligned_positions(match_for_1: IntArray, rows_file2: int) -> tuple[IntArray, IntArray]:
    """Aligned row positions, ``-1`` = no row on that side.

    The rows of file 1 in their order, each with its pair, then the rows of
    file 2 left without a pair.
    """
    only_in_2 = _unmatched_in_file2(match_for_1, rows_file2)
    positions1 = np.concatenate(
        [np.arange(len(match_for_1), dtype=np.intp), np.full(len(only_in_2), -1, dtype=np.intp)]
    )
    positions2 = np.concatenate([match_for_1, only_in_2.astype(np.intp)])
    return positions1, positions2


@dataclass
class _Side:
    """One file as the similarity pass sees it.

    ``frame`` is the preprocessed table, ``canonical`` its normalised cells
    and ``rest`` the positions of the rows left without an equal row.
    """

    frame: pd.DataFrame
    canonical: ObjectMatrix
    rest: IntArray


def _pair_similar_rows(side1: _Side, side2: _Side) -> list[tuple[int, int]]:
    """Second pass: pair the rows left without an equal row by similarity.

    Two leftover rows are candidates when at least half of the columns are
    equal. A candidate's score is the summed weight of its equal values; a
    value weighs ``log(N / count)`` over both files, so an equal rare value
    (an id, an amount) says much more about "the same row" than an equal
    common one (0, a currency, a date), and a value found in every row
    says nothing. A pair is taken when each side is the other's best
    candidate and that best is not tied: a tie leaves the rows unpaired,
    because a wrong pair is worse than a row reported in one file only.

    Identical leftover rows are grouped into profiles first, so duplicates
    never tie with each other, and a profile pair takes as many rows as
    both profiles still have, in order of appearance. Rounds repeat while
    they pair something, as a tie can resolve once a rival is paired
    elsewhere. Which rows are paired, by content, does not depend on the
    row order of either file.

    Returns ``(file 1 position, file 2 position)`` pairs.
    """
    n_columns = side1.canonical.shape[1]
    if n_columns < 2 or len(side1.rest) == 0 or len(side2.rest) == 0:
        return []

    codes1, codes2, weights = _value_codes(side1, side2)
    profiles1 = _Profiles.of(codes1, side1.rest)
    profiles2 = _Profiles.of(codes2, side2.rest)

    candidates1, candidates2 = _candidate_pairs(profiles1.codes, profiles2.codes)
    candidates1, candidates2, scores = _score_candidates(
        profiles1.codes, profiles2.codes, candidates1, candidates2, weights
    )

    remaining1 = profiles1.counts.copy()
    remaining2 = profiles2.counts.copy()
    pairs: list[tuple[int, int]] = []
    for _ in range(_MAX_SIMILARITY_ROUNDS):
        alive = (remaining1[candidates1] > 0) & (remaining2[candidates2] > 0)
        candidates1, candidates2, scores = candidates1[alive], candidates2[alive], scores[alive]
        accepted = _clear_mutual_best(candidates1, candidates2, scores, remaining1, remaining2)
        if not accepted.any():
            break
        for profile1, profile2 in zip(
            candidates1[accepted].tolist(), candidates2[accepted].tolist(), strict=True
        ):
            left1, left2 = int(remaining1[profile1]), int(remaining2[profile2])
            count = min(left1, left2)
            rows1 = profiles1.take(profile1, left1, count)
            rows2 = profiles2.take(profile2, left2, count)
            pairs.extend(zip(rows1.tolist(), rows2.tolist(), strict=True))
            remaining1[profile1] -= count
            remaining2[profile2] -= count
    return pairs


def _value_codes(side1: _Side, side2: _Side) -> tuple[IntMatrix, IntMatrix, list[FloatArray]]:
    """Value codes of the leftover rows and, per column, the weight of each code.

    Equal values share a code. A code's weight is ``log(N / count)``, its
    count taken over every row of both files.
    """
    rows1 = len(side1.canonical)
    total = rows1 + len(side2.canonical)
    leftover = np.concatenate([side1.rest, rows1 + side2.rest])
    n_columns = side1.canonical.shape[1]
    codes = np.empty((len(leftover), n_columns), dtype=np.intp)
    weights: list[FloatArray] = []
    for position in range(n_columns):
        column_codes = _column_codes(side1, side2, position)
        codes[:, position] = column_codes[leftover]
        weights.append(np.log(total / np.bincount(column_codes)))
    return codes[: len(side1.rest)], codes[len(side1.rest) :], weights


def _column_codes(side1: _Side, side2: _Side, position: int) -> IntArray:
    """Codes of one column over both files: equal values share a code.

    A plain numpy column of the same dtype in both files is coded from its
    raw values: equality is the same as for the canonical forms (NaN with
    NaN, NaT with NaT), and it is much faster than hashing Python objects.
    """
    column1 = side1.frame.iloc[:, position]
    column2 = side2.frame.iloc[:, position]
    dtype = column1.dtype
    if isinstance(dtype, np.dtype) and dtype == column2.dtype and dtype.kind in "biufM":
        values = np.concatenate([column1.to_numpy(), column2.to_numpy()])
    else:
        values = np.concatenate([side1.canonical[:, position], side2.canonical[:, position]])
    codes, _ = pd.factorize(values, use_na_sentinel=False)
    return codes


@dataclass
class _Profiles:
    """Distinct leftover rows of one file and the rows that share each one.

    The rows of profile ``p`` are ``rows[starts[p] : starts[p] + counts[p]]``,
    in order of appearance.
    """

    codes: IntMatrix
    counts: IntArray
    starts: IntArray
    rows: IntArray

    @classmethod
    def of(cls, codes: IntMatrix, rows: IntArray) -> _Profiles:
        unique, inverse, counts = np.unique(codes, axis=0, return_inverse=True, return_counts=True)
        order = np.argsort(inverse.reshape(-1), kind="stable")
        starts = np.cumsum(counts) - counts
        return cls(codes=unique, counts=counts, starts=starts, rows=rows[order])

    def take(self, profile: int, remaining: int, count: int) -> IntArray:
        """The next ``count`` rows of ``profile`` that are not paired yet."""
        first = self.starts[profile] + self.counts[profile] - remaining
        taken: IntArray = self.rows[first : first + count]
        return taken


class _Blocks(NamedTuple):
    """Profiles sharing a value in one column, file by file.

    Block ``b`` holds ``order1[starts1[b] : starts1[b] + counts1[b]]`` from
    file 1 and the matching slice of ``order2`` from file 2.
    """

    order1: IntArray
    starts1: IntArray
    counts1: IntArray
    order2: IntArray
    starts2: IntArray
    counts2: IntArray


def _column_blocks(values1: IntArray, values2: IntArray) -> _Blocks:
    """Blocks of one column: a value present on both sides makes a block."""
    order1 = np.argsort(values1, kind="stable")
    order2 = np.argsort(values2, kind="stable")
    unique1, starts1, counts1 = np.unique(values1[order1], return_index=True, return_counts=True)
    unique2, starts2, counts2 = np.unique(values2[order2], return_index=True, return_counts=True)
    _, at1, at2 = np.intersect1d(unique1, unique2, assume_unique=True, return_indices=True)
    return _Blocks(order1, starts1[at1], counts1[at1], order2, starts2[at2], counts2[at2])


def _expand_blocks(blocks: _Blocks, selected: BoolArray) -> tuple[IntArray, IntArray]:
    """Every (file 1 profile, file 2 profile) pair inside the selected blocks."""
    starts1, counts1 = blocks.starts1[selected], blocks.counts1[selected]
    starts2, counts2 = blocks.starts2[selected], blocks.counts2[selected]
    sizes = counts1 * counts2
    offsets = np.arange(sizes.sum(), dtype=np.intp) - np.repeat(np.cumsum(sizes) - sizes, sizes)
    widths = np.repeat(counts2, sizes)
    profiles1 = blocks.order1[np.repeat(starts1, sizes) + offsets // widths]
    profiles2 = blocks.order2[np.repeat(starts2, sizes) + offsets % widths]
    return profiles1, profiles2


def _candidate_pairs(codes1: IntMatrix, codes2: IntMatrix) -> tuple[IntArray, IntArray]:
    """Profile pairs that share a value in at least one column ("blocking").

    Blocks of every column are expanded from the most selective (fewest
    pairs) up while the total stays within ``_MAX_CANDIDATE_PAIRS``. With few
    leftover rows that is every pair. With very many, only blocks of common
    values (0, the one currency) are left out, and a pair that shares
    nothing rarer is not considered.
    """
    blocks = [_column_blocks(codes1[:, c], codes2[:, c]) for c in range(codes1.shape[1])]
    sizes = np.concatenate([block.counts1 * block.counts2 for block in blocks])
    order = np.argsort(sizes, kind="stable")
    selected = np.zeros(len(sizes), dtype=bool)
    selected[order[np.cumsum(sizes[order]) <= _MAX_CANDIDATE_PAIRS]] = True

    pairs1: list[IntArray] = []
    pairs2: list[IntArray] = []
    start = 0
    for block in blocks:
        end = start + len(block.counts1)
        profiles1, profiles2 = _expand_blocks(block, selected[start:end])
        pairs1.append(profiles1)
        pairs2.append(profiles2)
        start = end

    # A pair sharing several values comes from several blocks: keep one.
    width = len(codes2)
    pair_ids = np.unique(np.concatenate(pairs1) * width + np.concatenate(pairs2))
    return pair_ids // width, pair_ids % width


def _score_candidates(
    codes1: IntMatrix,
    codes2: IntMatrix,
    candidates1: IntArray,
    candidates2: IntArray,
    weights: list[FloatArray],
) -> tuple[IntArray, IntArray, FloatArray]:
    """Keep the candidates with at least half of the columns equal, with scores.

    The score is the summed weight of the equal values; a candidate whose
    equal values are found in every row (weight 0) is dropped too.
    """
    n_columns = codes1.shape[1]
    equal = np.zeros(len(candidates1), dtype=np.intp)
    scores = np.zeros(len(candidates1), dtype=np.float64)
    for position in range(n_columns):
        values = codes1[candidates1, position]
        same = values == codes2[candidates2, position]
        equal += same
        scores += np.where(same, weights[position][values], 0.0)
    keep = (equal * 2 >= n_columns) & (scores > 0)
    return candidates1[keep], candidates2[keep], np.round(scores[keep], _SCORE_DECIMALS)


def _clear_mutual_best(
    candidates1: IntArray,
    candidates2: IntArray,
    scores: FloatArray,
    remaining1: IntArray,
    remaining2: IntArray,
) -> BoolArray:
    """Candidates that are the clear best of both their profiles.

    A profile's best is clear when one candidate reaches it, or when the
    profile has rows enough for every candidate tied at its best: copies of
    one row can go to several equally good partners without ambiguity.
    """
    best1 = np.full(len(remaining1), -np.inf)
    np.maximum.at(best1, candidates1, scores)
    best2 = np.full(len(remaining2), -np.inf)
    np.maximum.at(best2, candidates2, scores)
    top1 = scores == best1[candidates1]
    top2 = scores == best2[candidates2]

    ties1 = np.bincount(candidates1[top1], minlength=len(remaining1))
    ties2 = np.bincount(candidates2[top2], minlength=len(remaining2))
    demand1 = np.bincount(
        candidates1[top1], weights=remaining2[candidates2[top1]], minlength=len(remaining1)
    )
    demand2 = np.bincount(
        candidates2[top2], weights=remaining1[candidates1[top2]], minlength=len(remaining2)
    )
    clear1 = (ties1 == 1) | (demand1 <= remaining1)
    clear2 = (ties2 == 1) | (demand2 <= remaining2)
    accepted: BoolArray = top1 & top2 & clear1[candidates1] & clear2[candidates2]
    return accepted


def _take_canonical(matrix: ObjectMatrix, positions: IntArray) -> ObjectMatrix:
    """Rows of ``matrix`` at ``positions``; ``-1`` becomes a row of ``None``."""
    padding = np.full((1, matrix.shape[1]), None, dtype=object)
    padded: ObjectMatrix = np.vstack([matrix, padding])
    index = np.array(positions, dtype=np.intp)  # a copy: -1 is rewritten below
    index[index < 0] = matrix.shape[0]
    taken: ObjectMatrix = padded[index]
    return taken


def _take_rows(df: pd.DataFrame, positions: IntArray) -> pd.DataFrame:
    """Rows of ``df`` at ``positions``; ``-1`` becomes an all-NA padding row."""
    return df.reindex(positions, fill_value=pd.NA).reset_index(drop=True)  # type: ignore[arg-type]


def _row_pairs(
    positions1: IntArray, positions2: IntArray, differs: BoolArray, similar: BoolArray
) -> pd.DataFrame:
    """One row per aligned row: the source positions and the ``STATUS_*``."""
    has1 = positions1 >= 0
    has2 = positions2 >= 0
    status = np.full(len(positions1), STATUS_EQUAL, dtype=object)
    status[has1 & has2 & differs.any(axis=1)] = STATUS_MODIFIED
    status[similar] = STATUS_SIMILAR
    status[has1 & ~has2] = STATUS_ONLY_FILE1
    status[~has1 & has2] = STATUS_ONLY_FILE2
    return pd.DataFrame({"row_file1": positions1, "row_file2": positions2, "status": status})


def _row_match_stats(
    positions1: IntArray,
    positions2: IntArray,
    differs: BoolArray,
    key_columns: list[str],
    rows_file1: int,
    rows_file2: int,
    similar: int,
) -> dict[str, Any]:
    """Counts of matched / modified / unmatched rows and whether order changed.

    ``similar`` pairs (found by the similarity pass) are part of ``modified``.
    """
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
        "similar": similar,
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
