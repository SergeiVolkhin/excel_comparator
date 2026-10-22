"""
Форматтер для вывода результатов в Excel

Отчёт пишется потоково через XlsxWriter (``constant_memory``): строки уходят
во временные файлы по мере записи, поэтому память не растёт с размером
таблицы, а ход записи можно показывать по кускам. Листы: «Сводка»,
«Расхождения» (только строки с отличиями) и две полные копии данных с
подсветкой — для таблиц до ``DATA_SHEETS_MAX_ROWS`` строк или по опции
``full_data_sheets``.
"""

from __future__ import annotations

import contextlib
import itertools
import logging
import os
import re
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, ClassVar

import numpy as np
import numpy.typing as npt
import pandas as pd
import xlsxwriter

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

IntArray = npt.NDArray[np.intp]

#: Report progress callback: share of the report written (0..1) and a message.
ProgressCallback = Callable[[float, str], None]

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

#: Above this row count full data sheets take a while to write; we log a
#: warning suggesting the HTML formatter (which paginates) for large tables.
EXCEL_LARGE_ROW_THRESHOLD: int = 20_000

#: Full data sheets are written on their own up to this many rows. Above it
#: two full copies of the data are most of the report's time and size, and
#: the differences sheet already lists every changed row.
DATA_SHEETS_MAX_ROWS: int = 100_000

#: Rows in one Excel sheet, the header included.
EXCEL_MAX_ROWS: int = 1_048_576

#: Sheet names used by the report itself.
SUMMARY_SHEET_NAME: str = "Сводка"
DIFFERENCES_SHEET_NAME: str = "Расхождения"

#: The differences sheet lists at most this many discrepancies. A changed row
#: takes two lines, and the lines must fit into one sheet together with the
#: header and a note, so the real limit may be lower (see ``_plan_items``).
DIFFERENCES_SHEET_MAX_ITEMS: int = EXCEL_MAX_ROWS - 2

#: Columns in front of the data columns on the differences sheet.
DIFFERENCES_LEAD_COLUMNS: list[str] = ["№", "Статус", "Файл", "Строка в файле"]

#: Rows written between two progress updates.
PROGRESS_CHUNK_ROWS: int = 10_000

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

#: Number formats of date cells: a column without times shows dates only.
DATE_FORMAT: str = "yyyy-mm-dd"
DATETIME_FORMAT: str = "yyyy-mm-dd hh:mm:ss"

#: XlsxWriter options: rows stream to disk, text always stays text (a value
#: like "=A1" or "http://…" must not turn into a formula or a link).
WORKBOOK_OPTIONS: dict[str, Any] = {
    "constant_memory": True,
    "strings_to_formulas": False,
    "strings_to_urls": False,
    "nan_inf_to_errors": True,
    "remove_timezone": True,
    "default_date_format": DATETIME_FORMAT,
}

#: Characters Excel does not allow in sheet names.
_INVALID_SHEET_NAME_CHARS = re.compile(r"[\[\]:*?/\\]")

#: Share of the progress taken by writing rows; the rest is saving the file.
_ROWS_SHARE = 0.97

_PAIRED = (STATUS_MODIFIED, STATUS_SIMILAR)
_ONLY = (STATUS_ONLY_FILE1, STATUS_ONLY_FILE2)
_NO_COLUMNS: IntArray = np.empty(0, dtype=np.intp)


@dataclass(frozen=True)
class _Formats:
    """Cell formats of one workbook (XlsxWriter formats belong to a workbook)."""

    header: Any
    highlight: Any
    title: Any
    section: Any
    bold: Any
    bordered: Any
    date: Any
    datetime: Any
    highlight_date: Any
    highlight_datetime: Any

    @classmethod
    def create(cls, workbook: Any, highlight_color: str) -> _Formats:
        highlight = {"bg_color": f"#{highlight_color}", "border": 1}
        return cls(
            header=workbook.add_format(
                {
                    "bold": True,
                    "font_size": 12,
                    "bg_color": f"#{HEADER_FILL_COLOR}",
                    "align": "center",
                    "valign": "vcenter",
                    "border": 1,
                }
            ),
            highlight=workbook.add_format(highlight),
            title=workbook.add_format(
                {"bold": True, "font_size": 16, "align": "center", "valign": "vcenter"}
            ),
            section=workbook.add_format({"bold": True, "font_size": 14}),
            bold=workbook.add_format({"bold": True}),
            bordered=workbook.add_format({"border": 1}),
            date=workbook.add_format({"num_format": DATE_FORMAT}),
            datetime=workbook.add_format({"num_format": DATETIME_FORMAT}),
            highlight_date=workbook.add_format({**highlight, "num_format": DATE_FORMAT}),
            highlight_datetime=workbook.add_format({**highlight, "num_format": DATETIME_FORMAT}),
        )


class _Progress:
    """Turns rows written into a share of the report for the callback."""

    def __init__(self, callback: ProgressCallback | None, total_rows: int) -> None:
        self._callback = callback
        self._total = max(total_rows, 1)
        self._done = 0

    def rows(self, count: int, message: str) -> None:
        self._done += count
        self.share(min(self._done / self._total, 1.0) * _ROWS_SHARE, message)

    def share(self, value: float, message: str) -> None:
        if self._callback is not None:
            self._callback(value, message)


@dataclass(frozen=True)
class _DifferencesPlan:
    """Which discrepancies the differences sheet shows and how many lines."""

    items: IntArray  # aligned row positions, in report order
    lines: int
    total: int  # all discrepancies, shown or not


class ExcelOutputFormatter(IOutputFormatter):
    """Форматтер для вывода результатов сравнения в Excel"""

    SUPPORTED_FORMATS: ClassVar[list[str]] = [".xlsx"]

    def __init__(self, config: Any = None) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)
        self.config = config

        self.highlight_color = (
            getattr(config.comparison, "highlight_color", DEFAULT_HIGHLIGHT_COLOR)
            if config
            else DEFAULT_HIGHLIGHT_COLOR
        )

        # Анализаторы различий
        self.analyzers = [
            ListDifferenceAnalyzer(
                separator=getattr(config.comparison, "list_separator", ",") if config else ","
            ),
            BasicDifferenceAnalyzer(),
        ]

    def format(self, result: ComparisonResult, output_path: Path, **options: Any) -> None:
        """Форматирует и сохраняет результат сравнения в Excel.

        Options:
            file1_name, file2_name: имена листов с данными.
            first_data_row: номер первой строки данных в исходных файлах.
            full_data_sheets: писать полные листы данных при любом размере.
            progress: ``callback(доля 0..1, сообщение)`` хода записи.
        """
        try:
            self.logger.info(f"Создание Excel отчета: {output_path}")
            row_pairs = self._row_pairs(result)
            statuses = row_pairs["status"].to_numpy()
            n_rows = len(result.file1_data)
            with_data = bool(options.get("full_data_sheets")) or n_rows <= DATA_SHEETS_MAX_ROWS

            rows = result.metadata.get("shape", (0, 0))[0]
            if with_data and rows > EXCEL_LARGE_ROW_THRESHOLD:
                self.logger.warning(
                    f"Большой объём данных ({rows} строк): полные листы данных пишутся "
                    f"долго. Для больших таблиц рассмотрите HTML-отчёт (укажите "
                    f"расширение .html в имени выходного файла)."
                )

            plan = self._plan_items(statuses)
            paired = np.isin(statuses, _PAIRED) & result.differences_mask.to_numpy(bool).any(1)
            described = np.flatnonzero(paired) if with_data else plan.items[paired[plan.items]]
            descriptions = self._describe_rows(result, described)

            total_rows = plan.lines + (2 * n_rows if with_data else 0)
            progress = _Progress(options.get("progress"), total_rows)
            workbook = xlsxwriter.Workbook(_target(output_path), WORKBOOK_OPTIONS)
            try:
                formats = _Formats.create(workbook, self.highlight_color)
                note = None if with_data else _data_sheets_note(n_rows)
                self._write_summary_sheet(workbook, formats, result, note)
                self._write_differences_sheet(
                    workbook, formats, progress, result, row_pairs, plan, descriptions, options
                )
                if with_data:
                    self._write_data_sheets(
                        workbook, formats, progress, result, statuses, descriptions, options
                    )
                progress.share(0.98, "Отчёт: сохранение файла…")
                workbook.close()
            except BaseException:
                _discard(workbook)
                raise
            progress.share(1.0, "Отчёт сохранён")
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

    @staticmethod
    def _plan_items(statuses: npt.NDArray[Any]) -> _DifferencesPlan:
        """Расхождения для листа: сколько поместится в лист Excel."""
        changed = np.flatnonzero(statuses != STATUS_EQUAL)
        lines = np.cumsum(np.where(np.isin(statuses[changed], _PAIRED), 2, 1))
        fits = int(np.searchsorted(lines, EXCEL_MAX_ROWS - 2, side="right"))
        count = min(fits, DIFFERENCES_SHEET_MAX_ITEMS)
        return _DifferencesPlan(
            items=changed[:count],
            lines=int(lines[count - 1]) if count else 0,
            total=len(changed),
        )

    # ------------------------------------------------------------------
    # Описания различий
    # ------------------------------------------------------------------
    def _describe_rows(self, result: ComparisonResult, rows: IntArray) -> dict[int, str]:
        """«Что изменилось» для выровненных строк ``rows`` (пары с отличиями)."""
        if len(rows) == 0:
            return {}
        columns = list(result.file1_data.columns)
        mask = result.differences_mask.to_numpy(dtype=bool)[rows]
        values1 = result.file1_data.iloc[rows].to_numpy(dtype=object)
        values2 = result.file2_data.iloc[rows].to_numpy(dtype=object)
        return {
            row: " | ".join(
                self._describe_change(columns[c], values1[k, c], values2[k, c])
                for c in np.flatnonzero(mask[k])
            )
            for k, row in enumerate(rows.tolist())
        }

    def _describe_change(self, column: Any, old_value: Any, new_value: Any) -> str:
        """«столбец: старое → новое» по подходящему анализатору."""
        try:
            if not (isinstance(old_value, str) and isinstance(new_value, str)):
                # Списки разбирает только ListDifferenceAnalyzer, и только
                # две строки: остальное сразу к базовому описанию.
                return f"{column}: {BasicDifferenceAnalyzer.describe(old_value, new_value)}"
            detail = self._find_analyzer(old_value, new_value).analyze(old_value, new_value, column)
            return f"{column}: {detail.description}"
        except Exception as e:
            self.logger.warning(f"Ошибка анализа различий для {column}: {e}")
            return f"{column}: {old_value} → {new_value}"

    def _find_analyzer(self, old_value: Any, new_value: Any) -> IDifferenceAnalyzer:
        """Находит подходящий анализатор для значений"""
        for analyzer in self.analyzers:
            if analyzer.can_analyze(old_value, new_value):
                return analyzer

        # Возвращаем базовый анализатор, если никто не подошел
        return self.analyzers[-1]

    @staticmethod
    def _status_label(status: str, by_key: bool) -> str:
        """Подпись статуса строки на листе «Расхождения»."""
        if status == STATUS_MODIFIED and by_key:
            return "Изменена (по ключу)"
        return STATUS_LABELS[status]

    # ------------------------------------------------------------------
    # Лист «Расхождения»
    # ------------------------------------------------------------------
    def _write_differences_sheet(
        self,
        workbook: Any,
        formats: _Formats,
        progress: _Progress,
        result: ComparisonResult,
        row_pairs: pd.DataFrame,
        plan: _DifferencesPlan,
        descriptions: dict[int, str],
        options: dict[str, Any],
    ) -> None:
        """Лист «Расхождения»: только строки с отличиями.

        Изменённая строка — двумя строками (файл 1, затем файл 2) с одним
        номером, подсветкой изменённых ячеек и описанием «что изменилось».
        Строка без пары — одной строкой. «Строка в файле» — номер строки в
        исходном файле (``first_data_row`` — номер первой строки данных).
        """
        worksheet = workbook.add_worksheet(DIFFERENCES_SHEET_NAME)
        header = [*DIFFERENCES_LEAD_COLUMNS, *map(str, result.file1_data.columns), "Что изменилось"]
        worksheet.freeze_panes(1, 0)

        if plan.total == 0:
            _set_widths(worksheet, [header, [None, "Расхождений нет"]])
            worksheet.write_row(0, 0, header, formats.header)
            worksheet.write(1, 1, "Расхождений нет")
            return

        lines = self._difference_lines(result, row_pairs, plan, descriptions, options)
        sample = list(itertools.islice(lines, COLUMN_WIDTH_SAMPLE_ROWS))
        _set_widths(worksheet, [header, *(values for values, _ in sample)])
        worksheet.write_row(0, 0, header, formats.header)

        lead = len(DIFFERENCES_LEAD_COLUMNS)
        row = 0
        for values, highlighted in itertools.chain(sample, lines):
            row += 1
            _write_line(worksheet, row, values, highlighted, lead, formats, {})
            if row % PROGRESS_CHUNK_ROWS == 0:
                progress.rows(
                    PROGRESS_CHUNK_ROWS, _rows_message(DIFFERENCES_SHEET_NAME, row, plan.lines)
                )
        progress.rows(
            row % PROGRESS_CHUNK_ROWS, _rows_message(DIFFERENCES_SHEET_NAME, row, plan.lines)
        )

        worksheet.autofilter(0, 0, row, len(header) - 1)
        if plan.total > len(plan.items):
            worksheet.write(
                row + 1,
                1,
                f"Показаны первые {len(plan.items)} расхождений из {plan.total}: "
                f"остальные не помещаются на лист Excel",
            )

    def _difference_lines(
        self,
        result: ComparisonResult,
        row_pairs: pd.DataFrame,
        plan: _DifferencesPlan,
        descriptions: dict[int, str],
        options: dict[str, Any],
    ) -> Iterator[tuple[list[Any], IntArray]]:
        """Строки листа «Расхождения»: значения и подсвечиваемые столбцы данных."""
        first_data_row = int(options.get("first_data_row", 2))
        by_key = bool((result.metadata.get("row_match") or {}).get("key_columns"))
        statuses = row_pairs["status"].to_numpy()
        sources = row_pairs[["row_file1", "row_file2"]].to_numpy()
        mask = result.differences_mask.to_numpy(dtype=bool)

        for start in range(0, len(plan.items), PROGRESS_CHUNK_ROWS):
            chunk = plan.items[start : start + PROGRESS_CHUNK_ROWS]
            values1 = _rows_as_lists(result.file1_data, chunk)
            values2 = _rows_as_lists(result.file2_data, chunk)
            for offset, i in enumerate(chunk.tolist()):
                number = start + offset + 1
                status = statuses[i]
                label = self._status_label(status, by_key)
                paired = status in _PAIRED
                highlighted = np.flatnonzero(mask[i]) if paired else _NO_COLUMNS
                if sources[i, 0] >= 0:
                    description = descriptions.get(i) if paired else None
                    line1 = [number, label, 1, int(sources[i, 0]) + first_data_row]
                    yield [*line1, *values1[offset], description], highlighted
                if sources[i, 1] >= 0:
                    line2 = [number, label, 2, int(sources[i, 1]) + first_data_row]
                    yield [*line2, *values2[offset], None], highlighted

    # ------------------------------------------------------------------
    # Листы с полными данными
    # ------------------------------------------------------------------
    def _write_data_sheets(
        self,
        workbook: Any,
        formats: _Formats,
        progress: _Progress,
        result: ComparisonResult,
        statuses: npt.NDArray[Any],
        descriptions: dict[int, str],
        options: dict[str, Any],
    ) -> None:
        """Два листа с данными файлов; столбец «Различия» общий: «файл 1 → файл 2»."""
        differences = _differences_column(statuses, descriptions)
        taken = {SUMMARY_SHEET_NAME.casefold(), DIFFERENCES_SHEET_NAME.casefold()}
        for name_option, default, frame in (
            ("file1_name", "Файл 1", result.file1_data),
            ("file2_name", "Файл 2", result.file2_data),
        ):
            name = _unique_sheet_name(str(options.get(name_option, default)), taken)
            self._write_data_sheet(workbook, formats, progress, name, frame, differences, result)

    def _write_data_sheet(
        self,
        workbook: Any,
        formats: _Formats,
        progress: _Progress,
        name: str,
        frame: pd.DataFrame,
        differences: npt.NDArray[np.object_],
        result: ComparisonResult,
    ) -> None:
        """Лист с данными файла и подсветкой различающихся ячеек."""
        worksheet = workbook.add_worksheet(name)
        header = [*map(str, frame.columns), "Различия"]
        sample = _rows_as_lists(frame, slice(0, COLUMN_WIDTH_SAMPLE_ROWS))
        _set_widths(
            worksheet,
            [header, *([*values, differences[k]] for k, values in enumerate(sample))],
        )
        worksheet.write_row(0, 0, header, formats.header)

        mask = result.differences_mask.to_numpy(dtype=bool)
        has_differences = mask.any(axis=1)
        date_columns = _date_columns(frame)
        n_rows = len(frame)
        for start in range(0, n_rows, PROGRESS_CHUNK_ROWS):
            stop = min(start + PROGRESS_CHUNK_ROWS, n_rows)
            for offset, values in enumerate(_rows_as_lists(frame, slice(start, stop))):
                i = start + offset
                values.append(differences[i])
                highlighted = np.flatnonzero(mask[i]) if has_differences[i] else _NO_COLUMNS
                _write_line(worksheet, i + 1, values, highlighted, 0, formats, date_columns)
            progress.rows(stop - start, _rows_message(name, stop, n_rows))

    # ------------------------------------------------------------------
    # Лист «Сводка»
    # ------------------------------------------------------------------
    def _write_summary_sheet(
        self,
        workbook: Any,
        formats: _Formats,
        result: ComparisonResult,
        data_sheets_note: str | None,
    ) -> None:
        """Лист со сводкой результатов: пишется построчно сверху вниз."""
        worksheet = workbook.add_worksheet(SUMMARY_SHEET_NAME)
        rows = self._summary_rows(result, data_sheets_note)
        _set_widths(worksheet, [[value for value, _ in cells] for cells in rows])

        by_name = {
            "header": formats.header,
            "section": formats.section,
            "bold": formats.bold,
            "bordered": formats.bordered,
        }
        title, _ = rows[0][0]
        worksheet.merge_range(0, 0, 0, 1, title, formats.title)
        for row, cells in enumerate(rows[1:], start=1):
            for column, (value, style) in enumerate(cells):
                worksheet.write(row, column, _plain(value), by_name.get(style or ""))

    def _summary_rows(
        self, result: ComparisonResult, data_sheets_note: str | None
    ) -> list[list[tuple[Any, str | None]]]:
        """Строки сводки: ячейки (значение, стиль) по порядку."""
        metadata = result.metadata
        rows: list[list[tuple[Any, str | None]]] = [[("Сводка сравнения файлов", "title")], []]

        stats: list[tuple[str, Any]] = [
            ("Общее количество ячеек:", metadata["total_cells"]),
            ("Ячеек с различиями:", metadata["different_cells"]),
            (
                "Процент схожести:",
                f"{floor_percentage(metadata['similarity_percentage']):.2f}%",
            ),
            (
                "Размер данных:",
                f"{metadata['shape'][0]} строк × {metadata['shape'][1]} столбцов",
            ),
        ]
        if data_sheets_note:
            stats.append(("Полные листы данных:", data_sheets_note))
        rows += [[(label, "bold"), (value, None)] for label, value in stats]

        # Сопоставление строк — только для сравнения без учёта порядка
        row_match = metadata.get("row_match")
        if row_match:
            rows += [[], []]
            rows += self._row_match_rows(row_match)

        # Различия по столбцам
        rows += [[], []]
        rows.append([("Различия по столбцам:", "section")])
        rows.append(
            [
                ("Столбец", "header"),
                ("Количество различий", "header"),
                ("Процент различий", "header"),
            ]
        )
        mask = result.differences_mask
        for column in mask.columns:
            count = int(mask[column].sum())
            share = count / len(mask) * 100 if len(mask) else 0.0
            rows.append([(column, "bordered"), (count, "bordered"), (f"{share:.1f}%", "bordered")])
        return rows

    @staticmethod
    def _row_match_rows(row_match: dict[str, Any]) -> list[list[tuple[Any, str | None]]]:
        """Блок сопоставления строк (режим без учёта порядка строк)."""
        rows: list[list[tuple[Any, str | None]]] = [
            [("Сопоставление строк (без учёта порядка):", "section")]
        ]

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
        rows += [[(label, "bold"), (value, None)] for label, value in lines]

        totals = row_match.get("column_totals") or {}
        if totals:
            rows.append([])
            headers = ["Столбец", "Сумма в файле 1", "Сумма в файле 2", "Разница"]
            rows.append([(header, "header") for header in headers])
            for column_name, sums in totals.items():
                values = [column_name, sums["file1"], sums["file2"], sums["file2"] - sums["file1"]]
                rows.append([(value, "bordered") for value in values])
        return rows


def _discard(workbook: Any) -> None:
    """Бросает недописанную книгу: ни отчёта, ни временных файлов.

    Без этого XlsxWriter сам закроет книгу в ``__del__`` и оставит на диске
    недописанный отчёт, а файлы строк режима ``constant_memory`` (они
    создаются через ``mkstemp`` и удаляются только при успешном ``close``)
    останутся во временной папке. ``_opt_close`` и ``row_data_filename`` —
    внутренности XlsxWriter 3.x, поэтому через ``getattr``.
    """
    workbook.fileclosed = True
    for worksheet in workbook.worksheets():
        close = getattr(worksheet, "_opt_close", None)
        if close is not None:
            close()
        filename = getattr(worksheet, "row_data_filename", None)
        if filename:
            with contextlib.suppress(OSError):
                os.unlink(filename)


def _target(output_path: Any) -> Any:
    """Имя файла для XlsxWriter; файловый объект (BytesIO) — как есть."""
    if isinstance(output_path, (str, os.PathLike)):
        return os.fspath(output_path)
    return output_path


def _rows_as_lists(frame: pd.DataFrame, positions: IntArray | slice) -> list[list[Any]]:
    """Строки ``frame`` списками обычных Python-значений; NA — None."""
    chunk = frame.iloc[positions]
    values = chunk.to_numpy(dtype=object)
    missing = chunk.isna().to_numpy()
    if missing.any():
        values[missing] = None
    rows: list[list[Any]] = values.tolist()
    return rows


def _write_line(
    worksheet: Any,
    row: int,
    values: list[Any],
    highlighted: IntArray,
    offset: int,
    formats: _Formats,
    date_columns: dict[int, bool],
) -> None:
    """Пишет строку; столбцы данных начинаются с ``offset``.

    Подсвеченные ячейки и ячейки дат дописываются поверх ``write_row`` своим
    форматом: в режиме ``constant_memory`` это можно, пока строка не сброшена.
    """
    worksheet.write_row(row, 0, values)
    for position, is_date in date_columns.items():
        value = values[offset + position]
        if value is not None:
            worksheet.write_datetime(
                row, offset + position, value, formats.date if is_date else formats.datetime
            )
    for position in highlighted.tolist():
        column = offset + position
        value = values[column]
        if isinstance(value, (datetime, date)):
            is_date = date_columns.get(position, False)
            date_format = formats.highlight_date if is_date else formats.highlight_datetime
            worksheet.write_datetime(row, column, value, date_format)
        else:
            worksheet.write(row, column, value, formats.highlight)


def _differences_column(
    statuses: npt.NDArray[Any], descriptions: dict[int, str]
) -> npt.NDArray[np.object_]:
    """Столбец «Различия» листов данных: описание или «Только в файле N»."""
    column = np.full(len(statuses), None, dtype=object)
    for status in _ONLY:
        column[statuses == status] = STATUS_LABELS[status]
    for row, text in descriptions.items():
        column[row] = text
    return column


def _date_columns(frame: pd.DataFrame) -> dict[int, bool]:
    """Столбцы datetime: позиция → True, если ни в одном значении нет времени."""
    columns: dict[int, bool] = {}
    for position in range(frame.shape[1]):
        values = frame.iloc[:, position]
        if pd.api.types.is_datetime64_any_dtype(values):
            present = values.dropna()
            columns[position] = bool((present == present.dt.normalize()).all())
    return columns


def _set_widths(worksheet: Any, rows: Iterable[Sequence[Any]]) -> None:
    """Ширина столбцов по длине значений в ``rows`` (+2, не больше 50)."""
    widths: dict[int, int] = {}
    for values in rows:
        for column, value in enumerate(values):
            if value is None:
                continue
            length = len(str(value))
            if length > widths.get(column, 0):
                widths[column] = length
    for column, length in widths.items():
        worksheet.set_column(column, column, min(length + 2, 50))


def _unique_sheet_name(name: str, taken: set[str]) -> str:
    """Допустимое и ещё не занятое имя листа (Excel не различает регистр)."""
    base = _INVALID_SHEET_NAME_CHARS.sub("_", name).strip("'")[:SHEET_NAME_MAX_LEN] or "Лист"
    candidate = base
    number = 2
    while candidate.casefold() in taken:
        suffix = f" ({number})"
        candidate = base[: SHEET_NAME_MAX_LEN - len(suffix)] + suffix
        number += 1
    taken.add(candidate.casefold())
    return candidate


def _data_sheets_note(n_rows: int) -> str:
    return (
        f"не записаны: {_count(n_rows)} строк больше {_count(DATA_SHEETS_MAX_ROWS)}. "
        "Включите «Полные листы данных для больших файлов» в «Дополнительно» "
        "или флаг --full-data-sheets"
    )


def _rows_message(sheet: str, done: int, total: int) -> str:
    return f"Отчёт: лист «{sheet}» — {_count(done)} из {_count(total)} строк"


def _count(value: int) -> str:
    """Число с разделением разрядов пробелом: ``380 598``."""
    return f"{value:,}".replace(",", " ")


def _plain(value: Any) -> Any:
    """numpy-скаляр → обычное Python-значение (XlsxWriter пишет int64 как float)."""
    return value.item() if isinstance(value, np.generic) else value
