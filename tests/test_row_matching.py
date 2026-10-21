"""Tests for order-independent row matching (src/comparators/row_matching.py)."""

from __future__ import annotations

import math
from datetime import date, datetime

import numpy as np
import pandas as pd
import pytest

from src.comparators import row_matching
from src.comparators.advanced_comparator import AdvancedComparator
from src.comparators.basic_comparator import BasicComparator
from src.comparators.row_matching import (
    STATUS_EQUAL,
    STATUS_MODIFIED,
    STATUS_ONLY_FILE1,
    STATUS_ONLY_FILE2,
    STATUS_SIMILAR,
    align_unordered,
    parse_key_columns,
)
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

    def test_changed_value_without_keys_is_found_by_similarity(self, df_base: pd.DataFrame) -> None:
        changed = df_base.copy()
        changed.loc[1, "Sum_bets"] = 1300.75
        alignment = align_unordered(df_base, changed, list(df_base.columns))
        match = alignment.row_match
        assert match["only_in_file1"] == 0
        assert match["only_in_file2"] == 0
        assert match["modified"] == 1
        assert match["similar"] == 1
        assert alignment.differences_mask.sum().sum() == 1
        assert bool(alignment.differences_mask.loc[1, "Sum_bets"]) is True


def _bets() -> pd.DataFrame:
    """A slice shaped like the real export: player × day, mostly-zero measures."""
    return pd.DataFrame(
        {
            "dt": ["2026-09-01"] * 6,
            "idUser": [998693777, 998702019, 998703229, 998704000, 998705000, 998706000],
            "Sum_bets": [3500.0, 1100.0, 23146.54, 0.0, 500.0, 0.0],
            "Number_of_bets": [2, 3, 12, 0, 1, 0],
            "Sum_wins": [0.0, 2414.5, 6045.91, 0.0, 0.0, 0.0],
            "Number_of_wins": [0, 1, 1, 0, 0, 0],
            "Sum_tax_out": [0.0] * 6,
            "Sum_in_from_sum_out": [0.0, 100.0, 500.0, 0.0, 0.0, 0.0],
            "Currency": ["XOF"] * 6,
        }
    )


def _rows(**columns: list[object]) -> pd.DataFrame:
    return pd.DataFrame(columns)


class TestSimilarityPass:
    """Rows without an equal row are paired when most columns agree."""

    def test_user_scenario_one_changed_cell(self) -> None:
        # File 1 had Sum_in_from_sum_out of player 998702019 changed 100 → 1000;
        # file 2 has the same rows in another order.
        file2 = _bets().iloc[[5, 3, 0, 4, 2, 1]].reset_index(drop=True)
        file1 = _bets()
        file1.loc[1, "Sum_in_from_sum_out"] = 1000.0

        alignment = align_unordered(file1, file2, list(file1.columns))
        match = alignment.row_match
        assert match["similar"] == 1
        assert match["modified"] == 1
        assert match["equal"] == 5
        assert match["only_in_file1"] == 0
        assert match["only_in_file2"] == 0

        mask = alignment.differences_mask
        assert mask.sum().sum() == 1
        assert bool(mask.loc[1, "Sum_in_from_sum_out"]) is True
        pair = alignment.row_pairs.loc[1]
        assert (pair["row_file1"], pair["row_file2"], pair["status"]) == (1, 5, STATUS_SIMILAR)
        assert alignment.file2_data.loc[1, "Sum_in_from_sum_out"] == 100.0

    def test_tie_leaves_rows_unpaired(self) -> None:
        # The only differing column is idUser, and two players of file 2 are
        # equally close to the player of file 1: no way to tell which one.
        zero_row = {name: values[3] for name, values in _bets().to_dict("list").items()}
        base = _bets().iloc[:3]
        file1 = pd.concat([base, pd.DataFrame([zero_row])], ignore_index=True)
        others = pd.DataFrame([{**zero_row, "idUser": 1}, {**zero_row, "idUser": 2}])
        file2 = pd.concat([base, others], ignore_index=True)

        match = align_unordered(file1, file2, list(file1.columns)).row_match
        assert match["similar"] == 0
        assert match["only_in_file1"] == 1
        assert match["only_in_file2"] == 2

    def test_rows_differing_in_most_columns_stay_unpaired(self) -> None:
        file1 = _rows(dt=["d"], idUser=["u1"], a=[10], b=[20], c=[30])
        file2 = _rows(dt=["d"], idUser=["u2"], a=[11], b=[21], c=[30])
        match = align_unordered(file1, file2, list(file1.columns)).row_match
        assert match["similar"] == 0
        assert (match["only_in_file1"], match["only_in_file2"]) == (1, 1)

    def test_rare_equal_value_beats_more_common_ones(self) -> None:
        # Z agrees with R in more columns, but only in values every row has;
        # R2 shares the player id, which is rare. R2 must win.
        n = 20
        background = _rows(
            dt=["d"] * n,
            idUser=list(range(100, 100 + n)),
            a=[5] * n,
            b=[0] * n,
            c=[0] * n,
            cur=["X"] * n,
        )
        r = _rows(dt=["d"], idUser=[7], a=[5], b=[0], c=[0], cur=["X"])
        z = _rows(dt=["d"], idUser=[8], a=[5], b=[0], c=[0], cur=["X"])
        r2 = _rows(dt=["d"], idUser=[7], a=[9], b=[1], c=[0], cur=["X"])
        file1 = pd.concat([background, r], ignore_index=True)
        file2 = pd.concat([background, z, r2], ignore_index=True)

        alignment = align_unordered(file1, file2, list(file1.columns))
        assert alignment.row_match["similar"] == 1
        assert alignment.row_match["only_in_file2"] == 1
        pairs = alignment.row_pairs.set_index("row_file1")
        assert pairs.loc[20, "row_file2"] == 21  # R ↔ R2, not R ↔ Z (20)

    def test_duplicates_changed_the_same_way_are_paired(self) -> None:
        file1 = _rows(id=["u1", "u1", "u9"], v=[10.0, 10.0, 3.0], cur=["X"] * 3)
        file2 = _rows(id=["u9", "u1", "u1"], v=[3.0, 11.0, 11.0], cur=["X"] * 3)
        match = align_unordered(file1, file2, list(file1.columns)).row_match
        assert match["similar"] == 2
        assert (match["only_in_file1"], match["only_in_file2"]) == (0, 0)

    def test_duplicates_go_to_equally_good_partners(self) -> None:
        # Two copies of one row and two different, equally close partners:
        # whichever copy goes where, the outcome is the same.
        file1 = _rows(id=["u1", "u1", "u9"], a=[10, 10, 1], b=[20, 20, 2])
        file2 = _rows(id=["u1", "u1", "u9"], a=[11, 10, 1], b=[20, 21, 2])
        match = align_unordered(file1, file2, list(file1.columns)).row_match
        assert match["similar"] == 2
        assert (match["only_in_file1"], match["only_in_file2"]) == (0, 0)

    def test_key_columns_turn_the_pass_off(self) -> None:
        file1 = _rows(idUser=["u1", "u2"], Sum=[10.0, 20.0])
        file2 = _rows(idUser=["u1", "u3"], Sum=[10.0, 20.0])
        columns = list(file1.columns)

        by_key = align_unordered(file1, file2, columns, key_columns=["idUser"]).row_match
        assert by_key["similar"] == 0
        assert (by_key["only_in_file1"], by_key["only_in_file2"]) == (1, 1)

        by_row = align_unordered(file1, file2, columns).row_match
        assert by_row["similar"] == 1

    def test_single_column_is_never_paired_by_similarity(self) -> None:
        match = align_unordered(_rows(a=[1, 5]), _rows(a=[1, 6]), ["a"]).row_match
        assert match["similar"] == 0
        assert (match["only_in_file1"], match["only_in_file2"]) == (1, 1)

    def test_pairs_do_not_depend_on_row_order(self) -> None:
        rng = np.random.default_rng(7)
        base = pd.DataFrame(
            {
                "dt": rng.choice(["2026-09-01", "2026-09-02"], 60),
                "idUser": rng.permutation(60) + 1000,
                "Sum_bets": rng.choice([0.0, 100.0, 250.5, 1000.0], 60),
                "Number_of_bets": rng.integers(0, 5, 60),
                "Currency": ["XOF"] * 60,
            }
        )
        changed = base.copy()
        changed.loc[[3, 17, 42], "Sum_bets"] += 1.0
        changed.loc[25, "Number_of_bets"] += 1

        def similar_pairs(file2: pd.DataFrame) -> set[tuple[tuple[object, ...], ...]]:
            alignment = align_unordered(base, file2, list(base.columns))
            rows = np.flatnonzero(alignment.row_pairs["status"] == STATUS_SIMILAR)
            return {
                (tuple(alignment.file1_data.iloc[i]), tuple(alignment.file2_data.iloc[i]))
                for i in rows
            }

        first = similar_pairs(changed.sample(frac=1, random_state=1).reset_index(drop=True))
        second = similar_pairs(changed.sample(frac=1, random_state=2).reset_index(drop=True))
        assert len(first) == 4
        assert first == second

    def test_candidate_budget_keeps_the_most_selective_blocks(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # With room for one candidate, the block of the rare id is kept.
        monkeypatch.setattr(row_matching, "_MAX_CANDIDATE_PAIRS", 1)
        background = _rows(dt=["d"] * 5, idUser=list(range(5)), a=[5] * 5, cur=["X"] * 5)
        file1 = pd.concat([background, _rows(dt=["d"], idUser=[7], a=[5], cur=["X"])])
        file2 = pd.concat(
            [
                background,
                _rows(dt=["d"], idUser=[8], a=[5], cur=["X"]),
                _rows(dt=["d"], idUser=[7], a=[9], cur=["X"]),
            ]
        )
        alignment = align_unordered(file1, file2, list(file1.columns))
        assert alignment.row_match["similar"] == 1
        assert alignment.row_pairs.set_index("row_file1").loc[5, "row_file2"] == 6


class TestRowPairs:
    def test_positions_and_statuses(self) -> None:
        file1 = _rows(id=["a", "b", "c"], v=[1.0, 2.0, 3.0])
        file2 = _rows(id=["d", "b", "a"], v=[9.0, 2.5, 1.0])
        pairs = align_unordered(file1, file2, ["id", "v"]).row_pairs
        assert pairs.to_dict("list") == {
            "row_file1": [0, 1, 2, -1],
            "row_file2": [2, 1, -1, 0],
            "status": [STATUS_EQUAL, STATUS_SIMILAR, STATUS_ONLY_FILE1, STATUS_ONLY_FILE2],
        }

    def test_key_pair_with_differences_is_modified(self, df_base: pd.DataFrame) -> None:
        changed = df_base.copy()
        changed.loc[1, "Sum_bets"] = 1300.75
        result = align_unordered(
            df_base, changed, list(df_base.columns), key_columns=["dt", "idUser"]
        ).to_result({})
        assert result.row_pairs is not None
        assert result.row_pairs["status"].tolist() == [
            STATUS_EQUAL,
            STATUS_MODIFIED,
            STATUS_EQUAL,
        ]

    def test_positional_advanced_pads_the_shorter_file(self) -> None:
        file1 = _rows(id=[1, 2, 3], name=["a", "b", "c"])
        file2 = _rows(id=[1, 2], name=["a", "B"])
        result = AdvancedComparator().compare(file1, file2)
        assert result.row_pairs is not None
        assert result.row_pairs.to_dict("list") == {
            "row_file1": [0, 1, 2],
            "row_file2": [0, 1, -1],
            "status": [STATUS_EQUAL, STATUS_MODIFIED, STATUS_ONLY_FILE1],
        }

    def test_positional_basic(self) -> None:
        file1 = _rows(id=[1, 2], name=["a", "b"])
        file2 = _rows(id=[1, 2], name=["a", "B"])
        result = BasicComparator().compare(file1, file2)
        assert result.row_pairs is not None
        assert result.row_pairs["status"].tolist() == [STATUS_EQUAL, STATUS_MODIFIED]


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
