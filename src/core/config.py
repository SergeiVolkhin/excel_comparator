"""
Конфигурация приложения
"""

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path


class ConfigValidationError(Exception):
    """Ошибка валидации конфигурации"""

    pass


class ConfigFormat(Enum):
    """Форматы файлов конфигурации"""

    JSON = "json"
    # Можно добавить поддержку других форматов в будущем
    # YAML = "yaml"
    # INI = "ini"


@dataclass
class ComparisonSettings:
    """Настройки сравнения"""

    ignore_case: bool = False
    ignore_whitespace: bool = False
    highlight_color: str = "FFFF00"
    max_differences_display: int = 1000
    enable_list_analysis: bool = True
    list_separator: str = ","

    def validate(self) -> list[str]:
        """Проверяет корректность настроек"""
        errors = []

        # Проверка формата цвета
        if not isinstance(self.highlight_color, str) or len(self.highlight_color) != 6:
            errors.append("Цвет подсветки должен быть в формате RRGGBB (6 символов)")

        # Проверка числовых значений
        if not isinstance(self.max_differences_display, int) or self.max_differences_display <= 0:
            errors.append(
                "Максимальное количество отображаемых различий должно быть положительным числом"
            )

        return errors


@dataclass
class GUISettings:
    """Настройки интерфейса"""

    window_width: int = 800
    window_height: int = 600
    theme: str = "default"
    font_family: str = "Arial"
    font_size: int = 10

    def validate(self) -> list[str]:
        """Проверяет корректность настроек"""
        errors = []

        # Проверка размеров окна
        if not isinstance(self.window_width, int) or self.window_width < 300:
            errors.append("Ширина окна должна быть не менее 300 пикселей")

        if not isinstance(self.window_height, int) or self.window_height < 200:
            errors.append("Высота окна должна быть не менее 200 пикселей")

        # Проверка размера шрифта
        if not isinstance(self.font_size, int) or self.font_size < 8 or self.font_size > 24:
            errors.append("Размер шрифта должен быть в диапазоне от 8 до 24")

        return errors


@dataclass
class AppConfig:
    """Главная конфигурация приложения"""

    comparison: ComparisonSettings = field(default_factory=ComparisonSettings)
    gui: GUISettings = field(default_factory=GUISettings)
    log_level: str = "INFO"
    auto_save_config: bool = True
    recent_files: list[str] = field(default_factory=list)
    max_recent_files: int = 10
    config_format: ConfigFormat = ConfigFormat.JSON

    def __post_init__(self):
        """Инициализация после создания объекта"""
        self.logger = logging.getLogger(self.__class__.__name__)

        # Определяем путь к файлу конфигурации
        app_data_dir = self._get_app_data_dir()
        self.config_path = app_data_dir / f"config.{self.config_format.value}"

        # Убеждаемся, что директория существует
        app_data_dir.mkdir(parents=True, exist_ok=True)

    def _get_app_data_dir(self) -> Path:
        """Возвращает директорию для хранения данных приложения"""
        if os.name == "nt":  # Windows
            app_data = os.environ.get("APPDATA", "")
            if not app_data:
                return Path.cwd()
            return Path(app_data) / "ExcelComparator"
        else:  # Linux/Mac
            home = os.environ.get("HOME", "")
            if not home:
                return Path.cwd()
            return Path(home) / ".config" / "excel-comparator"

    def load_config(self) -> None:
        """Загружает конфигурацию из файла"""
        if not self.config_path.exists():
            self.logger.info("Файл конфигурации не найден, используются настройки по умолчанию")
            return

        try:
            with open(self.config_path, encoding="utf-8") as f:
                if self.config_format == ConfigFormat.JSON:
                    config_data = json.load(f)
                # Здесь можно добавить поддержку других форматов

            # Обновляем настройки из файла
            if "comparison" in config_data:
                for key, value in config_data["comparison"].items():
                    if hasattr(self.comparison, key):
                        setattr(self.comparison, key, value)

            if "gui" in config_data:
                for key, value in config_data["gui"].items():
                    if hasattr(self.gui, key):
                        setattr(self.gui, key, value)

            # Загружаем остальные настройки
            for key in ["log_level", "auto_save_config", "recent_files", "max_recent_files"]:
                if key in config_data:
                    setattr(self, key, config_data[key])

            # Валидируем загруженную конфигурацию
            self.validate()

            self.logger.info("Конфигурация успешно загружена")

        except Exception as e:
            self.logger.error(f"Ошибка загрузки конфигурации: {e}")

    def save_config(self) -> None:
        """Сохраняет конфигурацию в файл"""
        try:
            # Валидируем перед сохранением
            self.validate()

            # Преобразуем dataclass в словарь, но обрабатываем вложенные dataclass
            config_data = {
                "comparison": asdict(self.comparison),
                "gui": asdict(self.gui),
                "log_level": self.log_level,
                "auto_save_config": self.auto_save_config,
                "recent_files": self.recent_files[-self.max_recent_files :],
                "max_recent_files": self.max_recent_files,
            }

            # Сериализуем enum-ы
            if hasattr(self, "config_format") and isinstance(self.config_format, Enum):
                config_data["config_format"] = self.config_format.value

            with open(self.config_path, "w", encoding="utf-8") as f:
                if self.config_format == ConfigFormat.JSON:
                    json.dump(config_data, f, indent=2, ensure_ascii=False)
                # Здесь можно добавить поддержку других форматов

            self.logger.info(f"Конфигурация успешно сохранена в {self.config_path}")

        except Exception as e:
            self.logger.error(f"Ошибка сохранения конфигурации: {e}")

    def validate(self) -> None:
        """Проверяет корректность конфигурации"""
        errors = []

        # Валидация вложенных настроек
        errors.extend(self.comparison.validate())
        errors.extend(self.gui.validate())

        # Валидация корневых настроек
        if self.log_level not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            errors.append(f"Некорректный уровень логирования: {self.log_level}")

        if not isinstance(self.max_recent_files, int) or self.max_recent_files <= 0:
            errors.append(
                "Максимальное количество недавних файлов должно быть положительным числом"
            )

        if errors:
            error_message = "Ошибки валидации конфигурации:\n" + "\n".join(errors)
            self.logger.warning(error_message)
            # Просто логируем ошибки, но не вызываем исключение, чтобы не блокировать работу

    def add_recent_file(self, file_path: str) -> None:
        """Добавляет файл в список недавних"""
        if file_path in self.recent_files:
            self.recent_files.remove(file_path)

        self.recent_files.insert(0, file_path)
        self.recent_files = self.recent_files[: self.max_recent_files]

        if self.auto_save_config:
            self.save_config()

    def get_recent_files(self) -> list[str]:
        """Возвращает список недавних файлов"""
        # Фильтруем несуществующие файлы
        existing_files = [f for f in self.recent_files if Path(f).exists()]
        if len(existing_files) != len(self.recent_files):
            self.recent_files = existing_files
            if self.auto_save_config:
                self.save_config()

        return self.recent_files

    def reset_to_defaults(self) -> None:
        """Сбрасывает настройки на значения по умолчанию"""
        self.comparison = ComparisonSettings()
        self.gui = GUISettings()
        self.log_level = "INFO"
        # Сохраняем список недавних файлов
        if self.auto_save_config:
            self.save_config()
