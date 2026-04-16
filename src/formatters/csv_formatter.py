"""CSV output formatter for comparison results.

Writes one CSV with the original columns plus a trailing ``__status__``
column carrying one of ``EQUAL`` / ``MODIFIED`` / ``ADDED`` / ``REMOVED``
per row. Uses :mod:`csv.writer` instead of :meth:`pandas.DataFrame.to_csv`
to keep full control over quoting and line terminators — pandas silently
normalises ``lineterminator`` in some release combinations.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any, ClassVar

import pandas as pd

from ..core.exceptions import ApplicationError
from ..core.interfaces import ComparisonResult, IOutputFormatter

#: The trailing column appended to the output.
STATUS_COLUMN: str = "__status__"

#: Sentinel values placed in the status column.
STATUS_EQUAL: str = "EQUAL"
STATUS_MODIFIED: str = "MODIFIED"
STATUS_ADDED: str = "ADDED"
STATUS_REMOVED: str = "REMOVED"


class CSVOutputFormatter(IOutputFormatter):
    """Форматтер для вывода результатов сравнения в CSV."""

    SUPPORTED_FORMATS: ClassVar[list[str]] = [".csv"]

    def __init__(self, config: Any = None) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)
        self.config = config

    def format(self, result: ComparisonResult, output_path: Path, **options: Any) -> None:
        """Сохраняет результат сравнения в CSV с колонкой ``__status__``.

        Args:
            result: comparison result from any :class:`IComparator`.
            output_path: destination file. Extension must be ``.csv``.
            **options:
                encoding (str): output encoding. Default ``"utf-8"``.
                    Pass ``"utf-8-sig"`` to emit a BOM for Excel
                    interop.
                delimiter (str): field separator. Default ``","``.
                quoting (int): :mod:`csv` quoting constant. Default
                    ``csv.QUOTE_MINIMAL``.
                lineterminator (str): row terminator. Default ``"\\n"``.
                diff_only (bool): when ``True``, rows flagged
                    ``EQUAL`` are dropped from the output. Default
                    ``False`` (full audit table).

        Raises:
            ApplicationError: on any I/O or pandas failure during
                serialisation. The root cause is chained.
        """
        encoding = str(options.get("encoding", "utf-8"))
        delimiter = str(options.get("delimiter", ","))
        quoting = int(options.get("quoting", csv.QUOTE_MINIMAL))
        lineterminator = str(options.get("lineterminator", "\n"))
        diff_only = bool(options.get("diff_only", False))

        try:
            self.logger.info(f"Создание CSV отчёта: {output_path}")
            statuses = self._compute_statuses(
                result.file1_data, result.file2_data, result.differences_mask
            )
            # ADDED rows carry content that lives only in file2 — swap them in.
            display_df = self._build_display_frame(result.file1_data, result.file2_data, statuses)
            display_df[STATUS_COLUMN] = statuses

            if diff_only:
                display_df = display_df[display_df[STATUS_COLUMN] != STATUS_EQUAL]

            self._write_csv(
                display_df,
                output_path,
                encoding=encoding,
                delimiter=delimiter,
                quoting=quoting,
                lineterminator=lineterminator,
            )
            self.logger.info(f"CSV отчёт создан: {output_path} ({len(display_df)} строк)")
        except Exception as e:
            self.logger.error(f"Ошибка создания CSV отчёта: {e}", exc_info=True)
            raise ApplicationError(f"Не удалось создать CSV отчёт: {e}") from e

    def get_supported_formats(self) -> list[str]:
        return self.SUPPORTED_FORMATS.copy()

    @staticmethod
    def _compute_statuses(
        file1: pd.DataFrame, file2: pd.DataFrame, mask: pd.DataFrame
    ) -> list[str]:
        """Classify each row as EQUAL / MODIFIED / ADDED / REMOVED.

        A row is ADDED/REMOVED when one side is fully NaN (i.e. the
        comparator padded to align shapes) and the other has values.
        Otherwise row status is derived from the diff mask.
        """
        f1_all_nan = file1.isna().all(axis=1).to_numpy()
        f2_all_nan = file2.isna().all(axis=1).to_numpy()
        any_diff = mask.any(axis=1).to_numpy()
        statuses: list[str] = []
        for i in range(len(file1)):
            if f1_all_nan[i] and not f2_all_nan[i]:
                statuses.append(STATUS_ADDED)
            elif f2_all_nan[i] and not f1_all_nan[i]:
                statuses.append(STATUS_REMOVED)
            elif any_diff[i]:
                statuses.append(STATUS_MODIFIED)
            else:
                statuses.append(STATUS_EQUAL)
        return statuses

    @staticmethod
    def _build_display_frame(
        file1: pd.DataFrame, file2: pd.DataFrame, statuses: list[str]
    ) -> pd.DataFrame:
        """file1 is the baseline; rows flagged ADDED are taken from file2
        so the audit actually shows the new content instead of empty cells."""
        display = file1.copy()
        for i, status in enumerate(statuses):
            if status == STATUS_ADDED:
                display.iloc[i] = file2.iloc[i]
        return display

    @staticmethod
    def _write_csv(
        df: pd.DataFrame,
        output_path: Path,
        *,
        encoding: str,
        delimiter: str,
        quoting: int,
        lineterminator: str,
    ) -> None:
        with open(output_path, "w", encoding=encoding, newline="") as fh:
            writer = csv.writer(
                fh,
                delimiter=delimiter,
                quoting=quoting,  # type: ignore[arg-type]  # csv accepts any int
                lineterminator=lineterminator,
            )
            writer.writerow([str(c) for c in df.columns])
            for row in df.itertuples(index=False, name=None):
                writer.writerow(["" if pd.isna(v) else v for v in row])
