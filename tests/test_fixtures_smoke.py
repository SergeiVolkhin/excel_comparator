"""Smoke tests ensuring the generated xlsx fixtures are well-formed."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import xlsx_to_dict


def test_identical_pair_readable(identical_xlsx_pair: tuple[Path, Path]) -> None:
    a, b = identical_xlsx_pair
    assert xlsx_to_dict(a) == xlsx_to_dict(b)


def test_value_diff_pair_differs(value_diff_xlsx_pair: tuple[Path, Path]) -> None:
    a, b = value_diff_xlsx_pair
    assert xlsx_to_dict(a) != xlsx_to_dict(b)


def test_multi_sheet_pair_has_two_sheets(multi_sheet_xlsx_pair: tuple[Path, Path]) -> None:
    a, _ = multi_sheet_xlsx_pair
    assert set(xlsx_to_dict(a).keys()) == {"Main", "Extra"}


def test_formulas_pair_stores_values(formulas_xlsx_pair: tuple[Path, Path]) -> None:
    a, _ = formulas_xlsx_pair
    data = xlsx_to_dict(a)
    assert data["Sheet1"][0] == ["id", "x", "y", "sum"]


@pytest.mark.slow
def test_large_pair_generates(large_xlsx_pair: tuple[Path, Path]) -> None:
    a, b = large_xlsx_pair
    assert a.stat().st_size > 100_000
    assert b.stat().st_size > 100_000
