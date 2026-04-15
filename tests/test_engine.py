"""End-to-end characterization tests for ComparisonEngine."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.core.engine import ComparisonEngine, StandardComparisonStrategy
from src.core.exceptions import ApplicationError, UnsupportedFormatError
from src.core.interfaces import ComparisonResult


@pytest.fixture
def engine() -> ComparisonEngine:
    return ComparisonEngine()


class TestRegistries:
    def test_default_comparators(self, engine: ComparisonEngine) -> None:
        assert set(engine.get_available_comparators()) == {"basic", "advanced"}

    def test_default_formatters(self, engine: ComparisonEngine) -> None:
        assert set(engine.get_available_formatters()) == {"excel", "html"}

    def test_supported_extensions(self, engine: ComparisonEngine) -> None:
        exts = set(engine.get_supported_file_extensions())
        assert {".xlsx", ".xls"}.issubset(exts)


class TestDetermineFormatter:
    @pytest.mark.parametrize(
        ("suffix", "expected"),
        [(".xlsx", "excel"), (".xls", "excel"), (".html", "html"), (".htm", "html"), (".bin", "excel")],
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
