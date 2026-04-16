"""Characterization tests for src/validators/base_validators.py."""

from __future__ import annotations

import pandas as pd
import pytest

from src.validators.base_validators import (
    ColumnNamesValidationRule,
    DataTypeValidationRule,
    EmptyDataValidationRule,
    ShapeValidationRule,
    SizeValidationRule,
    ValidationRuleFactory,
)


@pytest.fixture
def df_base() -> pd.DataFrame:
    return pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})


class TestShapeRule:
    def test_equal_shape_no_errors(self, df_base: pd.DataFrame) -> None:
        errors = ShapeValidationRule().validate(df_base, df_base.copy())
        assert errors == []

    def test_different_shape_reports_error(self, df_base: pd.DataFrame) -> None:
        df2 = pd.DataFrame({"a": [1], "b": ["x"]})
        errors = ShapeValidationRule().validate(df_base, df2)
        assert errors and "Размеры" in errors[0]

    def test_rule_name(self) -> None:
        assert ShapeValidationRule().get_rule_name() == "Проверка размеров"


class TestColumnNamesRule:
    def test_strict_same_cols(self, df_base: pd.DataFrame) -> None:
        assert ColumnNamesValidationRule(strict_mode=True).validate(df_base, df_base.copy()) == []

    def test_strict_diff_cols_errors(self, df_base: pd.DataFrame) -> None:
        df2 = pd.DataFrame({"a": [1, 2], "c": ["x", "y"]})
        errors = ColumnNamesValidationRule(strict_mode=True).validate(df_base, df2)
        assert errors and "столбцов" in errors[0]

    def test_lenient_diff_cols_no_errors(self, df_base: pd.DataFrame) -> None:
        df2 = pd.DataFrame({"a": [1, 2], "c": ["x", "y"]})
        errors = ColumnNamesValidationRule(strict_mode=False).validate(df_base, df2)
        assert errors == []

    def test_rule_name_reflects_mode(self) -> None:
        assert "строгая" in ColumnNamesValidationRule(strict_mode=True).get_rule_name()
        assert "мягкая" in ColumnNamesValidationRule(strict_mode=False).get_rule_name()


class TestDataTypeRule:
    def test_compatible_numeric(self, df_base: pd.DataFrame) -> None:
        df2 = df_base.copy()
        df2["a"] = df2["a"].astype(float)
        errors = DataTypeValidationRule(check_compatibility=True).validate(df_base, df2)
        assert errors == []

    def test_incompatible_types(self, df_base: pd.DataFrame) -> None:
        df2 = pd.DataFrame({"a": ["1", "2"], "b": ["x", "y"]})
        errors = DataTypeValidationRule(check_compatibility=True).validate(df_base, df2)
        assert errors and "Несовместимые" in errors[0]

    def test_disabled_short_circuits(self, df_base: pd.DataFrame) -> None:
        df2 = pd.DataFrame({"a": ["1", "2"], "b": ["x", "y"]})
        assert DataTypeValidationRule(check_compatibility=False).validate(df_base, df2) == []


class TestEmptyDataRule:
    def test_nonempty_ok(self, df_base: pd.DataFrame) -> None:
        assert EmptyDataValidationRule().validate(df_base, df_base.copy()) == []

    def test_empty_df1(self, df_base: pd.DataFrame) -> None:
        errors = EmptyDataValidationRule().validate(pd.DataFrame(), df_base)
        assert errors and "Первый" in errors[0]

    def test_disallow_empty_cells(self) -> None:
        df1 = pd.DataFrame({"a": [1, None]})
        df2 = pd.DataFrame({"a": [1, 2]})
        errors = EmptyDataValidationRule(allow_empty_cells=False).validate(df1, df2)
        assert errors and "пустых ячеек" in errors[0]


class TestSizeRule:
    def test_within_limits(self, df_base: pd.DataFrame) -> None:
        assert SizeValidationRule().validate(df_base, df_base.copy()) == []

    def test_too_many_rows(self, df_base: pd.DataFrame) -> None:
        rule = SizeValidationRule(max_rows=1, max_columns=100)
        errors = rule.validate(df_base, df_base.copy())
        assert len(errors) == 2  # both df1 and df2

    def test_too_many_cols(self) -> None:
        df = pd.DataFrame({"a": [1], "b": [2], "c": [3]})
        rule = SizeValidationRule(max_rows=100, max_columns=2)
        errors = rule.validate(df, df.copy())
        assert all("столбцов" in e for e in errors)


class TestFactory:
    def test_standard_creates_five(self) -> None:
        assert len(ValidationRuleFactory.create_standard_validators()) == 5

    def test_lenient_skips_shape(self) -> None:
        rules = ValidationRuleFactory.create_lenient_validators()
        assert not any(isinstance(r, ShapeValidationRule) for r in rules)

    def test_strict_includes_type_check(self) -> None:
        rules = ValidationRuleFactory.create_strict_validators()
        assert any(isinstance(r, DataTypeValidationRule) for r in rules)
