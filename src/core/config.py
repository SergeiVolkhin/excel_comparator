"""Application configuration (migrated to pydantic v2 / pydantic-settings).

Public contract preserved:
    ComparisonSettings, GUISettings, AppConfig, ConfigFormat,
    ConfigValidationError. All existing field names, method signatures
    and behaviour match the previous dataclass-based implementation.
"""

from __future__ import annotations

import json
import logging
import os
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ConfigValidationError(Exception):
    """Ошибка валидации конфигурации"""


class ConfigFormat(Enum):
    """Форматы файлов конфигурации"""

    JSON = "json"


class ComparisonSettings(BaseModel):
    """Настройки сравнения"""

    model_config = ConfigDict(validate_assignment=False)

    ignore_case: bool = False
    ignore_whitespace: bool = False
    highlight_color: str = "FFFF00"
    max_differences_display: int = 1000
    enable_list_analysis: bool = True
    list_separator: str = ","

    def validate(self) -> list[str]:  # type: ignore[override]
        """Проверяет корректность настроек, возвращает список ошибок."""
        errors: list[str] = []
        if not isinstance(self.highlight_color, str) or len(self.highlight_color) != 6:
            errors.append("Цвет подсветки должен быть в формате RRGGBB (6 символов)")
        if not isinstance(self.max_differences_display, int) or self.max_differences_display <= 0:
            errors.append(
                "Максимальное количество отображаемых различий должно быть положительным числом"
            )
        return errors


class GUISettings(BaseModel):
    """Настройки интерфейса"""

    model_config = ConfigDict(validate_assignment=False)

    window_width: int = 800
    window_height: int = 600
    theme: str = "default"
    font_family: str = "Arial"
    font_size: int = 10

    def validate(self) -> list[str]:  # type: ignore[override]
        """Проверяет корректность настроек, возвращает список ошибок."""
        errors: list[str] = []
        if not isinstance(self.window_width, int) or self.window_width < 300:
            errors.append("Ширина окна должна быть не менее 300 пикселей")
        if not isinstance(self.window_height, int) or self.window_height < 200:
            errors.append("Высота окна должна быть не менее 200 пикселей")
        if not isinstance(self.font_size, int) or self.font_size < 8 or self.font_size > 24:
            errors.append("Размер шрифта должен быть в диапазоне от 8 до 24")
        return errors


def _default_app_data_dir() -> Path:
    """Return the per-platform directory used to store config/state."""
    if os.name == "nt":
        app_data = os.environ.get("APPDATA", "")
        return Path(app_data) / "ExcelComparator" if app_data else Path.cwd()
    home = os.environ.get("HOME", "")
    return Path(home) / ".config" / "excel-comparator" if home else Path.cwd()


class AppConfig(BaseModel):
    """Главная конфигурация приложения"""

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        validate_assignment=False,
    )

    comparison: ComparisonSettings = Field(default_factory=ComparisonSettings)
    gui: GUISettings = Field(default_factory=GUISettings)
    log_level: str = "INFO"
    auto_save_config: bool = True
    recent_files: list[str] = Field(default_factory=list)
    max_recent_files: int = 10
    config_format: ConfigFormat = ConfigFormat.JSON

    # Runtime-only attributes (excluded from serialization)
    config_path: Path = Field(default=Path("config.json"), exclude=True)

    def model_post_init(self, _context: Any) -> None:
        """Инициализация после создания объекта"""
        self.logger = logging.getLogger(self.__class__.__name__)

        app_data_dir = _default_app_data_dir()
        # Mutate private attribute directly: BaseModel forbids unknown attrs
        object.__setattr__(
            self,
            "config_path",
            app_data_dir / f"config.{self.config_format.value}",
        )
        app_data_dir.mkdir(parents=True, exist_ok=True)

    def __setattr__(self, name: str, value: Any) -> None:
        # Allow setting the runtime-only `logger` and `config_path` like the
        # previous dataclass implementation did.
        if name in {"logger", "config_path"}:
            object.__setattr__(self, name, value)
        else:
            super().__setattr__(name, value)

    # ------------------------------------------------------------------
    # Back-compat helper used by some legacy paths
    # ------------------------------------------------------------------
    def _get_app_data_dir(self) -> Path:
        return _default_app_data_dir()

    # ------------------------------------------------------------------
    # File IO — kept in the same module for minimal diff; can be extracted
    # to src/core/config_io.py in a later refactor step.
    # ------------------------------------------------------------------
    def load_config(self) -> None:
        """Загружает конфигурацию из файла"""
        if not self.config_path.exists():
            self.logger.info(
                "Файл конфигурации не найден, используются настройки по умолчанию"
            )
            return

        try:
            with open(self.config_path, encoding="utf-8") as f:
                if self.config_format == ConfigFormat.JSON:
                    config_data = json.load(f)

            if "comparison" in config_data:
                for key, value in config_data["comparison"].items():
                    if hasattr(self.comparison, key):
                        setattr(self.comparison, key, value)

            if "gui" in config_data:
                for key, value in config_data["gui"].items():
                    if hasattr(self.gui, key):
                        setattr(self.gui, key, value)

            for key in ["log_level", "auto_save_config", "recent_files", "max_recent_files"]:
                if key in config_data:
                    setattr(self, key, config_data[key])

            self.validate()
            self.logger.info("Конфигурация успешно загружена")

        except Exception as e:
            self.logger.error(f"Ошибка загрузки конфигурации: {e}")

    def save_config(self) -> None:
        """Сохраняет конфигурацию в файл"""
        try:
            self.validate()

            config_data: dict[str, Any] = {
                "comparison": self.comparison.model_dump(),
                "gui": self.gui.model_dump(),
                "log_level": self.log_level,
                "auto_save_config": self.auto_save_config,
                "recent_files": self.recent_files[-self.max_recent_files :],
                "max_recent_files": self.max_recent_files,
            }

            if isinstance(self.config_format, Enum):
                config_data["config_format"] = self.config_format.value

            with open(self.config_path, "w", encoding="utf-8") as f:
                if self.config_format == ConfigFormat.JSON:
                    json.dump(config_data, f, indent=2, ensure_ascii=False)

            self.logger.info(f"Конфигурация успешно сохранена в {self.config_path}")

        except Exception as e:
            self.logger.error(f"Ошибка сохранения конфигурации: {e}")

    def validate(self) -> None:  # type: ignore[override]
        """Проверяет корректность конфигурации (только логирование, не raise)."""
        errors: list[str] = []
        errors.extend(self.comparison.validate())
        errors.extend(self.gui.validate())

        if self.log_level not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            errors.append(f"Некорректный уровень логирования: {self.log_level}")

        if not isinstance(self.max_recent_files, int) or self.max_recent_files <= 0:
            errors.append(
                "Максимальное количество недавних файлов должно быть положительным числом"
            )

        if errors:
            error_message = "Ошибки валидации конфигурации:\n" + "\n".join(errors)
            self.logger.warning(error_message)

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
        if self.auto_save_config:
            self.save_config()
