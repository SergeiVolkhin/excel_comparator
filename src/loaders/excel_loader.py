"""
Загрузчик Excel файлов
"""

import logging
from pathlib import Path
from typing import ClassVar

import pandas as pd

from ..core.exceptions import FileLoadError
from ..core.interfaces import IFileLoader


class ExcelFileLoader(IFileLoader):
    """Загрузчик для Excel файлов (.xlsx, .xls)"""

    SUPPORTED_EXTENSIONS: ClassVar[list[str]] = [".xlsx", ".xls"]

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)

    def can_load(self, file_path: Path) -> bool:
        """Проверяет, может ли загрузчик обработать данный файл"""
        return file_path.suffix.lower() in self.SUPPORTED_EXTENSIONS

    def load(self, file_path: Path, **kwargs) -> pd.DataFrame:
        """Загружает Excel файл и возвращает DataFrame"""
        if not file_path.exists():
            raise FileLoadError(str(file_path), "Файл не существует")

        if not self.can_load(file_path):
            raise FileLoadError(
                str(file_path),
                f"Неподдерживаемое расширение. Поддерживаемые: {', '.join(self.SUPPORTED_EXTENSIONS)}",
            )

        try:
            # Параметры по умолчанию
            sheet_name = kwargs.get("sheet_name", 0)
            header = kwargs.get("header", 0)

            self.logger.info(f"Загрузка файла: {file_path}")

            # Определяем движок на основе расширения
            engine = "openpyxl" if file_path.suffix.lower() == ".xlsx" else "xlrd"

            df = pd.read_excel(file_path, sheet_name=sheet_name, header=header, engine=engine)

            self.logger.info(f"Успешно загружен файл {file_path.name}: {df.shape}")

            # Проверяем, что DataFrame не пустой
            if df.empty:
                raise FileLoadError(str(file_path), "Файл пустой или не содержит данных")

            return df

        except PermissionError as e:
            raise FileLoadError(
                str(file_path), "Закройте файл Excel и попробуйте снова"
            ) from e
        except pd.errors.EmptyDataError as e:
            raise FileLoadError(str(file_path), "Файл не содержит данных") from e
        except Exception as e:
            self.logger.error(f"Ошибка загрузки файла {file_path}: {e}")
            raise FileLoadError(str(file_path), str(e)) from e

    def get_supported_extensions(self) -> list[str]:
        """Возвращает список поддерживаемых расширений"""
        return self.SUPPORTED_EXTENSIONS.copy()

    def get_sheet_names(self, file_path: Path) -> list[str]:
        """Получает список листов в Excel файле"""
        try:
            engine = "openpyxl" if file_path.suffix.lower() == ".xlsx" else "xlrd"
            excel_file = pd.ExcelFile(file_path, engine=engine)
            return excel_file.sheet_names
        except Exception as e:
            self.logger.error(f"Ошибка получения списка листов из {file_path}: {e}")
            return []

    def preview_data(self, file_path: Path, max_rows: int = 5) -> pd.DataFrame:
        """Предварительный просмотр данных из файла"""
        try:
            engine = "openpyxl" if file_path.suffix.lower() == ".xlsx" else "xlrd"
            df = pd.read_excel(file_path, nrows=max_rows, engine=engine)
            return df
        except Exception as e:
            self.logger.error(f"Ошибка предварительного просмотра {file_path}: {e}")
            return pd.DataFrame()
