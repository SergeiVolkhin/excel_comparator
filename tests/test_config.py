"""Characterization tests for AppConfig (src/core/config.py)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from src.core.config import AppConfig, ComparisonSettings, ConfigFormat, GUISettings


@pytest.fixture
def config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AppConfig:
    # Redirect APPDATA / HOME so we don't touch user dirs.
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    cfg = AppConfig()
    cfg.auto_save_config = False  # don't write during tests
    return cfg


class TestDefaults:
    def test_comparison_defaults(self) -> None:
        s = ComparisonSettings()
        assert s.ignore_case is False
        assert s.highlight_color == "FFFF00"
        assert s.list_separator == ","

    def test_gui_defaults(self) -> None:
        g = GUISettings()
        assert g.window_width == 800
        assert g.theme == "default"

    def test_app_defaults(self, config: AppConfig) -> None:
        assert config.log_level == "INFO"
        assert config.config_format is ConfigFormat.JSON
        assert isinstance(config.comparison, ComparisonSettings)


class TestValidation:
    def test_comparison_bad_color(self) -> None:
        s = ComparisonSettings(highlight_color="XYZ")
        errors = s.validate()
        assert any("Цвет" in e for e in errors)

    def test_comparison_bad_max(self) -> None:
        s = ComparisonSettings(max_differences_display=-1)
        assert any("положительным" in e for e in s.validate())

    def test_gui_small_window(self) -> None:
        g = GUISettings(window_width=100)
        assert any("300" in e for e in g.validate())

    def test_gui_bad_font(self) -> None:
        g = GUISettings(font_size=999)
        assert any("шрифта" in e for e in g.validate())

    def test_app_bad_log_level(self, config: AppConfig) -> None:
        config.log_level = "NOPE"
        # validate() only logs, doesn't raise — verify it runs
        config.validate()


class TestPersistence:
    def test_load_missing_file_does_not_raise(self, config: AppConfig) -> None:
        # Fresh config_path doesn't exist yet
        if config.config_path.exists():
            config.config_path.unlink()
        config.load_config()

    def test_save_then_load_roundtrip(self, config: AppConfig) -> None:
        config.comparison.ignore_case = True
        config.log_level = "DEBUG"
        config.save_config()
        assert config.config_path.exists()

        # Read raw JSON to confirm structure
        data = json.loads(config.config_path.read_text(encoding="utf-8"))
        assert data["comparison"]["ignore_case"] is True
        assert data["log_level"] == "DEBUG"

        # Now load into a fresh object
        fresh = AppConfig()
        fresh.auto_save_config = False
        fresh.config_path = config.config_path
        fresh.load_config()
        assert fresh.comparison.ignore_case is True
        assert fresh.log_level == "DEBUG"

    def test_redundant_identical_save_is_skipped(
        self, config: AppConfig, caplog: pytest.LogCaptureFixture
    ) -> None:
        config.log_level = "DEBUG"
        config.save_config()  # first write
        assert config.config_path.exists()
        first_mtime = config.config_path.stat().st_mtime_ns

        # An identical second save must skip the write (content dirty-guard).
        with caplog.at_level(logging.DEBUG, logger="AppConfig"):
            config.save_config()
        assert any("не изменилась" in r.message for r in caplog.records)
        assert config.config_path.stat().st_mtime_ns == first_mtime

        # A real change must write again.
        caplog.clear()
        config.log_level = "WARNING"
        with caplog.at_level(logging.DEBUG, logger="AppConfig"):
            config.save_config()
        assert any("успешно сохранена" in r.message for r in caplog.records)
        data = json.loads(config.config_path.read_text(encoding="utf-8"))
        assert data["log_level"] == "WARNING"


class TestRecentFiles:
    def test_add_and_get(self, config: AppConfig, tmp_path: Path) -> None:
        existing = tmp_path / "f.xlsx"
        existing.write_bytes(b"")
        config.add_recent_file(str(existing))
        assert str(existing) in config.get_recent_files()

    def test_add_duplicate_moves_to_front(self, config: AppConfig, tmp_path: Path) -> None:
        f1 = tmp_path / "a.xlsx"
        f2 = tmp_path / "b.xlsx"
        f1.write_bytes(b"")
        f2.write_bytes(b"")
        config.add_recent_file(str(f1))
        config.add_recent_file(str(f2))
        config.add_recent_file(str(f1))
        assert config.recent_files[0] == str(f1)

    def test_truncates_to_max(self, config: AppConfig, tmp_path: Path) -> None:
        config.max_recent_files = 3
        for i in range(5):
            f = tmp_path / f"f{i}.xlsx"
            f.write_bytes(b"")
            config.add_recent_file(str(f))
        assert len(config.recent_files) == 3


class TestReset:
    def test_reset_restores_defaults(self, config: AppConfig) -> None:
        config.comparison.ignore_case = True
        config.log_level = "DEBUG"
        config.reset_to_defaults()
        assert config.comparison.ignore_case is False
        assert config.log_level == "INFO"
