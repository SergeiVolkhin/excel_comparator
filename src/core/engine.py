"""
Движок сравнения файлов - центральный компонент системы
"""

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pandas as pd

    from .config import AppConfig

from ..comparators.advanced_comparator import AdvancedComparator
from ..comparators.basic_comparator import BasicComparator
from ..formatters.csv_formatter import CSVOutputFormatter
from ..formatters.excel_formatter import ExcelOutputFormatter
from ..formatters.html_formatter import HTMLOutputFormatter
from ..loaders.csv_loader import CSVFileLoader
from ..loaders.excel_loader import ExcelFileLoader
from .exceptions import ApplicationError, UnsupportedFormatError, ValidationError
from .interfaces import (
    ComparisonResult,
    IComparator,
    IComparisonStrategy,
    IFileLoader,
    IOutputFormatter,
    IProgressReporter,
    IValidationRule,
)

#: Общий прогресс по этапам (проценты в конце этапа): загрузка обоих файлов,
#: начало сравнения, сравнение готово, отчёт записан. Между PROGRESS_COMPARED
#: и PROGRESS_REPORTED движется отметка записи отчёта (обратный вызов
#: форматтера), 100 — всё готово.
PROGRESS_LOADED = 40
PROGRESS_COMPARING = 42
PROGRESS_COMPARED = 55
PROGRESS_REPORTED = 99


class ComparisonEngine:
    """Основной движок для сравнения файлов"""

    def __init__(self, config: "AppConfig | None" = None) -> None:
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)

        # Реестры компонентов
        self._file_loaders: list[IFileLoader] = []
        self._comparators: dict[str, IComparator] = {}
        self._formatters: dict[str, IOutputFormatter] = {}
        self._validation_rules: list[IValidationRule] = []

        # Регистрируем компоненты по умолчанию
        self._register_default_components()

    def _register_default_components(self) -> None:
        """Регистрирует компоненты по умолчанию"""
        # Загрузчики файлов
        self.register_file_loader(ExcelFileLoader())
        self.register_file_loader(CSVFileLoader())

        # Компараторы
        self.register_comparator("basic", BasicComparator())
        self.register_comparator("advanced", AdvancedComparator())

        # Форматтеры
        self.register_formatter("excel", ExcelOutputFormatter(self.config))
        self.register_formatter("html", HTMLOutputFormatter(self.config))
        self.register_formatter("csv", CSVOutputFormatter(self.config))

    def register_file_loader(self, loader: IFileLoader) -> None:
        """Регистрирует загрузчик файлов"""
        self._file_loaders.append(loader)
        self.logger.info(f"Зарегистрирован загрузчик: {loader.__class__.__name__}")

    def register_comparator(self, name: str, comparator: IComparator) -> None:
        """Регистрирует компаратор"""
        self._comparators[name] = comparator
        self.logger.info(f"Зарегистрирован компаратор '{name}': {comparator.__class__.__name__}")

    def register_formatter(self, name: str, formatter: IOutputFormatter) -> None:
        """Регистрирует форматтер"""
        self._formatters[name] = formatter
        self.logger.info(f"Зарегистрирован форматтер '{name}': {formatter.__class__.__name__}")

    def register_validation_rule(self, rule: IValidationRule) -> None:
        """Регистрирует правило валидации"""
        self._validation_rules.append(rule)
        self.logger.info(f"Зарегистрировано правило валидации: {rule.__class__.__name__}")

    def get_available_comparators(self) -> list[str]:
        """Возвращает список доступных компараторов"""
        return list(self._comparators.keys())

    def get_available_formatters(self) -> list[str]:
        """Возвращает список доступных форматтеров"""
        return list(self._formatters.keys())

    def get_supported_file_extensions(self) -> list[str]:
        """Возвращает список поддерживаемых расширений файлов"""
        extensions = []
        for loader in self._file_loaders:
            extensions.extend(loader.get_supported_extensions())
        return list(set(extensions))

    def _determine_formatter(self, output_path: Path) -> str:
        """Определяет форматтер на основе расширения выходного файла"""
        suffix = output_path.suffix.lower()

        if suffix in [".xlsx", ".xls"]:
            return "excel"
        elif suffix in [".html", ".htm"]:
            return "html"
        elif suffix == ".csv":
            return "csv"
        else:
            # По умолчанию используем Excel
            return "excel"

    def compare_files(
        self,
        file1_path: Path,
        file2_path: Path,
        output_path: Path,
        comparator_name: str = "advanced",
        formatter_name: str | None = None,
        progress_reporter: IProgressReporter | None = None,
        **options: Any,
    ) -> ComparisonResult:
        """Выполняет полное сравнение файлов"""
        try:
            self._report(progress_reporter, 0, "Загрузка файлов…")

            if formatter_name is None:
                formatter_name = self._determine_formatter(output_path)
                self.logger.info(f"Автоматически выбран форматтер: {formatter_name}")

            df1, df2 = self._load_pair(file1_path, file2_path, options, progress_reporter)
            load_info = self._check_loaded_pair(df1, df2)

            self._validate_data(df1, df2)
            self._report(progress_reporter, PROGRESS_COMPARING, "Сравнение данных…")

            result = self._run_comparison(df1, df2, comparator_name, options)
            if load_info:
                result.metadata.setdefault("load_info", load_info)
            self._report(progress_reporter, PROGRESS_COMPARED, "Сравнение выполнено")

            self._run_formatter(
                result,
                output_path,
                formatter_name,
                file1_path,
                file2_path,
                options,
                self._stage_progress(progress_reporter, PROGRESS_COMPARED, PROGRESS_REPORTED),
            )
            self._report(progress_reporter, 100, "Сравнение завершено")
            if progress_reporter:
                progress_reporter.report_completion(f"Результат сохранен в {output_path}")

            self.logger.info(f"Сравнение успешно завершено: {output_path}")
            return result

        except Exception as e:
            if progress_reporter:
                progress_reporter.report_error(e)

            self.logger.error(f"Ошибка при сравнении файлов: {e}", exc_info=True)
            raise

    @staticmethod
    def _report(reporter: IProgressReporter | None, percent: int, message: str) -> None:
        if reporter:
            reporter.report_progress(percent, 100, message)

    def _stage_progress(
        self, reporter: IProgressReporter | None, start: int, end: int
    ) -> Callable[[float, str], None] | None:
        """Обратный вызов для этапа: доля 0..1 → проценты ``start``..``end``.

        Повтор того же процента с тем же текстом не отправляется, чтобы не
        засорять очередь событий окна.
        """
        if reporter is None:
            return None
        last: list[tuple[int, str]] = []

        def report(share: float, message: str) -> None:
            percent = start + int((end - start) * min(max(share, 0.0), 1.0))
            if last and last[0] == (percent, message):
                return
            last[:] = [(percent, message)]
            self._report(reporter, percent, message)

        return report

    def _load_pair(
        self,
        file1_path: Path,
        file2_path: Path,
        options: dict[str, Any],
        reporter: IProgressReporter | None = None,
    ) -> tuple["pd.DataFrame", "pd.DataFrame"]:
        """Загружает оба файла одновременно.

        calamine разбирает xlsx в Rust, отпуская GIL, поэтому два потока
        читают пару файлов примерно на четверть быстрее, чем по очереди.
        """
        self.logger.info(f"Загрузка файлов: {file1_path.name} и {file2_path.name}")
        loader_options = options.get("loader_options", {})
        loader1 = self._find_file_loader(file1_path)
        loader2 = self._find_file_loader(file2_path)
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="load") as pool:
            future1 = pool.submit(loader1.load, file1_path, **loader_options)
            future2 = pool.submit(loader2.load, file2_path, **loader_options)
            names = {future1: file1_path.name, future2: file2_path.name}
            for loaded, future in enumerate(as_completed(names), start=1):
                future.result()  # ошибка загрузки — сразу, не дожидаясь второго файла
                self._report(
                    reporter,
                    PROGRESS_LOADED * loaded // 2,
                    f"Загружен «{names[future]}» ({loaded} из 2)",
                )
        return future1.result(), future2.result()

    def _check_loaded_pair(self, df1: "pd.DataFrame", df2: "pd.DataFrame") -> dict[str, Any]:
        """Сверяет форму загруженных таблиц и логирует расхождения.

        Не бросает исключений: только заранее предупреждает о разном числе
        столбцов/строк. Cell-level сравнение это уже умеет переживать, но
        «тихое» расхождение прежде было сюрпризом для пользователя. Возвращает
        небольшой словарь, который движок дописывает в ``result.metadata``.
        """
        info: dict[str, Any] = {}

        cols1, cols2 = df1.shape[1], df2.shape[1]
        if cols1 != cols2:
            self.logger.warning(f"Разное число столбцов: {cols1} vs {cols2}")
            info["column_count_mismatch"] = (cols1, cols2)

        rows1, rows2 = df1.shape[0], df2.shape[0]
        if rows1 != rows2:
            delta = abs(rows1 - rows2)
            self.logger.info(f"Разное число строк: {rows1} vs {rows2} (Δ={delta})")
            info["row_count_delta"] = delta

        return info

    def _run_comparison(
        self,
        df1: "pd.DataFrame",
        df2: "pd.DataFrame",
        comparator_name: str,
        options: dict[str, Any],
    ) -> ComparisonResult:
        comparator = self._get_comparator(comparator_name)
        comparison_options: dict[str, Any] = dict(options.get("comparison_options", {}))
        if self.config:
            comparison_options.setdefault(
                "ignore_case",
                getattr(self.config.comparison, "ignore_case", False),
            )
            comparison_options.setdefault(
                "ignore_whitespace",
                getattr(self.config.comparison, "ignore_whitespace", False),
            )
            comparison_options.setdefault(
                "ignore_row_order",
                getattr(self.config.comparison, "ignore_row_order", False),
            )
        return comparator.compare(df1, df2, **comparison_options)

    def _run_formatter(
        self,
        result: ComparisonResult,
        output_path: Path,
        formatter_name: str,
        file1_path: Path,
        file2_path: Path,
        options: dict[str, Any],
        progress: Callable[[float, str], None] | None = None,
    ) -> None:
        formatter = self._get_formatter(formatter_name)
        format_options: dict[str, Any] = dict(options.get("format_options", {}))
        format_options.update({"file1_name": file1_path.stem, "file2_name": file2_path.stem})
        format_options.setdefault(
            "first_data_row", self._first_data_row(options.get("loader_options", {}))
        )
        if progress is not None:
            format_options.setdefault("progress", progress)
        formatter.format(result, output_path, **format_options)

    @staticmethod
    def _first_data_row(loader_options: dict[str, Any]) -> int:
        """Номер (с 1) первой строки данных в исходном файле.

        По умолчанию строка 1 — заголовок, данные со строки 2. Учитывает
        строку заголовка (``header``) и пропуск первых строк CSV
        (``skiprows``, если это число).
        """
        skipped = loader_options.get("skiprows", 0)
        if not isinstance(skipped, int):
            skipped = 0
        header = loader_options.get("header", 0)
        if header is None:
            return skipped + 1
        return skipped + int(header) + 2

    def _find_file_loader(self, file_path: Path) -> IFileLoader:
        """Находит подходящий загрузчик для файла"""
        for loader in self._file_loaders:
            if loader.can_load(file_path):
                return loader

        supported_extensions = self.get_supported_file_extensions()
        raise UnsupportedFormatError(file_path.suffix, supported_extensions)

    def _get_comparator(self, name: str) -> IComparator:
        """Получает компаратор по имени"""
        if name not in self._comparators:
            available = list(self._comparators.keys())
            raise ApplicationError(
                f"Компаратор '{name}' не найден. Доступные: {', '.join(available)}"
            )

        return self._comparators[name]

    def _get_formatter(self, name: str) -> IOutputFormatter:
        """Получает форматтер по имени"""
        if name not in self._formatters:
            available = list(self._formatters.keys())
            raise ApplicationError(
                f"Форматтер '{name}' не найден. Доступные: {', '.join(available)}"
            )

        return self._formatters[name]

    def _validate_data(self, df1: "pd.DataFrame", df2: "pd.DataFrame") -> None:
        """Выполняет валидацию данных"""
        errors: list[str] = []

        for rule in self._validation_rules:
            rule_errors = rule.validate(df1, df2)
            errors.extend(rule_errors)

        if errors:
            raise ValidationError(errors)


class StandardComparisonStrategy(IComparisonStrategy):
    """Стандартная стратегия сравнения"""

    def __init__(self, engine: ComparisonEngine) -> None:
        self.engine = engine
        self.logger = logging.getLogger(self.__class__.__name__)

    def execute(
        self,
        file1: Path,
        file2: Path,
        output: Path,
        progress_reporter: IProgressReporter | None = None,
        **options: Any,
    ) -> ComparisonResult:
        """Выполняет стандартное сравнение файлов"""
        # Pop rather than get: compare_files accepts comparator_name and
        # formatter_name as explicit kwargs, so leaving them in **options
        # would cause a TypeError ("multiple values for keyword argument").
        comparator_name = options.pop("comparator_name", "advanced")
        formatter_name = options.pop("formatter_name", None)

        return self.engine.compare_files(
            file1,
            file2,
            output,
            comparator_name=comparator_name,
            formatter_name=formatter_name,
            progress_reporter=progress_reporter,
            **options,
        )
