"""
Базовый компаратор для сравнения DataFrames
"""

import pandas as pd
import numpy as np
from typing import Any, Dict
import logging

from ..core.interfaces import IComparator, ComparisonResult
from ..core.exceptions import ComparisonError


class BasicComparator(IComparator):
    """Базовый компаратор для сравнения DataFrames"""
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self._na_marker = object()  # Уникальный объект для обозначения NaN
    
    def compare(self, df1: pd.DataFrame, df2: pd.DataFrame, **options) -> ComparisonResult:
        """Сравнивает два DataFrame и возвращает результат"""
        
        # Валидация входных данных
        self._validate_dataframes(df1, df2)
        
        # Опции сравнения
        ignore_case = options.get('ignore_case', False)
        ignore_whitespace = options.get('ignore_whitespace', False)
        
        self.logger.info(f"Начало сравнения DataFrames {df1.shape} vs {df2.shape}")
        
        # Предобработка данных
        processed_df1 = self._preprocess_dataframe(df1, ignore_case, ignore_whitespace)
        processed_df2 = self._preprocess_dataframe(df2, ignore_case, ignore_whitespace)
        
        # Создание маски различий
        differences_mask = self._create_differences_mask(processed_df1, processed_df2)
        
        # Подсчет статистики
        total_cells = df1.size
        different_cells = differences_mask.sum().sum()
        
        metadata = {
            'total_cells': total_cells,
            'different_cells': different_cells,
            'similarity_percentage': ((total_cells - different_cells) / total_cells) * 100,
            'comparison_options': options,
            'shape': df1.shape
        }
        
        self.logger.info(
            f"Сравнение завершено: {different_cells}/{total_cells} различий "
            f"({metadata['similarity_percentage']:.2f}% схожести)"
        )
        
        return ComparisonResult(
            differences_mask=differences_mask,
            file1_data=df1.copy(),
            file2_data=df2.copy(),
            metadata=metadata
        )
    
    def get_name(self) -> str:
        """Возвращает название компаратора"""
        return "Базовое сравнение"
    
    def _validate_dataframes(self, df1: pd.DataFrame, df2: pd.DataFrame) -> None:
        """Валидирует DataFrames перед сравнением"""
        if df1.shape != df2.shape:
            raise ComparisonError(
                f"Размеры DataFrames не совпадают: {df1.shape} vs {df2.shape}"
            )
        
        if not df1.columns.equals(df2.columns):
            raise ComparisonError("Названия столбцов не совпадают")
        
        if df1.empty or df2.empty:
            raise ComparisonError("Один из DataFrames пустой")
    
    def _preprocess_dataframe(
        self, 
        df: pd.DataFrame, 
        ignore_case: bool = False, 
        ignore_whitespace: bool = False
    ) -> pd.DataFrame:
        """Предобрабатывает DataFrame для сравнения"""
        result_df = df.copy()
        
        if ignore_case or ignore_whitespace:
            # Применяем обработку только к строковым столбцам
            for col in result_df.columns:
                if result_df[col].dtype == 'object':
                    # Обрабатываем только строковые значения
                    mask = result_df[col].astype(str) != 'nan'
                    
                    if ignore_case:
                        result_df.loc[mask, col] = result_df.loc[mask, col].astype(str).str.lower()
                    
                    if ignore_whitespace:
                        result_df.loc[mask, col] = result_df.loc[mask, col].astype(str).str.strip()
        
        return result_df
    
    def _create_differences_mask(self, df1: pd.DataFrame, df2: pd.DataFrame) -> pd.DataFrame:
        """Создает маску различий между двумя DataFrames"""
        # Заменяем NaN на уникальный маркер для корректного сравнения
        df1_filled = df1.fillna(self._na_marker)
        df2_filled = df2.fillna(self._na_marker)
        
        # Создаем маску различий
        differences_mask = df1_filled.values != df2_filled.values
        
        return pd.DataFrame(
            differences_mask,
            columns=df1.columns,
            index=df1.index
        )
    
    def get_differences_summary(self, result: ComparisonResult) -> Dict[str, Any]:
        """Возвращает сводку различий"""
        mask = result.differences_mask
        
        # Различия по столбцам
        column_differences = {}
        for col in mask.columns:
            diff_count = mask[col].sum()
            if diff_count > 0:
                column_differences[col] = {
                    'count': diff_count,
                    'percentage': (diff_count / len(mask)) * 100
                }
        
        # Строки с различиями
        rows_with_differences = mask.any(axis=1).sum()
        
        return {
            'column_differences': column_differences,
            'rows_with_differences': rows_with_differences,
            'total_different_cells': mask.sum().sum(),
            'most_different_column': max(column_differences.keys(), 
                                       key=lambda x: column_differences[x]['count'])
                                     if column_differences else None
        }