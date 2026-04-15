"""
Форматтер для вывода результатов в Excel
"""

from pathlib import Path
from typing import List, Dict, Any
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils.dataframe import dataframe_to_rows
from openpyxl.cell.cell import MergedCell
import logging

from ..core.interfaces import IOutputFormatter, ComparisonResult, IDifferenceAnalyzer
from ..core.exceptions import ApplicationError
from ..analyzers.list_analyzer import ListDifferenceAnalyzer, BasicDifferenceAnalyzer


class ExcelOutputFormatter(IOutputFormatter):
    """Форматтер для вывода результатов сравнения в Excel"""
    
    SUPPORTED_FORMATS = ['.xlsx']
    
    def __init__(self, config=None):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.config = config
        
        # Настройки стилей
        self.highlight_fill = PatternFill(
            start_color=getattr(config.comparison, 'highlight_color', 'FFFF00') if config else 'FFFF00',
            end_color=getattr(config.comparison, 'highlight_color', 'FFFF00') if config else 'FFFF00',
            fill_type='solid'
        )
        
        self.header_fill = PatternFill(
            start_color='E6E6FA',
            end_color='E6E6FA',
            fill_type='solid'
        )
        
        self.header_font = Font(bold=True, size=12)
        self.center_align = Alignment(horizontal='center', vertical='center')
        
        # Границы
        self.thin_border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )
        
        # Анализаторы различий
        self.analyzers = [
            ListDifferenceAnalyzer(
                separator=getattr(config.comparison, 'list_separator', ',') if config else ','
            ),
            BasicDifferenceAnalyzer()
        ]
    
    def format(self, result: ComparisonResult, output_path: Path, **options) -> None:
        """Форматирует и сохраняет результат сравнения в Excel"""
        try:
            self.logger.info(f"Создание Excel отчета: {output_path}")
            
            # Создаем рабочую книгу
            workbook = Workbook()
            
            # Удаляем лист по умолчанию
            workbook.remove(workbook.active)
            
            # Добавляем листы с данными
            self._add_comparison_sheets(workbook, result, options)
            
            # Добавляем лист со сводкой
            self._add_summary_sheet(workbook, result)
            
            # Сохраняем файл
            workbook.save(output_path)
            
            self.logger.info(f"Excel отчет успешно создан: {output_path}")
            
        except Exception as e:
            self.logger.error(f"Ошибка создания Excel отчета: {e}", exc_info=True)
            raise ApplicationError(f"Не удалось создать отчет: {e}")
    
    def get_supported_formats(self) -> List[str]:
        """Возвращает список поддерживаемых форматов"""
        return self.SUPPORTED_FORMATS.copy()
    
    def _add_comparison_sheets(self, workbook: Workbook, result: ComparisonResult, options: dict) -> None:
        """Добавляет листы с результатами сравнения"""
        file1_name = options.get('file1_name', 'Файл 1')
        file2_name = options.get('file2_name', 'Файл 2')
        
        # Обрезаем имена листов до 30 символов
        sheet1_name = file1_name[:30]
        sheet2_name = file2_name[:30]
        
        # Создаем столбцы с различиями
        diff_column1 = self._create_differences_column(
            result.file1_data, result.file2_data, result.differences_mask
        )
        diff_column2 = self._create_differences_column(
            result.file2_data, result.file1_data, result.differences_mask
        )
        
        # Добавляем данные к DataFrame
        result1_df = result.file1_data.copy()
        result1_df['Различия'] = diff_column1
        
        result2_df = result.file2_data.copy()
        result2_df['Различия'] = diff_column2
        
        # Создаем листы
        self._create_data_sheet(workbook, sheet1_name, result1_df, result.differences_mask)
        self._create_data_sheet(workbook, sheet2_name, result2_df, result.differences_mask)
    
    def _create_data_sheet(self, workbook: Workbook, sheet_name: str, 
                          data_df: pd.DataFrame, mask: pd.DataFrame) -> None:
        """Создает лист с данными и применяет форматирование"""
        worksheet = workbook.create_sheet(title=sheet_name)
        
        # Добавляем данные
        for row in dataframe_to_rows(data_df, index=False, header=True):
            worksheet.append(row)
        
        # Применяем стили к заголовкам
        for col_num, cell in enumerate(worksheet[1], 1):
            cell.fill = self.header_fill
            cell.font = self.header_font
            cell.alignment = self.center_align
            cell.border = self.thin_border
        
        # Применяем подсветку к различающимся ячейкам
        for row_idx, row in mask.iterrows():
            for col_idx, is_different in enumerate(row):
                if is_different:
                    cell = worksheet.cell(row=row_idx + 2, column=col_idx + 1)
                    cell.fill = self.highlight_fill
                    cell.border = self.thin_border
        
        # Автоподбор ширины столбцов
        self._auto_adjust_columns(worksheet)
    
    def _create_differences_column(self, base_df: pd.DataFrame, 
                                 other_df: pd.DataFrame, mask: pd.DataFrame) -> pd.Series:
        """Создает столбец с описанием различий"""
        differences = []
        
        for idx in base_df.index:
            row_differences = []
            
            for col in base_df.columns:
                if not mask.at[idx, col]:
                    continue
                
                old_value = base_df.at[idx, col]
                new_value = other_df.at[idx, col]
                
                # Находим подходящий анализатор
                analyzer = self._find_analyzer(old_value, new_value)
                
                try:
                    detail = analyzer.analyze(old_value, new_value, col)
                    row_differences.append(f"{col}: {detail.description}")
                except Exception as e:
                    self.logger.warning(f"Ошибка анализа различий для {col}: {e}")
                    row_differences.append(f"{col}: {old_value} → {new_value}")
            
            differences.append(' | '.join(row_differences))
        
        return pd.Series(differences, index=base_df.index, name='Различия')
    
    def _find_analyzer(self, old_value: Any, new_value: Any) -> IDifferenceAnalyzer:
        """Находит подходящий анализатор для значений"""
        for analyzer in self.analyzers:
            if analyzer.can_analyze(old_value, new_value):
                return analyzer
        
        # Возвращаем базовый анализатор, если никто не подошел
        return self.analyzers[-1]
    
    def _add_summary_sheet(self, workbook: Workbook, result: ComparisonResult) -> None:
        """Добавляет лист со сводкой результатов"""
        worksheet = workbook.create_sheet(title="Сводка", index=0)
        
        # Заголовок
        worksheet['A1'] = "Сводка сравнения файлов"
        worksheet['A1'].font = Font(bold=True, size=16)
        worksheet['A1'].alignment = self.center_align
        worksheet.merge_cells('A1:B1')
        
        # Статистика
        row = 3
        stats = [
            ("Общее количество ячеек:", result.metadata['total_cells']),
            ("Ячеек с различиями:", result.metadata['different_cells']),
            ("Процент схожести:", f"{result.metadata['similarity_percentage']:.2f}%"),
            ("Размер данных:", f"{result.metadata['shape'][0]} строк × {result.metadata['shape'][1]} столбцов"),
        ]
        
        for label, value in stats:
            worksheet[f'A{row}'] = label
            worksheet[f'B{row}'] = value
            worksheet[f'A{row}'].font = Font(bold=True)
            row += 1
        
        # Различия по столбцам
        row += 2
        worksheet[f'A{row}'] = "Различия по столбцам:"
        worksheet[f'A{row}'].font = Font(bold=True, size=14)
        row += 1
        
        # Заголовки таблицы
        worksheet[f'A{row}'] = "Столбец"
        worksheet[f'B{row}'] = "Количество различий"
        worksheet[f'C{row}'] = "Процент различий"
        
        for col in ['A', 'B', 'C']:
            worksheet[f'{col}{row}'].font = self.header_font
            worksheet[f'{col}{row}'].fill = self.header_fill
            worksheet[f'{col}{row}'].border = self.thin_border
        
        row += 1
        
        # Статистика по столбцам
        for col_name in result.differences_mask.columns:
            diff_count = result.differences_mask[col_name].sum()
            diff_percentage = (diff_count / len(result.differences_mask)) * 100
            
            worksheet[f'A{row}'] = col_name
            worksheet[f'B{row}'] = diff_count
            worksheet[f'C{row}'] = f"{diff_percentage:.1f}%"
            
            for col in ['A', 'B', 'C']:
                worksheet[f'{col}{row}'].border = self.thin_border
            
            row += 1
        
        # Автоподбор ширины столбцов
        self._auto_adjust_columns(worksheet)
    
    def _auto_adjust_columns(self, worksheet) -> None:
        """Автоматически подбирает ширину столбцов"""
        for column in worksheet.columns:
            max_length = 0
            column_letter = None
            
            # Находим первую нормальную ячейку в столбце, чтобы получить column_letter
            for cell in column:
                if not isinstance(cell, MergedCell):
                    column_letter = cell.column_letter
                    break
            
            # Если не удалось найти column_letter, пропускаем этот столбец
            if column_letter is None:
                self.logger.warning(f"Не удалось определить column_letter для столбца, возможно все ячейки объединены")
                continue
            
            # Теперь определяем максимальную длину значения в столбце
            for cell in column:
                try:
                    if cell.value and len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except (TypeError, AttributeError):
                    # Игнорируем ошибки при обработке null-значений или объединенных ячеек
                    pass
            
            # Устанавливаем ширину столбца, ограничивая максимальное значение
            adjusted_width = min(max_length + 2, 50)  # Максимум 50 символов
            worksheet.column_dimensions[column_letter].width = adjusted_width