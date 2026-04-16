"""
Базовые интерфейсы для системы сравнения файлов
Соответствуют принципу DIP (Dependency Inversion Principle)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import pandas as pd


@dataclass
class ComparisonResult:
    """Результат сравнения файлов"""

    differences_mask: pd.DataFrame
    file1_data: pd.DataFrame
    file2_data: pd.DataFrame
    metadata: dict[str, Any]


@dataclass
class DifferenceDetail:
    """Детальная информация о различии"""

    column: str
    old_value: Any
    new_value: Any
    difference_type: str
    description: str


class IFileLoader(ABC):
    """Интерфейс для загрузки файлов"""

    @abstractmethod
    def can_load(self, file_path: Path) -> bool:
        """Проверяет, может ли загрузчик обработать данный файл"""
        pass

    @abstractmethod
    def load(self, file_path: Path, **kwargs) -> pd.DataFrame:
        """Загружает файл и возвращает DataFrame"""
        pass

    @abstractmethod
    def get_supported_extensions(self) -> list[str]:
        """Возвращает список поддерживаемых расширений"""
        pass


class IComparator(ABC):
    """Интерфейс для сравнения данных"""

    @abstractmethod
    def compare(self, df1: pd.DataFrame, df2: pd.DataFrame, **options) -> ComparisonResult:
        """Сравнивает два DataFrame и возвращает результат"""
        pass

    @abstractmethod
    def get_name(self) -> str:
        """Возвращает название компаратора"""
        pass


class IDifferenceAnalyzer(ABC):
    """Интерфейс для анализа различий"""

    @abstractmethod
    def analyze(self, old_value: Any, new_value: Any, column: str) -> DifferenceDetail:
        """Анализирует различие между двумя значениями"""
        pass

    @abstractmethod
    def can_analyze(self, old_value: Any, new_value: Any) -> bool:
        """Проверяет, может ли анализатор обработать данные значения"""
        pass


class IOutputFormatter(ABC):
    """Интерфейс для форматирования вывода"""

    @abstractmethod
    def format(self, result: ComparisonResult, output_path: Path, **options) -> None:
        """Форматирует и сохраняет результат сравнения"""
        pass

    @abstractmethod
    def get_supported_formats(self) -> list[str]:
        """Возвращает список поддерживаемых форматов"""
        pass


class IProgressObserver(Protocol):
    """Наблюдатель за прогрессом (Observer Pattern)"""

    def on_progress(self, current: int, total: int, message: str = "") -> None:
        """Вызывается при обновлении прогресса"""
        pass

    def on_error(self, error: Exception) -> None:
        """Вызывается при возникновении ошибки"""
        pass

    def on_completion(self, message: str = "") -> None:
        """Вызывается при завершении операции"""
        pass


class IProgressReporter(ABC):
    """Интерфейс для отчетов о прогрессе (Subject в паттерне Observer)"""

    @abstractmethod
    def add_observer(self, observer: IProgressObserver) -> None:
        """Добавляет наблюдателя"""
        pass

    @abstractmethod
    def remove_observer(self, observer: IProgressObserver) -> None:
        """Удаляет наблюдателя"""
        pass

    @abstractmethod
    def report_progress(self, current: int, total: int, message: str = "") -> None:
        """Сообщает о текущем прогрессе"""
        pass

    @abstractmethod
    def report_error(self, error: Exception) -> None:
        """Сообщает об ошибке"""
        pass

    @abstractmethod
    def report_completion(self, message: str = "") -> None:
        """Сообщает о завершении операции"""
        pass


class ProgressReporter(IProgressReporter):
    """Базовая реализация репортера прогресса"""

    def __init__(self):
        """Инициализация репортера прогресса"""
        self._observers: set[IProgressObserver] = set()

    def add_observer(self, observer: IProgressObserver) -> None:
        """Добавляет наблюдателя"""
        self._observers.add(observer)

    def remove_observer(self, observer: IProgressObserver) -> None:
        """Удаляет наблюдателя"""
        self._observers.discard(observer)

    def report_progress(self, current: int, total: int, message: str = "") -> None:
        """Сообщает о текущем прогрессе"""
        for observer in self._observers:
            observer.on_progress(current, total, message)

    def report_error(self, error: Exception) -> None:
        """Сообщает об ошибке"""
        for observer in self._observers:
            observer.on_error(error)

    def report_completion(self, message: str = "") -> None:
        """Сообщает о завершении операции"""
        for observer in self._observers:
            observer.on_completion(message)


class IValidationRule(ABC):
    """Интерфейс для правил валидации"""

    @abstractmethod
    def validate(self, df1: pd.DataFrame, df2: pd.DataFrame) -> list[str]:
        """Валидирует данные перед сравнением. Возвращает список ошибок"""
        pass

    @abstractmethod
    def get_rule_name(self) -> str:
        """Возвращает название правила"""
        pass


class IComparisonStrategy(ABC):
    """Стратегия сравнения (Strategy Pattern)"""

    @abstractmethod
    def execute(
        self,
        file1: Path,
        file2: Path,
        output: Path,
        progress_reporter: IProgressReporter | None = None,
        **options,
    ) -> ComparisonResult:
        """Выполняет полный цикл сравнения"""
        pass
