#!/usr/bin/env python3
"""
Excel Comparator - Программное обеспечение для сравнения Excel файлов
"""

import argparse
import io
import logging
import sys
import warnings
from pathlib import Path

# Подавляем предупреждения от сторонних библиотек
warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")
warnings.filterwarnings("ignore", category=FutureWarning, module="pandas")


def _reconfigure_stdout_for_windows() -> None:
    """Force UTF-8 on stdout for cp1251-locale consoles. Called only from
    __main__ so that importing this module under pytest (which captures
    stdout) doesn't break the test runner."""
    if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


def setup_logging(log_level: str = "INFO") -> None:
    """
    Настраивает систему логирования

    Args:
        log_level: Уровень логирования (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    numeric_level = getattr(logging, log_level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f"Некорректный уровень логирования: {log_level}")

    # Создаем директорию для логов, если она не существует
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    # Настраиваем корневой логгер
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_dir / "app.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def parse_arguments():
    """
    Парсит аргументы командной строки

    Returns:
        argparse.Namespace: Объект с аргументами командной строки
    """
    parser = argparse.ArgumentParser(description="Excel Comparator - Сравнение Excel файлов")

    parser.add_argument(
        "--gui", action="store_true", help="Запустить в режиме графического интерфейса"
    )

    parser.add_argument("--cli", action="store_true", help="Запустить в режиме командной строки")

    parser.add_argument("--file1", type=str, help="Путь к первому файлу")
    parser.add_argument("--file2", type=str, help="Путь ко второму файлу")
    parser.add_argument("--output", type=str, help="Путь к файлу результата")

    parser.add_argument(
        "--ignore-case", action="store_true", help="Игнорировать регистр при сравнении"
    )

    parser.add_argument(
        "--ignore-whitespace", action="store_true", help="Игнорировать пробелы при сравнении"
    )

    parser.add_argument(
        "--format",
        type=str,
        choices=["xlsx", "html", "csv"],
        default=None,
        help="Формат выходного файла. По умолчанию определяется по расширению --output.",
    )

    parser.add_argument(
        "--csv-encoding",
        type=str,
        default=None,
        help="Принудительная кодировка для CSV-входов (иначе — автодетект chardet).",
    )

    parser.add_argument(
        "--csv-delimiter",
        type=str,
        default=None,
        help="Принудительный разделитель для CSV-входов (иначе — автодетект).",
    )

    parser.add_argument(
        "--csv-skip-rows",
        type=int,
        default=None,
        help="Пропустить N первых строк при чтении CSV.",
    )

    parser.add_argument(
        "--chunk-size",
        type=int,
        default=None,
        help="Размер чанка при чтении CSV > 100 MB (по умолчанию 50000).",
    )

    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Уровень логирования",
    )

    return parser.parse_args()


def run_gui_mode(args):
    """
    Запускает приложение в режиме графического интерфейса

    Args:
        args: Аргументы командной строки
    """
    from src.core.config import AppConfig
    from src.gui.main_window import MainWindow

    # Загружаем конфигурацию
    config = AppConfig()

    # Применяем параметры командной строки, если они указаны
    if args.ignore_case:
        config.comparison.ignore_case = True

    if args.ignore_whitespace:
        config.comparison.ignore_whitespace = True

    if args.log_level:
        config.log_level = args.log_level.upper()

    # Запускаем GUI
    window = MainWindow(config)

    # Если указаны файлы в аргументах, предварительно заполняем поля
    if args.file1 and Path(args.file1).exists():
        window.file1_selector.set_path(args.file1)

    if args.file2 and Path(args.file2).exists():
        window.file2_selector.set_path(args.file2)

    if args.output:
        window.output_var.set(args.output)

    # Запускаем приложение
    window.run()


def run_cli_mode(args):
    """
    Запускает приложение в режиме командной строки

    Args:
        args: Аргументы командной строки
    """
    from src.core.config import AppConfig
    from src.core.engine import ComparisonEngine, StandardComparisonStrategy
    from src.core.interfaces import ProgressReporter

    logger = logging.getLogger("CLI")

    # Проверяем обязательные аргументы
    if not args.file1 or not args.file2 or not args.output:
        logger.error("Не указаны обязательные аргументы: --file1, --file2, --output")
        print("Ошибка: Необходимо указать --file1, --file2 и --output")
        sys.exit(1)

    # Проверяем существование файлов
    file1_path = Path(args.file1)
    file2_path = Path(args.file2)
    output_path = Path(args.output)

    if not file1_path.exists():
        logger.error(f"Файл не найден: {file1_path}")
        print(f"Ошибка: Файл не найден: {file1_path}")
        sys.exit(1)

    if not file2_path.exists():
        logger.error(f"Файл не найден: {file2_path}")
        print(f"Ошибка: Файл не найден: {file2_path}")
        sys.exit(1)

    # Создаем конфигурацию
    config = AppConfig()

    # Применяем параметры командной строки
    config.comparison.ignore_case = args.ignore_case
    config.comparison.ignore_whitespace = args.ignore_whitespace

    # Создаем движок сравнения
    engine = ComparisonEngine(config)
    strategy = StandardComparisonStrategy(engine)

    # Создаем репортер прогресса для CLI
    progress_reporter = ProgressReporter()

    class CLIProgressObserver:
        def on_progress(self, current, total, message=""):
            percent = (current / total) * 100 if total > 0 else 0
            print(f"\rПрогресс: [{current}/{total}] {percent:.1f}% {message}", end="")

        def on_error(self, error):
            print(f"\nОшибка: {error}")

        def on_completion(self, message=""):
            print(f"\n{message}")

    # Регистрируем наблюдателя прогресса
    cli_observer = CLIProgressObserver()
    progress_reporter.add_observer(cli_observer)

    try:
        # Выполняем сравнение
        print("Сравнение файлов:")
        print(f"  Файл 1: {file1_path}")
        print(f"  Файл 2: {file2_path}")
        print(f"  Результат будет сохранен в: {output_path}")
        print("")

        loader_options: dict = {}
        if args.csv_encoding is not None:
            loader_options["encoding"] = args.csv_encoding
        if args.csv_delimiter is not None:
            loader_options["sep"] = args.csv_delimiter
        if args.csv_skip_rows is not None:
            loader_options["skiprows"] = args.csv_skip_rows
        if args.chunk_size is not None:
            loader_options["chunk_size"] = args.chunk_size

        # CLI --format uses user-facing extension labels; the engine's
        # formatter registry keys them differently for xlsx.
        format_map = {"xlsx": "excel", "html": "html", "csv": "csv"}
        formatter_name = format_map[args.format] if args.format else None

        options = {
            "comparison_options": {
                "ignore_case": args.ignore_case,
                "ignore_whitespace": args.ignore_whitespace,
            },
            "loader_options": loader_options,
            "formatter_name": formatter_name,
            "file1_name": file1_path.name,
            "file2_name": file2_path.name,
        }

        result = strategy.execute(
            file1_path, file2_path, output_path, progress_reporter=progress_reporter, **options
        )

        # Выводим итоговую статистику
        total_cells = result.metadata.get("total_cells", 0)
        different_cells = result.metadata.get("different_cells", 0)
        similarity = result.metadata.get("similarity_percentage", 0)

        print("\nРезультаты сравнения:")
        print(f"  Всего ячеек: {total_cells}")
        print(f"  Различающихся ячеек: {different_cells}")
        print(f"  Схожесть: {similarity:.2f}%")
        print(f"\nРезультат сохранен в: {output_path}")

    except Exception as e:
        logger.exception("Ошибка при сравнении файлов")
        print(f"Ошибка при сравнении: {e}")
        sys.exit(1)


def main():
    """Главная функция приложения"""
    # Парсим аргументы командной строки
    args = parse_arguments()

    # Настраиваем логирование
    setup_logging(args.log_level)

    logger = logging.getLogger(__name__)
    logger.info("Запуск Excel Comparator")

    try:
        # Определяем режим запуска
        if args.cli:
            # Запускаем в режиме командной строки
            run_cli_mode(args)
        else:
            # По умолчанию или если указан --gui, запускаем GUI
            run_gui_mode(args)
    except Exception as e:
        logger.exception(f"Критическая ошибка: {e}")
        print(f"❌ Ошибка запуска: {e}")
        sys.exit(1)


if __name__ == "__main__":
    _reconfigure_stdout_for_windows()
    main()
