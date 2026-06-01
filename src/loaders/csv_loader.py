"""
Загрузчик CSV файлов - демонстрация расширяемости системы
"""

import logging
from pathlib import Path
from typing import Any, ClassVar, cast

import chardet
import pandas as pd

from ..core.exceptions import FileLoadError
from ..core.interfaces import IFileLoader


class CSVFileLoader(IFileLoader):
    """Загрузчик для CSV файлов с автоопределением кодировки"""

    SUPPORTED_EXTENSIONS: ClassVar[list[str]] = [".csv", ".txt", ".tsv"]

    #: Files larger than this are read through a pandas chunk iterator and
    #: concatenated. Below the threshold pandas' peak memory usage stays
    #: tolerable; above it the iterator caps concurrent memory at one chunk.
    _CHUNK_THRESHOLD_BYTES: ClassVar[int] = 100 * 1024 * 1024

    #: Rows per chunk when the chunked path is taken. Tuneable via the
    #: ``chunk_size`` kwarg on ``load``.
    _DEFAULT_CHUNK_SIZE: ClassVar[int] = 50_000

    def __init__(self) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)

    def can_load(self, file_path: Path) -> bool:
        """Проверяет, может ли загрузчик обработать данный файл"""
        return file_path.suffix.lower() in self.SUPPORTED_EXTENSIONS

    def load(self, file_path: Path, **kwargs: Any) -> pd.DataFrame:
        """Загружает CSV файл с автоопределением параметров.

        Auto-detected when not provided:
            encoding — via chardet (fallback UTF-8 when confidence < 0.7).
            sep — scoring over {",", ";", "\\t", "|"} on the first few lines.

        First-class explicit overrides (all passed straight to pandas):
            sep: str — skip auto-detection of the delimiter.
            encoding: str — skip chardet; also silences the fallback warning.
            skiprows: int | Sequence[int] — drop leading rows before the header.
            header: int | None — row index for the header, or None for
                integer-labelled columns.
            nrows: int — cap the number of data rows read.
            dtype: str | dict — force a dtype; set to ``str`` to disable
                pandas' type inference (useful for string-only workflows).
            keep_default_na: bool — when False, sentinels like "NaN"/"NULL"
                are kept as strings instead of becoming NaN.
            comment, quoting, quotechar, doublequote, escapechar,
            thousands, decimal, lineterminator, skip_blank_lines,
            na_values, parse_dates, dayfirst, converters, index_col,
            skipfooter, cache_dates — all forwarded to ``pandas.read_csv``.
            chunk_size: int — rows per chunk when the file size exceeds
                ``_CHUNK_THRESHOLD_BYTES`` (100 MB). Default 50 000. Lower
                values reduce peak memory at the cost of more concat work.
            on_bad_lines: {'error', 'skip', 'warn'} | callable — how to
                handle malformed rows. Default ``'error'`` (raises
                ``FileLoadError`` with a hint). ``'skip'`` drops the
                offending line silently; ``'warn'`` drops it and emits a
                pandas ``ParserWarning``.

        Any kwarg not in the allowlist (see ``_prepare_load_params``) is
        dropped silently. ``engine`` is pinned to ``\"python\"`` by this
        loader and cannot be overridden.

        Raises:
            FileLoadError: file missing, wrong extension, empty, decoding
                error, parser error, or any other read_csv failure.
        """

        if not file_path.exists():
            raise FileLoadError(str(file_path), "Файл не существует")

        if not self.can_load(file_path):
            raise FileLoadError(
                str(file_path),
                f"Неподдерживаемое расширение. Поддерживаемые: {', '.join(self.SUPPORTED_EXTENSIONS)}",
            )

        chunk_size = int(kwargs.pop("chunk_size", self._DEFAULT_CHUNK_SIZE))

        try:
            # Определяем кодировку
            encoding = self._detect_encoding(file_path)
            self.logger.info(f"Определена кодировка: {encoding}")

            # Определяем разделитель
            separator = self._detect_separator(file_path, encoding, **kwargs)
            self.logger.info(f"Определен разделитель: '{separator}'")

            # Параметры загрузки
            load_params = self._prepare_load_params(separator, encoding, **kwargs)

            self.logger.info(f"Загрузка CSV файла: {file_path}")

            file_size = file_path.stat().st_size
            df = self._read_csv(file_path, load_params, file_size, chunk_size)

            self.logger.info(f"Успешно загружен CSV файл {file_path.name}: {df.shape}")

            # Проверяем, что DataFrame не пустой
            if df.empty:
                raise FileLoadError(str(file_path), "Файл пустой или не содержит данных")

            return df

        except UnicodeDecodeError as e:
            raise FileLoadError(str(file_path), f"Ошибка кодировки: {e}") from e
        except pd.errors.EmptyDataError as e:
            raise FileLoadError(str(file_path), "Файл не содержит данных") from e
        except pd.errors.ParserError as e:
            hint = (
                ""
                if kwargs.get("on_bad_lines") in ("skip", "warn")
                else (
                    " Подсказка: включите пропуск повреждённых строк "
                    "(CLI: --csv-on-bad-lines skip; GUI: галочка «Пропускать "
                    "повреждённые строки»)."
                )
            )
            raise FileLoadError(str(file_path), f"Ошибка парсинга CSV: {e}.{hint}") from e
        except Exception as e:
            self.logger.error(f"Ошибка загрузки CSV файла {file_path}: {e}")
            raise FileLoadError(str(file_path), str(e)) from e

    def get_supported_extensions(self) -> list[str]:
        """Возвращает список поддерживаемых расширений"""
        return self.SUPPORTED_EXTENSIONS.copy()

    def _read_csv(
        self,
        file_path: Path,
        load_params: dict[str, Any],
        file_size: int,
        chunk_size: int,
    ) -> pd.DataFrame:
        """Читает CSV обычным или чанкованным путём.

        Если ``on_bad_lines="skip"`` (путь, который включают GUI-галочка и
        ``--csv-on-bad-lines skip``), строковое значение заменяется на
        callable-обработчик, который считает пропущенные строки и возвращает
        ``None`` (строка отбрасывается). Это даёт точный счётчик пропущенных
        строк, который затем выводится одним WARNING.

        Режим ``"warn"`` НЕ перехватывается: его обрабатывает сам pandas
        (эмитит ``ParserWarning`` на каждую строку) — это закреплено тестами.
        По умолчанию ``on_bad_lines`` отсутствует, и pandas работает строго
        (режим ``"error"``): повреждённый файл по-прежнему завершается ошибкой.
        """
        params = dict(load_params)
        bad_lines_mode = params.get("on_bad_lines")
        skipped = 0

        if bad_lines_mode == "skip":

            def _count_bad_line(bad_line: list[str]) -> None:
                nonlocal skipped
                skipped += 1
                return None

            params["on_bad_lines"] = _count_bad_line

        if file_size > self._CHUNK_THRESHOLD_BYTES:
            self.logger.info(
                f"Размер файла {file_size / 1024 / 1024:.1f} MB превышает порог "
                f"{self._CHUNK_THRESHOLD_BYTES / 1024 / 1024:.0f} MB — чтение по {chunk_size} строк"
            )
            chunks = pd.read_csv(file_path, chunksize=chunk_size, **params)
            df = cast(pd.DataFrame, pd.concat(chunks, ignore_index=True))
        else:
            df = cast(pd.DataFrame, pd.read_csv(file_path, **params))

        if bad_lines_mode == "skip" and skipped:
            self.logger.warning(
                f"Пропущено повреждённых строк при чтении {file_path.name}: {skipped}. "
                f"Данные загружены частично, итоговый размер: {df.shape}"
            )

        return df

    def _detect_encoding(self, file_path: Path) -> str:
        """Определяет кодировку файла"""
        try:
            with open(file_path, "rb") as f:
                raw_data = f.read(10000)  # Читаем первые 10KB

            result = chardet.detect(raw_data)
            encoding = result["encoding"] or "utf-8"
            confidence = result["confidence"] or 0.0

            self.logger.debug(f"Определена кодировка {encoding} с уверенностью {confidence}")

            # Если уверенность низкая, используем UTF-8 по умолчанию
            if confidence < 0.7:
                self.logger.warning(
                    f"Низкая уверенность в кодировке ({confidence}), используем UTF-8"
                )
                encoding = "utf-8"

            return encoding

        except Exception as e:
            self.logger.warning(f"Не удалось определить кодировку: {e}, используем UTF-8")
            return "utf-8"

    _SEPARATOR_CANDIDATES: ClassVar[list[str]] = [",", ";", "\t", "|"]

    def _detect_separator(self, file_path: Path, encoding: str, **kwargs: Any) -> str:
        """Определяет разделитель в CSV файле."""
        if "sep" in kwargs:
            return str(kwargs["sep"])
        if file_path.suffix.lower() == ".tsv":
            return "\t"
        try:
            sample = self._read_sample_lines(file_path, encoding)
            scores = self._score_separators(sample)
            return self._pick_best_separator(scores)
        except Exception as e:
            self.logger.warning(f"Не удалось определить разделитель: {e}, используем запятую")
            return ","

    @staticmethod
    def _read_sample_lines(file_path: Path, encoding: str, max_lines: int = 50) -> list[str]:
        """Читает до ``max_lines`` первых строк без полного прохода по файлу.

        Раньше функция сначала считала ВСЕ строки файла
        (``sum(1 for _ in f)``) лишь ради ограничения среза — на больших файлах
        это был напрасный полный проход. Теперь читаем построчно и
        останавливаемся на EOF. Больший размер выборки (50 против прежних 5)
        повышает надёжность определения разделителя на файлах с кавычками и
        строками переменной длины.
        """
        lines: list[str] = []
        with open(file_path, encoding=encoding) as f:
            for _ in range(max_lines):
                line = f.readline()
                if not line:
                    break
                lines.append(line.strip())
        return lines

    @classmethod
    def _score_separators(cls, lines: list[str]) -> dict[str, tuple[float, float]]:
        scores: dict[str, tuple[float, float]] = {}
        for sep in cls._SEPARATOR_CANDIDATES:
            col_counts = [len(line.split(sep)) for line in lines if line]
            if not col_counts:
                continue
            avg = sum(col_counts) / len(col_counts)
            consistency = 1.0 - (max(col_counts) - min(col_counts)) / max(1, avg)
            scores[sep] = (avg, consistency)
        return scores

    @staticmethod
    def _pick_best_separator(scores: dict[str, tuple[float, float]]) -> str:
        best_sep, best_score = ",", 0.0
        for sep, (avg, consistency) in scores.items():
            if avg <= 1:
                continue
            value = avg * consistency
            if value > best_score:
                best_sep, best_score = sep, value
        return best_sep

    def _prepare_load_params(self, separator: str, encoding: str, **kwargs: Any) -> dict[str, Any]:
        """Подготавливает параметры для загрузки pandas.read_csv"""

        params: dict[str, Any] = {
            "sep": separator,
            "encoding": encoding,
            "engine": "python",  # Более гибкий парсер
        }

        # Добавляем параметры из kwargs
        allowed_params = [
            "header",
            "index_col",
            "skiprows",
            "skipfooter",
            "nrows",
            "na_values",
            "keep_default_na",
            "dtype",
            "converters",
            "thousands",
            "decimal",
            "lineterminator",
            "quotechar",
            "quoting",
            "doublequote",
            "escapechar",
            "comment",
            "skip_blank_lines",
            "parse_dates",
            "infer_datetime_format",
            "date_parser",
            "dayfirst",
            "cache_dates",
            "on_bad_lines",
        ]

        for param in allowed_params:
            if param in kwargs:
                params[param] = kwargs[param]

        # Настройки по умолчанию для надежности
        if "header" not in params:
            params["header"] = 0  # Первая строка - заголовки

        if "skip_blank_lines" not in params:
            params["skip_blank_lines"] = True

        return params

    def preview_data(self, file_path: Path, max_rows: int = 5, **kwargs: Any) -> pd.DataFrame:
        """Предварительный просмотр CSV данных"""
        try:
            encoding = self._detect_encoding(file_path)
            separator = self._detect_separator(file_path, encoding, **kwargs)

            params = self._prepare_load_params(separator, encoding, **kwargs)
            params["nrows"] = max_rows

            return cast(pd.DataFrame, pd.read_csv(file_path, **params))

        except Exception as e:
            self.logger.error(f"Ошибка предварительного просмотра CSV {file_path}: {e}")
            return pd.DataFrame()

    def analyze_file_structure(self, file_path: Path) -> dict[str, Any]:
        """Анализирует структуру CSV файла"""
        try:
            encoding = self._detect_encoding(file_path)
            separator = self._detect_separator(file_path, encoding)

            # Загружаем небольшую выборку для анализа
            params = self._prepare_load_params(separator, encoding)
            params["nrows"] = 100

            df = pd.read_csv(file_path, **params)

            # Подсчитываем общее количество строк
            with open(file_path, encoding=encoding) as f:
                total_rows = sum(1 for _ in f) - 1  # Минус заголовок

            analysis = {
                "encoding": encoding,
                "separator": separator,
                "total_rows": total_rows,
                "columns": len(df.columns),
                "column_names": list(df.columns),
                "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
                "sample_data": df.head().to_dict("records"),
                "has_header": True,  # Предполагаем наличие заголовка
                "null_counts": df.isnull().sum().to_dict(),
                "file_size_bytes": file_path.stat().st_size,
            }

            return analysis

        except Exception as e:
            self.logger.error(f"Ошибка анализа структуры CSV файла {file_path}: {e}")
            return {}
