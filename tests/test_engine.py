"""End-to-end characterization tests for ComparisonEngine."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import pytest

from src.core.engine import ComparisonEngine, StandardComparisonStrategy
from src.core.exceptions import ApplicationError, UnsupportedFormatError
from src.core.interfaces import ComparisonResult

from .conftest import _write_csv


@pytest.fixture
def engine() -> ComparisonEngine:
    return ComparisonEngine()


class TestRegistries:
    def test_default_comparators(self, engine: ComparisonEngine) -> None:
        assert set(engine.get_available_comparators()) == {"basic", "advanced"}

    def test_default_formatters(self, engine: ComparisonEngine) -> None:
        assert set(engine.get_available_formatters()) == {"excel", "html", "csv"}

    def test_supported_extensions(self, engine: ComparisonEngine) -> None:
        exts = set(engine.get_supported_file_extensions())
        assert {".xlsx", ".xls", ".csv", ".txt", ".tsv"}.issubset(exts)


class TestDetermineFormatter:
    @pytest.mark.parametrize(
        ("suffix", "expected"),
        [
            (".xlsx", "excel"),
            (".xls", "excel"),
            (".html", "html"),
            (".htm", "html"),
            (".csv", "csv"),
            (".bin", "excel"),
        ],
    )
    def test_auto(self, engine: ComparisonEngine, suffix: str, expected: bool) -> None:
        assert engine._determine_formatter(Path(f"out{suffix}")) == expected


class TestCompareFilesE2E:
    def test_identical_pair_xlsx_output(
        self,
        engine: ComparisonEngine,
        identical_xlsx_pair: tuple[Path, Path],
        tmp_path: Path,
    ) -> None:
        a, b = identical_xlsx_pair
        out = tmp_path / "result.xlsx"
        result = engine.compare_files(a, b, out, comparator_name="basic")
        assert isinstance(result, ComparisonResult)
        assert out.exists()
        assert out.stat().st_size > 0
        assert result.metadata["different_cells"] == 0

    def test_value_diff_pair_html_output(
        self,
        engine: ComparisonEngine,
        value_diff_xlsx_pair: tuple[Path, Path],
        tmp_path: Path,
    ) -> None:
        a, b = value_diff_xlsx_pair
        out = tmp_path / "result.html"
        result = engine.compare_files(a, b, out, comparator_name="basic")
        assert out.exists()
        assert result.metadata["different_cells"] > 0

    def test_unknown_comparator_raises(
        self,
        engine: ComparisonEngine,
        identical_xlsx_pair: tuple[Path, Path],
        tmp_path: Path,
    ) -> None:
        a, b = identical_xlsx_pair
        with pytest.raises(ApplicationError, match="Компаратор"):
            engine.compare_files(a, b, tmp_path / "out.xlsx", comparator_name="missing")

    def test_unsupported_input_extension_raises(
        self, engine: ComparisonEngine, tmp_path: Path
    ) -> None:
        f = tmp_path / "a.bin"
        f.write_bytes(b"\x00")
        with pytest.raises(UnsupportedFormatError):
            engine.compare_files(f, f, tmp_path / "out.xlsx")


class TestStrategy:
    def test_strategy_executes(
        self,
        engine: ComparisonEngine,
        identical_xlsx_pair: tuple[Path, Path],
        tmp_path: Path,
    ) -> None:
        strategy = StandardComparisonStrategy(engine)
        a, b = identical_xlsx_pair
        result = strategy.execute(a, b, tmp_path / "out.xlsx")
        assert isinstance(result, ComparisonResult)


class TestLoadInfoSizeCheck:
    def test_row_count_mismatch_logged_and_in_metadata(
        self,
        engine: ComparisonEngine,
        csv_dir: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        a = _write_csv(csv_dir / "a.csv", pd.DataFrame({"id": [1, 2, 3], "v": [4, 5, 6]}))
        b = _write_csv(csv_dir / "b.csv", pd.DataFrame({"id": [1, 2], "v": [4, 5]}))
        with caplog.at_level(logging.INFO, logger="ComparisonEngine"):
            result = engine.compare_files(a, b, csv_dir / "out.xlsx", comparator_name="advanced")
        assert any("Разное число строк" in r.message for r in caplog.records)
        assert result.metadata["load_info"]["row_count_delta"] == 1

    def test_column_count_mismatch_logged_and_in_metadata(
        self,
        engine: ComparisonEngine,
        csv_dir: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        a = _write_csv(csv_dir / "a.csv", pd.DataFrame({"id": [1, 2], "v": [4, 5], "x": [7, 8]}))
        b = _write_csv(csv_dir / "b.csv", pd.DataFrame({"id": [1, 2], "v": [4, 5]}))
        with caplog.at_level(logging.WARNING, logger="ComparisonEngine"):
            result = engine.compare_files(a, b, csv_dir / "out.xlsx", comparator_name="advanced")
        assert any("Разное число столбцов" in r.message for r in caplog.records)
        assert result.metadata["load_info"]["column_count_mismatch"] == (3, 2)

    def test_identical_shapes_have_no_load_info(
        self,
        engine: ComparisonEngine,
        identical_csv_pair: tuple[Path, Path],
        tmp_path: Path,
    ) -> None:
        a, b = identical_csv_pair
        result = engine.compare_files(a, b, tmp_path / "out.xlsx", comparator_name="advanced")
        assert "load_info" not in result.metadata
