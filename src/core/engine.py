"""
Движок сравнения файлов - центральный компонент системы
"""

from pathlib import Path
from typing import List, Optional, Dict, Any
import logging

from .interfaces import (
    IFileLoader, IComparator, IOutputFormatter, 
    IProgressReporter, IValidationRule, IComparisonStrategy,
    ComparisonResult
)
from .exceptions import ApplicationError, FileLoadError, UnsupportedFormatError, ValidationError
from ..loaders.excel_loader import ExcelFileLoader
from ..comparators.basic_comparator import BasicComparator
from ..comparators.advanced_comparator import AdvancedComparator
from ..formatters.excel_formatter import ExcelOutputFormatter
from ..formatters.html_formatter import HTMLOutputFormatter


class ComparisonEngine:
    """Основной движок для сравнения файлов"""
    
    def __init__(self, config=None):
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Реестры компонентов
        self._file_loaders: List[IFileLoader] = []
        self._comparators: Dict[str, IComparator] = {}
        self._formatters: Dict[str, IOutputFormatter] = {}
        self._validation_rules: List[IValidationRule] = []
        
        # Регистрируем компоненты по умолчанию
        self._register_default_components()
    
    def _register_default_components(self) -> None:
        """Регистрирует компоненты по умолчанию"""
        # Загрузчики файлов
        self.register_file_loader(ExcelFileLoader())
        
        # Компараторы
        self.register_comparator("basic", BasicComparator())
        self.register_comparator("advanced", AdvancedComparator())
        
        # Форматтеры
        self.register_formatter("excel", ExcelOutputFormatter(self.config))
        self.register_formatter("html", HTMLOutputFormatter(self.config))
    
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
    
    def get_available_comparators(self) -> List[str]:
        """Возвращает список доступных компараторов"""
        return list(self._comparators.keys())
    
    def get_available_formatters(self) -> List[str]:
        """Возвращает список доступных форматтеров"""
        return list(self._formatters.keys())
    
    def get_supported_file_extensions(self) -> List[str]:
        """Возвращает список поддерживаемых расширений файлов"""
        extensions = []
        for loader in self._file_loaders:
            extensions.extend(loader.get_supported_extensions())
        return list(set(extensions))
    
    def _determine_formatter(self, output_path: Path) -> str:
        """Определяет форматтер на основе расширения выходного файла"""
        suffix = output_path.suffix.lower()
        
        if suffix in ['.xlsx', '.xls']:
            return 'excel'
        elif suffix in ['.html', '.htm']:
            return 'html'
        else:
            # По умолчанию используем Excel
            return 'excel'
    
    def compare_files(
        self,
        file1_path: Path,
        file2_path: Path,
        output_path: Path,
        comparator_name: str = "advanced",  # По умолчанию используем улучшенный компаратор
        formatter_name: str = None,  # Автоопределение по расширению
        progress_reporter: Optional[IProgressReporter] = None,
        **options
    ) -> ComparisonResult:
        """Выполняет полное сравнение файлов"""
        
        try:
            if progress_reporter:
                progress_reporter.report_progress(0, 100, "Начало сравнения...")
            
            # Определяем форматтер, если не указан
            if formatter_name is None:
                formatter_name = self._determine_formatter(output_path)
                self.logger.info(f"Автоматически выбран форматтер: {formatter_name}")
            
            # 1. Загружаем файлы
            self.logger.info(f"Загрузка файлов: {file1_path.name} и {file2_path.name}")
            
            loader1 = self._find_file_loader(file1_path)
            loader2 = self._find_file_loader(file2_path)
            
            df1 = loader1.load(file1_path, **options.get('loader_options', {}))
            df2 = loader2.load(file2_path, **options.get('loader_options', {}))
            
            if progress_reporter:
                progress_reporter.report_progress(20, 100, "Файлы загружены")
            
            # 2. Валидация
            self._validate_data(df1, df2)
            
            if progress_reporter:
                progress_reporter.report_progress(30, 100, "Валидация выполнена")
            
            # 3. Сравнение
            comparator = self._get_comparator(comparator_name)
            comparison_options = options.get('comparison_options', {})
            
            # Добавляем опции из конфигурации
            if self.config:
                comparison_options.update({
                    'ignore_case': getattr(self.config.comparison, 'ignore_case', False),
                    'ignore_whitespace': getattr(self.config.comparison, 'ignore_whitespace', False),
                })
            
            result = comparator.compare(df1, df2, **comparison_options)
            
            if progress_reporter:
                progress_reporter.report_progress(70, 100, "Сравнение выполнено")
            
            # 4. Форматирование и сохранение
            formatter = self._get_formatter(formatter_name)
            
            format_options = options.get('format_options', {})
            format_options.update({
                'file1_name': file1_path.stem,
                'file2_name': file2_path.stem
            })
            
            formatter.format(result, output_path, **format_options)
            
            if progress_reporter:
                progress_reporter.report_progress(100, 100, "Сравнение завершено")
                progress_reporter.report_completion(f"Результат сохранен в {output_path}")
            
            self.logger.info(f"Сравнение успешно завершено: {output_path}")
            
            return result
            
        except Exception as e:
            if progress_reporter:
                progress_reporter.report_error(e)
            
            self.logger.error(f"Ошибка при сравнении файлов: {e}", exc_info=True)
            raise
    
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
    
    def _validate_data(self, df1, df2) -> None:
        """Выполняет валидацию данных"""
        errors = []
        
        for rule in self._validation_rules:
            rule_errors = rule.validate(df1, df2)
            errors.extend(rule_errors)
        
        if errors:
            raise ValidationError(errors)


class StandardComparisonStrategy(IComparisonStrategy):
    """Стандартная стратегия сравнения"""
    
    def __init__(self, engine: ComparisonEngine):
        self.engine = engine
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def execute(
        self,
        file1: Path,
        file2: Path,
        output: Path,
        progress_reporter: Optional[IProgressReporter] = None,
        **options
    ) -> ComparisonResult:
        """Выполняет стандартное сравнение файлов"""
        # Устанавливаем компаратор по умолчанию, если не указан
        comparator_name = options.get('comparator_name', 'advanced')
        
        # Определяем форматтер на основе расширения файла, если не указан
        formatter_name = options.get('formatter_name', None)
        
        return self.engine.compare_files(
            file1, file2, output,
            comparator_name=comparator_name,
            formatter_name=formatter_name,
            progress_reporter=progress_reporter,
            **options
        )