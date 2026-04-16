"""
Базовые валидаторы для проверки данных перед сравнением
"""

import logging
from typing import Any

import pandas as pd

from ..core.interfaces import IValidationRule


class ShapeValidationRule(IValidationRule):
    """Правило валидации размеров DataFrames"""

    def __init__(self) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)

    def validate(self, df1: pd.DataFrame, df2: pd.DataFrame) -> list[str]:
        """Проверяет, что размеры DataFrames совпадают"""
        errors: list[str] = []

        if df1.shape != df2.shape:
            errors.append(f"Размеры файлов не совпадают: {df1.shape} vs {df2.shape}")
            self.logger.warning(f"Несовпадение размеров: {df1.shape} vs {df2.shape}")

        return errors

    def get_rule_name(self) -> str:
        return "Проверка размеров"


class ColumnNamesValidationRule(IValidationRule):
    """Правило валидации названий столбцов"""

    def __init__(self, strict_mode: bool = True):
        self.strict_mode = strict_mode
        self.logger = logging.getLogger(self.__class__.__name__)

    def validate(self, df1: pd.DataFrame, df2: pd.DataFrame) -> list[str]:
        """Проверяет совпадение названий столбцов"""
        errors = []

        if not df1.columns.equals(df2.columns):
            if self.strict_mode:
                errors.append("Названия столбцов не совпадают")
                self.logger.warning("Несовпадение названий столбцов")
            else:
                # В нестрогом режиме только предупреждаем
                missing_in_df2 = set(df1.columns) - set(df2.columns)
                missing_in_df1 = set(df2.columns) - set(df1.columns)

                if missing_in_df2:
                    self.logger.warning(f"Столбцы отсутствуют во втором файле: {missing_in_df2}")

                if missing_in_df1:
                    self.logger.warning(f"Столбцы отсутствуют в первом файле: {missing_in_df1}")

        return errors

    def get_rule_name(self) -> str:
        mode = "строгая" if self.strict_mode else "мягкая"
        return f"Проверка названий столбцов ({mode})"


class DataTypeValidationRule(IValidationRule):
    """Правило валидации типов данных"""

    def __init__(self, check_compatibility: bool = True):
        self.check_compatibility = check_compatibility
        self.logger = logging.getLogger(self.__class__.__name__)

    def validate(self, df1: pd.DataFrame, df2: pd.DataFrame) -> list[str]:
        """Проверяет совместимость типов данных"""
        errors: list[str] = []

        if not self.check_compatibility:
            return errors

        # Проверяем только общие столбцы
        common_columns = set(df1.columns) & set(df2.columns)

        incompatible_columns: list[str] = []
        for col in common_columns:
            type1 = df1[col].dtype
            type2 = df2[col].dtype

            if not self._are_types_compatible(type1, type2):
                incompatible_columns.append(f"{col} ({type1} vs {type2})")
                self.logger.warning(f"Несовместимые типы в столбце {col}: {type1} vs {type2}")

        if incompatible_columns:
            errors.append(f"Несовместимые типы данных: {', '.join(incompatible_columns)}")

        return errors

    def _are_types_compatible(self, type1: Any, type2: Any) -> bool:
        """Проверяет совместимость типов данных"""
        # Числовые типы совместимы между собой
        numeric_types = ["int64", "int32", "float64", "float32"]
        if str(type1) in numeric_types and str(type2) in numeric_types:
            return True

        # Строковые типы и object совместимы
        string_types = ["object", "string"]
        if str(type1) in string_types and str(type2) in string_types:
            return True

        # Точное совпадение
        return bool(type1 == type2)

    def get_rule_name(self) -> str:
        return "Проверка типов данных"


class EmptyDataValidationRule(IValidationRule):
    """Правило валидации пустых данных"""

    def __init__(self, allow_empty_cells: bool = True):
        self.allow_empty_cells = allow_empty_cells
        self.logger = logging.getLogger(self.__class__.__name__)

    def validate(self, df1: pd.DataFrame, df2: pd.DataFrame) -> list[str]:
        """Проверяет наличие данных"""
        errors = []

        # Проверяем пустые DataFrames
        if df1.empty:
            errors.append("Первый файл не содержит данных")

        if df2.empty:
            errors.append("Второй файл не содержит данных")

        if errors:
            return errors

        # Проверяем количество пустых ячеек
        if not self.allow_empty_cells:
            empty_cells_df1 = df1.isnull().sum().sum()
            empty_cells_df2 = df2.isnull().sum().sum()

            if empty_cells_df1 > 0:
                errors.append(f"Первый файл содержит {empty_cells_df1} пустых ячеек")

            if empty_cells_df2 > 0:
                errors.append(f"Второй файл содержит {empty_cells_df2} пустых ячеек")

        return errors

    def get_rule_name(self) -> str:
        return "Проверка пустых данных"


class SizeValidationRule(IValidationRule):
    """Правило валидации размера данных"""

    def __init__(self, max_rows: int = 100000, max_columns: int = 1000):
        self.max_rows = max_rows
        self.max_columns = max_columns
        self.logger = logging.getLogger(self.__class__.__name__)

    def validate(self, df1: pd.DataFrame, df2: pd.DataFrame) -> list[str]:
        """Проверяет размер данных"""
        errors = []

        # Проверяем количество строк
        if df1.shape[0] > self.max_rows:
            errors.append(
                f"Первый файл слишком большой: {df1.shape[0]} строк (максимум {self.max_rows})"
            )

        if df2.shape[0] > self.max_rows:
            errors.append(
                f"Второй файл слишком большой: {df2.shape[0]} строк (максимум {self.max_rows})"
            )

        # Проверяем количество столбцов
        if df1.shape[1] > self.max_columns:
            errors.append(
                f"Первый файл содержит слишком много столбцов: {df1.shape[1]} (максимум {self.max_columns})"
            )

        if df2.shape[1] > self.max_columns:
            errors.append(
                f"Второй файл содержит слишком много столбцов: {df2.shape[1]} (максимум {self.max_columns})"
            )

        return errors

    def get_rule_name(self) -> str:
        return f"Проверка размера (макс. {self.max_rows} строк, {self.max_columns} столбцов)"


class ValidationRuleFactory:
    """Фабрика для создания валидаторов"""

    @staticmethod
    def create_standard_validators(config: Any = None) -> list[IValidationRule]:
        """Создает стандартный набор валидаторов"""
        validators = [
            EmptyDataValidationRule(),
            ShapeValidationRule(),
            ColumnNamesValidationRule(strict_mode=True),
            DataTypeValidationRule(check_compatibility=False),  # Отключаем для гибкости
        ]

        # Добавляем ограничения размера если указано в конфигурации
        if config and hasattr(config, "validation"):
            max_rows = getattr(config.validation, "max_rows", 100000)
            max_columns = getattr(config.validation, "max_columns", 1000)
            validators.append(SizeValidationRule(max_rows, max_columns))
        else:
            validators.append(SizeValidationRule())

        return validators

    @staticmethod
    def create_lenient_validators() -> list[IValidationRule]:
        """Создает мягкий набор валидаторов"""
        return [
            EmptyDataValidationRule(),
            ColumnNamesValidationRule(strict_mode=False),
            SizeValidationRule(max_rows=500000, max_columns=5000),
        ]

    @staticmethod
    def create_strict_validators() -> list[IValidationRule]:
        """Создает строгий набор валидаторов"""
        return [
            EmptyDataValidationRule(allow_empty_cells=False),
            ShapeValidationRule(),
            ColumnNamesValidationRule(strict_mode=True),
            DataTypeValidationRule(check_compatibility=True),
            SizeValidationRule(max_rows=50000, max_columns=500),
        ]
