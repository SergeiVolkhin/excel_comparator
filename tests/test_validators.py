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

    def test_for_csv_extends_standard_with_csv_rules(self) -> None:
        from src.validators.csv_validators import (
            CSVRowCountRatioValidator,
            CSVSingleColumnCollapseValidator,
        )

        rules = ValidationRuleFactory.for_csv()
        assert any(isinstance(r, CSVRowCountRatioValidator) for r in rules)
        assert any(isinstance(r, CSVSingleColumnCollapseValidator) for r in rules)
        # Plus all standard rules still present.
        assert any(isinstance(r, ShapeValidationRule) for r in rules)


class TestCSVRowCountRatio:
    def test_equal_sizes_no_error(self) -> None:
        from src.validators.csv_validators import CSVRowCountRatioValidator

        df = pd.DataFrame({"a": range(50)})
        assert CSVRowCountRatioValidator().validate(df, df.copy()) == []

    def test_modest_imbalance_no_error(self) -> None:
        from src.validators.csv_validators import CSVRowCountRatioValidator

        df1 = pd.DataFrame({"a": range(100)})
        df2 = pd.DataFrame({"a": range(500)})  # 5x
        assert CSVRowCountRatioValidator().validate(df1, df2) == []

    def test_huge_imbalance_reported(self) -> None:
        from src.validators.csv_validators import CSVRowCountRatioValidator

        df1 = pd.DataFrame({"a": [1]})
        df2 = pd.DataFrame({"a": range(500)})  # 500x
        errors = CSVRowCountRatioValidator().validate(df1, df2)
        assert len(errors) == 1
        assert "разделитель" in errors[0]

    def test_empty_side_silent(self) -> None:
        from src.validators.csv_validators import CSVRowCountRatioValidator

        df1 = pd.DataFrame({"a": []})
        df2 = pd.DataFrame({"a": range(500)})
        # EmptyDataValidationRule handles empty-data; this rule stays silent.
        assert CSVRowCountRatioValidator().validate(df1, df2) == []

    def test_custom_threshold(self) -> None:
        from src.validators.csv_validators import CSVRowCountRatioValidator

        df1 = pd.DataFrame({"a": [1]})
        df2 = pd.DataFrame({"a": [1, 2, 3, 4, 5]})  # 5x
        rule = CSVRowCountRatioValidator(max_ratio=3.0)
        assert rule.validate(df1, df2)  # triggers at 3x threshold

    def test_rule_name(self) -> None:
        from src.validators.csv_validators import CSVRowCountRatioValidator

        assert "CSV" in CSVRowCountRatioValidator().get_rule_name()


class TestCSVSingleColumnCollapse:
    def test_well_structured_two_column_no_error(self) -> None:
        from src.validators.csv_validators import CSVSingleColumnCollapseValidator

        df = pd.DataFrame({"id": [1, 2], "name": ["a", "b"]})
        assert CSVSingleColumnCollapseValidator().validate(df, df.copy()) == []

    def test_collapsed_column_with_commas_reported(self) -> None:
        from src.validators.csv_validators import CSVSingleColumnCollapseValidator

        collapsed = pd.DataFrame({"id,name,score": ["1,A,10", "2,B,20", "3,C,30"]})
        clean = pd.DataFrame({"id": [1, 2, 3]})
        errors = CSVSingleColumnCollapseValidator().validate(collapsed, clean)
        assert len(errors) == 1
        assert "первом" in errors[0]

    def test_numeric_single_column_not_collapsed(self) -> None:
        # A single numeric column is normal (e.g. a list of IDs) and must
        # not trigger the heuristic.
        from src.validators.csv_validators import CSVSingleColumnCollapseValidator

        df = pd.DataFrame({"id": [1, 2, 3, 4, 5]})
        assert CSVSingleColumnCollapseValidator().validate(df, df.copy()) == []

    def test_single_string_column_without_delimiters_clean(self) -> None:
        from src.validators.csv_validators import CSVSingleColumnCollapseValidator

        df = pd.DataFrame({"name": ["Alice", "Bob", "Charlie"]})
        assert CSVSingleColumnCollapseValidator().validate(df, df.copy()) == []

    def test_both_sides_collapsed_two_errors(self) -> None:
        from src.validators.csv_validators import CSVSingleColumnCollapseValidator

        a = pd.DataFrame({"a,b": ["1,2", "3,4"]})
        b = pd.DataFrame({"c;d": ["5;6", "7;8"]})
        errors = CSVSingleColumnCollapseValidator().validate(a, b)
        assert len(errors) == 2

    def test_rule_name(self) -> None:
        from src.validators.csv_validators import CSVSingleColumnCollapseValidator

        assert "CSV" in CSVSingleColumnCollapseValidator().get_rule_name()
