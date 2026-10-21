"""
Форматтер для вывода результатов в Excel
"""

import logging
from pathlib import Path
from typing import Any, ClassVar

import numpy as np
import pandas as pd
from openpyxl import Workbook
from openpyxl.cell.cell import MergedCell
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.utils.dataframe import dataframe_to_rows

from ..analyzers.list_analyzer import BasicDifferenceAnalyzer, ListDifferenceAnalyzer
from ..comparators.row_matching import (
    STATUS_EQUAL,
    STATUS_MODIFIED,
    STATUS_ONLY_FILE1,
    STATUS_ONLY_FILE2,
    STATUS_SIMILAR,
    positional_row_pairs,
)
from ..core.exceptions import ApplicationError
from ..core.interfaces import ComparisonResult, IDifferenceAnalyzer, IOutputFormatter
from ..core.result_summary import floor_percentage

#: Excel spec caps sheet names at 31 chars; we stay one under to avoid
#: silent truncation on append when duplicate-suffix resolution kicks in.
SHEET_NAME_MAX_LEN: int = 30

#: Default hex color used for highlighting differing cells.
DEFAULT_HIGHLIGHT_COLOR: str = "FFFF00"

#: Header row background color.
HEADER_FILL_COLOR: str = "E6E6FA"

#: Column-width auto-fit samples only the first N data rows instead of the
#: whole sheet. Width is a visual estimate, so sampling keeps the cost roughly
#: constant rather than O(rows × cols) on large tables.
COLUMN_WIDTH_SAMPLE_ROWS: int = 200

#: Above this row count an Excel report is slow to build; we log a warning
#: suggesting the HTML formatter (which paginates) for large tables.
EXCEL_LARGE_ROW_THRESHOLD: int = 20_000

#: Sheet that lists only the rows with differences.
DIFFERENCES_SHEET_NAME: str = "Расхождения"

#: The differences sheet lists at most this many discrepancies (a changed
#: row takes two lines); all of them stay marked on the data sheets.
DIFFERENCES_SHEET_MAX_ITEMS: int = 50_000

#: Columns in front of the data columns on the differences sheet.
DIFFERENCES_LEAD_COLUMNS: list[str] = ["№", "Статус", "Файл", "Строка в файле"]

#: Row status → label on the differences sheet ("modified" also has a
#: "by key" variant, see ``_status_label``).
STATUS_LABELS: dict[str, str] = {
    STATUS_MODIFIED: "Изменена",
    STATUS_SIMILAR: "Изменена (по сходству)",
    STATUS_ONLY_FILE1: "Только в файле 1",
    STATUS_ONLY_FILE2: "Только в файле 2",
}

#: Summary note shown when rows were paired by the similarity pass.
SIMILARITY_NOTE: str = (
    "Пары найдены по совпадению большинства столбцов. Для точного "
    "сопоставления задайте ключевые столбцы — те, что однозначно определяют строку."
)


class ExcelOutputFormatter(IOutputFormatter):
    """Форматтер для вывода результатов сравнения в Excel"""

    SUPPORTED_FORMATS: ClassVar[list[str]] = [".xlsx"]

    def __init__(self, config: Any = None) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)
        self.config = config

        # Настройки стилей
        highlight_color = (
            getattr(config.comparison, "highlight_color", DEFAULT_HIGHLIGHT_COLOR)
            if config
            else DEFAULT_HIGHLIGHT_COLOR
        )
        self.highlight_fill = PatternFill(
            start_color=highlight_color,
            end_color=highlight_color,
            fill_type="solid",
        )

        self.header_fill = PatternFill(
            start_color=HEADER_FILL_COLOR,
            end_color=HEADER_FILL_COLOR,
            fill_type="solid",
        )

        self.header_font = Font(bold=True, size=12)
        self.center_align = Alignment(horizontal="center", vertical="center")

        # Границы
        self.thin_border = Border(
            left=Side(style="thin"),
            right=Side(style="thin"),
            top=Side(style="thin"),
            bottom=Side(style="thin"),
        )

        # Анализаторы различий
        self.analyzers = [
            ListDifferenceAnalyzer(
                separator=getattr(config.comparison, "list_separator", ",") if config else ","
            ),
            BasicDifferenceAnalyzer(),
        ]

    def format(self, result: ComparisonResult, output_path: Path, **options: Any) -> None:
        """Форматирует и сохраняет результат сравнения в Excel"""
        try:
            self.logger.info(f"Создание Excel отчета: {output_path}")

            rows = result.metadata.get("shape", (0, 0))[0]
            if rows > EXCEL_LARGE_ROW_THRESHOLD:
                self.logger.warning(
                    f"Большой объём данных ({rows} строк): формирование Excel-отчёта "
                    f"может быть медленным. Для больших таблиц рассмотрите HTML-отчёт "
                    f"(укажите расширение .html в имени выходного файла)."
                )

            # Создаем рабочую книгу
            workbook = Workbook()

            # Удаляем лист по умолчанию
            workbook.remove(workbook.active)

            row_pairs = self._row_pairs(result)

            # Добавляем листы с данными
            self._add_comparison_sheets(workbook, result, row_pairs, options)

            # Лист только с расхождениями — вторым, сразу после сводки
            self._add_differences_sheet(workbook, result, row_pairs, options)

            # Добавляем лист со сводкой
            self._add_summary_sheet(workbook, result)

            # Сохраняем файл
            workbook.save(output_path)

            self.logger.info(f"Excel отчет успешно создан: {output_path}")

        except Exception as e:
            self.logger.error(f"Ошибка создания Excel отчета: {e}", exc_info=True)
            raise ApplicationError(f"Не удалось создать отчет: {e}") from e

    def get_supported_formats(self) -> list[str]:
        """Возвращает список поддерживаемых форматов"""
        return self.SUPPORTED_FORMATS.copy()

    @staticmethod
    def _row_pairs(result: ComparisonResult) -> pd.DataFrame:
        """Пары строк результата; у собранного вручную — по позиции."""
        if result.row_pairs is not None:
            return result.row_pairs
        return positional_row_pairs(
            result.differences_mask, len(result.file1_data), len(result.file2_data)
        )

    def _add_comparison_sheets(
        self,
        workbook: Workbook,
        result: ComparisonResult,
        row_pairs: pd.DataFrame,
        options: dict[str, Any],
    ) -> None:
        """Добавляет листы с результатами сравнения"""
        file1_name = options.get("file1_name", "Файл 1")
        file2_name = options.get("file2_name", "Файл 2")

        sheet1_name = file1_name[:SHEET_NAME_MAX_LEN]
        sheet2_name = file2_name[:SHEET_NAME_MAX_LEN]

        # Столбец с различиями — один на оба листа: «файл 1 → файл 2»
        differences = self._create_differences_column(
            result.file1_data, result.file2_data, result.differences_mask, row_pairs["status"]
        ).to_numpy()

        # Добавляем данные к DataFrame
        result1_df = result.file1_data.copy()
        result1_df["Различия"] = differences

        result2_df = result.file2_data.copy()
        result2_df["Различия"] = differences

        # Создаем листы
        self._create_data_sheet(workbook, sheet1_name, result1_df, result.differences_mask)
        self._create_data_sheet(workbook, sheet2_name, result2_df, result.differences_mask)

    def _create_data_sheet(
        self, workbook: Workbook, sheet_name: str, data_df: pd.DataFrame, mask: pd.DataFrame
    ) -> None:
        """Создает лист с данными и применяет форматирование"""
        worksheet = workbook.create_sheet(title=sheet_name)

        # Добавляем данные. openpyxl не умеет писать pd.NA (в отличие от
        # numpy.nan), а advanced-сравнение добивает короткую таблицу через
        # reindex(fill_value=pd.NA). Поэтому NA меняем на None — пустую ячейку.
        for row in dataframe_to_rows(data_df, index=False, header=True):
            worksheet.append([None if pd.isna(v) else v for v in row])

        self._style_header_row(worksheet)

        # Применяем подсветку только к различающимся ячейкам.
        # Векторизация: numpy.nonzero возвращает позиции диффов одним проходом,
        # поэтому стоимость линейна от количества различий, а не от размера
        # таблицы. Это критично для больших листов с редкими изменениями.
        diff_rows, diff_cols = mask.values.nonzero()
        for row_pos, col_idx in zip(diff_rows, diff_cols, strict=True):
            cell = worksheet.cell(row=int(row_pos) + 2, column=int(col_idx) + 1)
            cell.fill = self.highlight_fill
            cell.border = self.thin_border

        # Автоподбор ширины столбцов
        self._auto_adjust_columns(worksheet)

    def _style_header_row(self, worksheet: Any) -> None:
        """Оформляет первую строку листа как заголовок таблицы."""
        for cell in worksheet[1]:
            cell.fill = self.header_fill
            cell.font = self.header_font
            cell.alignment = self.center_align
            cell.border = self.thin_border

    def _create_differences_column(
        self,
        file1_df: pd.DataFrame,
        file2_df: pd.DataFrame,
        mask: pd.DataFrame,
        statuses: pd.Series,
    ) -> pd.Series:
        """Создает столбец с описанием различий: «столбец: файл 1 → файл 2».

        Строка, которой нет в другом файле, подписывается целиком
        («Только в файле 1»), а не перечислением «значение → NULL» по
        каждой ячейке.

        Iterates only over diff positions (via ``mask.values.nonzero``)
        instead of the full ``rows × cols`` grid. For sparse differences
        this is roughly O(diffs) vs the previous O(rows × cols).
        """
        cols = list(file1_df.columns)
        values1 = file1_df.values
        values2 = file2_df.values
        status_values = statuses.to_numpy()
        diff_rows, diff_cols = mask.values.nonzero()

        by_row: dict[int, list[str]] = {}
        for r, c in zip(diff_rows, diff_cols, strict=True):
            if status_values[r] in (STATUS_ONLY_FILE1, STATUS_ONLY_FILE2):
                continue
            message = self._describe_change(cols[c], values1[r, c], values2[r, c])
            by_row.setdefault(int(r), []).append(message)

        descriptions = [
            STATUS_LABELS[status_values[i]]
            if status_values[i] in (STATUS_ONLY_FILE1, STATUS_ONLY_FILE2)
            else " | ".join(by_row.get(i, []))
            for i in range(len(file1_df))
        ]
        return pd.Series(descriptions, index=file1_df.index, name="Различия")

    def _describe_change(self, column: Any, old_value: Any, new_value: Any) -> str:
        """«столбец: старое → новое» по подходящему анализатору."""
        analyzer = self._find_analyzer(old_value, new_value)
        try:
            detail = analyzer.analyze(old_value, new_value, column)
            return f"{column}: {detail.description}"
        except Exception as e:
            self.logger.warning(f"Ошибка анализа различий для {column}: {e}")
            return f"{column}: {old_value} → {new_value}"

    def _add_differences_sheet(
        self,
        workbook: Workbook,
        result: ComparisonResult,
        row_pairs: pd.DataFrame,
        options: dict[str, Any],
    ) -> None:
        """Лист «Расхождения»: только строки с отличиями.

        Изменённая строка — двумя строками (файл 1, затем файл 2) с одним
        номером, подсветкой изменённых ячеек и описанием «что изменилось».
        Строка без пары — одной строкой. «Строка в файле» — номер строки в
        исходном файле (``first_data_row`` — номер первой строки данных).
        """
        worksheet = workbook.create_sheet(title=DIFFERENCES_SHEET_NAME, index=0)
        columns = list(result.file1_data.columns)
        worksheet.append([*DIFFERENCES_LEAD_COLUMNS, *columns, "Что изменилось"])
        self._style_header_row(worksheet)
        worksheet.freeze_panes = "A2"

        statuses = row_pairs["status"].to_numpy()
        changed = np.flatnonzero(statuses != STATUS_EQUAL)
        if len(changed) == 0:
            worksheet.append([None, "Расхождений нет"])
            self._auto_adjust_columns(worksheet)
            return

        first_data_row = int(options.get("first_data_row", 2))
        by_key = bool((result.metadata.get("row_match") or {}).get("key_columns"))
        sources = [
            (1, result.file1_data.to_numpy(dtype=object), row_pairs["row_file1"].to_numpy()),
            (2, result.file2_data.to_numpy(dtype=object), row_pairs["row_file2"].to_numpy()),
        ]
        mask = result.differences_mask.to_numpy(dtype=bool)
        lead = len(DIFFERENCES_LEAD_COLUMNS)

        for number, i in enumerate(changed[:DIFFERENCES_SHEET_MAX_ITEMS].tolist(), start=1):
            status = statuses[i]
            paired = status in (STATUS_MODIFIED, STATUS_SIMILAR)
            description = (
                " | ".join(
                    self._describe_change(columns[c], sources[0][1][i, c], sources[1][1][i, c])
                    for c in np.flatnonzero(mask[i])
                )
                if paired
                else None
            )
            for file_number, values, source_rows in sources:
                if source_rows[i] < 0:
                    continue
                worksheet.append(
                    [
                        number,
                        self._status_label(status, by_key),
                        file_number,
                        int(source_rows[i]) + first_data_row,
                        *(None if pd.isna(v) else v for v in values[i]),
                        description if file_number == 1 or not paired else None,
                    ]
                )
                if paired:
                    for c in np.flatnonzero(mask[i]):
                        cell = worksheet.cell(row=worksheet.max_row, column=lead + int(c) + 1)
                        cell.fill = self.highlight_fill
                        cell.border = self.thin_border

        worksheet.auto_filter.ref = (
            f"A1:{get_column_letter(worksheet.max_column)}{worksheet.max_row}"
        )
        if len(changed) > DIFFERENCES_SHEET_MAX_ITEMS:
            worksheet.append(
                [
                    None,
                    f"Показаны первые {DIFFERENCES_SHEET_MAX_ITEMS} расхождений "
                    f"из {len(changed)}; все отмечены на листах данных",
                ]
            )
        self._auto_adjust_columns(worksheet)

    @staticmethod
    def _status_label(status: str, by_key: bool) -> str:
        """Подпись статуса строки на листе «Расхождения»."""
        if status == STATUS_MODIFIED and by_key:
            return "Изменена (по ключу)"
        return STATUS_LABELS[status]

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
        worksheet["A1"] = "Сводка сравнения файлов"
        worksheet["A1"].font = Font(bold=True, size=16)
        worksheet["A1"].alignment = self.center_align
        worksheet.merge_cells("A1:B1")

        # Статистика
        row = 3
        stats = [
            ("Общее количество ячеек:", result.metadata["total_cells"]),
            ("Ячеек с различиями:", result.metadata["different_cells"]),
            (
                "Процент схожести:",
                f"{floor_percentage(result.metadata['similarity_percentage']):.2f}%",
            ),
            (
                "Размер данных:",
                f"{result.metadata['shape'][0]} строк × {result.metadata['shape'][1]} столбцов",
            ),
        ]

        for label, value in stats:
            worksheet[f"A{row}"] = label
            worksheet[f"B{row}"] = value
            worksheet[f"A{row}"].font = Font(bold=True)
            row += 1

        # Сопоставление строк — только для сравнения без учёта порядка
        row_match = result.metadata.get("row_match")
        if row_match:
            row = self._add_row_match_section(worksheet, row + 2, row_match)

        # Различия по столбцам
        row += 2
        worksheet[f"A{row}"] = "Различия по столбцам:"
        worksheet[f"A{row}"].font = Font(bold=True, size=14)
        row += 1

        # Заголовки таблицы
        worksheet[f"A{row}"] = "Столбец"
        worksheet[f"B{row}"] = "Количество различий"
        worksheet[f"C{row}"] = "Процент различий"

        for col in ["A", "B", "C"]:
            worksheet[f"{col}{row}"].font = self.header_font
            worksheet[f"{col}{row}"].fill = self.header_fill
            worksheet[f"{col}{row}"].border = self.thin_border

        row += 1

        # Статистика по столбцам
        for col_name in result.differences_mask.columns:
            diff_count = result.differences_mask[col_name].sum()
            diff_percentage = (diff_count / len(result.differences_mask)) * 100

            worksheet[f"A{row}"] = col_name
            worksheet[f"B{row}"] = diff_count
            worksheet[f"C{row}"] = f"{diff_percentage:.1f}%"

            for col in ["A", "B", "C"]:
                worksheet[f"{col}{row}"].border = self.thin_border

            row += 1

        # Автоподбор ширины столбцов
        self._auto_adjust_columns(worksheet)

    def _add_row_match_section(self, worksheet: Any, row: int, row_match: dict[str, Any]) -> int:
        """Пишет блок сопоставления строк (режим без учёта порядка строк).

        Возвращает номер строки сразу после блока.
        """
        worksheet[f"A{row}"] = "Сопоставление строк (без учёта порядка):"
        worksheet[f"A{row}"].font = Font(bold=True, size=14)
        row += 1

        key_columns = row_match.get("key_columns") or []
        similar = row_match.get("similar", 0)
        lines: list[tuple[str, Any]] = [
            ("Итог:", "Совпадают" if row_match["identical"] else "Есть расхождения"),
            ("Ключевые столбцы:", ", ".join(key_columns) if key_columns else "вся строка"),
            ("Строк в файле 1:", row_match["rows_file1"]),
            ("Строк в файле 2:", row_match["rows_file2"]),
            ("Совпало строк:", row_match["equal"]),
            ("Изменённые строки (пара найдена):", row_match["modified"]),
        ]
        if not key_columns:
            # Без ключей изменённую строку находит только проход по сходству
            lines.append(("из них по сходству:", similar))
        lines += [
            ("Только в файле 1:", row_match["only_in_file1"]),
            ("Только в файле 2:", row_match["only_in_file2"]),
            ("Порядок строк отличается:", "да" if row_match["order_changed"] else "нет"),
        ]
        if similar:
            lines.append(("Примечание:", SIMILARITY_NOTE))
        for label, value in lines:
            worksheet[f"A{row}"] = label
            worksheet[f"B{row}"] = value
            worksheet[f"A{row}"].font = Font(bold=True)
            row += 1

        totals = row_match.get("column_totals") or {}
        if totals:
            row = self._add_column_totals_table(worksheet, row + 1, totals)

        return row

    def _add_column_totals_table(
        self, worksheet: Any, row: int, totals: dict[str, dict[str, float | int]]
    ) -> int:
        """Таблица итогов по числовым столбцам; возвращает строку после таблицы."""
        headers = ["Столбец", "Сумма в файле 1", "Сумма в файле 2", "Разница"]
        for col, header in zip(["A", "B", "C", "D"], headers, strict=True):
            worksheet[f"{col}{row}"] = header
            worksheet[f"{col}{row}"].font = self.header_font
            worksheet[f"{col}{row}"].fill = self.header_fill
            worksheet[f"{col}{row}"].border = self.thin_border
        row += 1

        for column_name, sums in totals.items():
            values = [column_name, sums["file1"], sums["file2"], sums["file2"] - sums["file1"]]
            for col, value in zip(["A", "B", "C", "D"], values, strict=True):
                worksheet[f"{col}{row}"] = value
                worksheet[f"{col}{row}"].border = self.thin_border
            row += 1

        return row

    def _auto_adjust_columns(self, worksheet: Any) -> None:
        """Подбирает ширину столбцов по выборке первых строк.

        Раньше функция проходила по ``worksheet.columns``, материализуя КАЖДУЮ
        ячейку листа (для листа 58k×19 — около 1.1 млн ячеек на лист) и вызывая
        ``str()``+``len()`` для каждой; это и было основной стоимостью при
        формировании больших отчётов. Теперь сканируем только первые
        ``COLUMN_WIDTH_SAMPLE_ROWS`` строк (+ строка заголовков): ширина всё
        равно лишь визуальная оценка, а стоимость становится практически
        постоянной и не зависит от числа строк.
        """
        last_row = min(worksheet.max_row, COLUMN_WIDTH_SAMPLE_ROWS + 1)
        widths: dict[str, int] = {}

        for row in worksheet.iter_rows(min_row=1, max_row=last_row):
            for cell in row:
                if isinstance(cell, MergedCell):
                    continue
                value = cell.value
                if value is None:
                    continue
                length = len(str(value))
                letter = cell.column_letter
                if length > widths.get(letter, 0):
                    widths[letter] = length

        for letter, max_length in widths.items():
            worksheet.column_dimensions[letter].width = min(max_length + 2, 50)
