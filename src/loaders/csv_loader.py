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

    def __init__(self) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)

    def can_load(self, file_path: Path) -> bool:
        """Проверяет, может ли загрузчик обработать данный файл"""
        return file_path.suffix.lower() in self.SUPPORTED_EXTENSIONS

    def load(self, file_path: Path, **kwargs: Any) -> pd.DataFrame:
        """Загружает CSV файл с автоопределением параметров"""

        if not file_path.exists():
            raise FileLoadError(str(file_path), "Файл не существует")

        if not self.can_load(file_path):
            raise FileLoadError(
                str(file_path),
                f"Неподдерживаемое расширение. Поддерживаемые: {', '.join(self.SUPPORTED_EXTENSIONS)}",
            )

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

            # Загружаем файл
            df = cast(pd.DataFrame, pd.read_csv(file_path, **load_params))

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
            raise FileLoadError(str(file_path), f"Ошибка парсинга CSV: {e}") from e
        except Exception as e:
            self.logger.error(f"Ошибка загрузки CSV файла {file_path}: {e}")
            raise FileLoadError(str(file_path), str(e)) from e

    def get_supported_extensions(self) -> list[str]:
        """Возвращает список поддерживаемых расширений"""
        return self.SUPPORTED_EXTENSIONS.copy()

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

    _SEPARATOR_CANDIDATES: ClassVar[list[str]] = [",", ";", "\\t", "|", " "]

    def _detect_separator(self, file_path: Path, encoding: str, **kwargs: Any) -> str:
        """Определяет разделитель в CSV файле."""
        if "sep" in kwargs:
            return str(kwargs["sep"])
        if file_path.suffix.lower() == ".tsv":
            return "\\t"
        try:
            sample = self._read_sample_lines(file_path, encoding)
            scores = self._score_separators(sample)
            return self._pick_best_separator(scores)
        except Exception as e:
            self.logger.warning(f"Не удалось определить разделитель: {e}, используем запятую")
            return ","

    @staticmethod
    def _read_sample_lines(file_path: Path, encoding: str, max_lines: int = 5) -> list[str]:
        with open(file_path, encoding=encoding) as f:
            total = sum(1 for _ in f)
        with open(file_path, encoding=encoding) as f:
            return [f.readline().strip() for _ in range(min(max_lines, total))]

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

    def _prepare_load_params(
        self, separator: str, encoding: str, **kwargs: Any
    ) -> dict[str, Any]:
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

    def preview_data(
        self, file_path: Path, max_rows: int = 5, **kwargs: Any
    ) -> pd.DataFrame:
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
