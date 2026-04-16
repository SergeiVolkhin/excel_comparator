"""Baseline performance benchmarks (pytest-benchmark).

Captures current throughput of the load→compare→format pipeline on
generated xlsx files. Run with:

    pytest tests/test_benchmarks.py --benchmark-only --benchmark-save=baseline

Re-run after refactor/perf changes and compare:

    pytest tests/test_benchmarks.py --benchmark-only --benchmark-compare=baseline
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from openpyxl import Workbook

from src.comparators.advanced_comparator import AdvancedComparator
from src.comparators.basic_comparator import BasicComparator
from src.core.engine import ComparisonEngine
from src.formatters.excel_formatter import ExcelOutputFormatter
from src.formatters.html_formatter import HTMLOutputFormatter
from src.loaders.csv_loader import CSVFileLoader
from src.loaders.excel_loader import ExcelFileLoader

pytestmark = pytest.mark.benchmark


def _write_xlsx(path: Path, n_rows: int, n_cols: int) -> Path:
    """Write a deterministic xlsx with n_rows × n_cols."""
    wb = Workbook(write_only=True)
    ws = wb.create_sheet("Sheet1")
    ws.append([f"c{i}" for i in range(n_cols)])
    for r in range(n_rows):
        ws.append([r * n_cols + c for c in range(n_cols)])
    wb.save(path)
    return path


@pytest.fixture(scope="module")
def medium_xlsx_pair(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    d = tmp_path_factory.mktemp("bench")
    a = _write_xlsx(d / "a.xlsx", n_rows=10_000, n_cols=5)
    b = _write_xlsx(d / "b.xlsx", n_rows=10_000, n_cols=5)
    return a, b


@pytest.fixture(scope="module")
def medium_df_pair() -> tuple[pd.DataFrame, pd.DataFrame]:
    df = pd.DataFrame({f"c{i}": range(10_000) for i in range(5)})
    df2 = df.copy()
    df2.loc[5000, "c0"] = -1
    return df, df2


class TestLoaderBenchmarks:
    def test_excel_load_10k_rows(self, benchmark, medium_xlsx_pair: tuple[Path, Path]) -> None:
        loader = ExcelFileLoader()
        a, _ = medium_xlsx_pair
        df = benchmark(loader.load, a)
        assert len(df) == 10_000

    def test_excel_load_10k_rows_readonly(
        self, benchmark, medium_xlsx_pair: tuple[Path, Path]
    ) -> None:
        loader = ExcelFileLoader()
        a, _ = medium_xlsx_pair
        df = benchmark(loader.load, a, read_only=True)
        assert len(df) == 10_000


class TestComparatorBenchmarks:
    def test_basic_compare_10k_rows(
        self, benchmark, medium_df_pair: tuple[pd.DataFrame, pd.DataFrame]
    ) -> None:
        df1, df2 = medium_df_pair
        comp = BasicComparator()
        result = benchmark(comp.compare, df1, df2)
        assert result.metadata["different_cells"] == 1

    def test_advanced_compare_10k_rows(
        self, benchmark, medium_df_pair: tuple[pd.DataFrame, pd.DataFrame]
    ) -> None:
        df1, df2 = medium_df_pair
        comp = AdvancedComparator()
        result = benchmark(comp.compare, df1, df2)
        assert result.metadata["different_cells"] == 1


class TestFormatterBenchmarks:
    def test_excel_format_10k_rows(
        self,
        benchmark,
        medium_df_pair: tuple[pd.DataFrame, pd.DataFrame],
        tmp_path: Path,
    ) -> None:
        df1, df2 = medium_df_pair
        result = BasicComparator().compare(df1, df2)
        formatter = ExcelOutputFormatter()
        benchmark(formatter.format, result, tmp_path / "out.xlsx")

    def test_html_format_10k_rows(
        self,
        benchmark,
        medium_df_pair: tuple[pd.DataFrame, pd.DataFrame],
        tmp_path: Path,
    ) -> None:
        df1, df2 = medium_df_pair
        result = BasicComparator().compare(df1, df2)
        formatter = HTMLOutputFormatter()
        benchmark(formatter.format, result, tmp_path / "out.html")


class TestPipelineBenchmark:
    def test_full_pipeline_10k_rows_xlsx(
        self,
        benchmark,
        medium_xlsx_pair: tuple[Path, Path],
        tmp_path: Path,
    ) -> None:
        a, b = medium_xlsx_pair
        engine = ComparisonEngine()
        out = tmp_path / "full.xlsx"
        benchmark(engine.compare_files, a, b, out, comparator_name="basic")


# ---------------------------------------------------------------------------
# CSV benchmarks — saved under 0002_csv_baseline, untouching 0001_baseline
# (the Excel regression reference used by the existing pre-commit policy).
# ---------------------------------------------------------------------------


def _write_csv_bench(path: Path, n_rows: int, n_cols: int) -> Path:
    df = pd.DataFrame({f"c{i}": range(n_rows) for i in range(n_cols)})
    df.to_csv(path, index=False)
    return path


@pytest.fixture(scope="module")
def small_csv_pair(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    d = tmp_path_factory.mktemp("csv_bench_small")
    a = _write_csv_bench(d / "a.csv", n_rows=10_000, n_cols=5)
    b = _write_csv_bench(d / "b.csv", n_rows=10_000, n_cols=5)
    return a, b


@pytest.fixture(scope="module")
def medium_csv_pair(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    d = tmp_path_factory.mktemp("csv_bench_medium")
    a = _write_csv_bench(d / "a.csv", n_rows=200_000, n_cols=10)
    b = _write_csv_bench(d / "b.csv", n_rows=200_000, n_cols=10)
    return a, b


class TestCSVBenchmarks:
    def test_csv_load_small_10k(self, benchmark, small_csv_pair: tuple[Path, Path]) -> None:
        loader = CSVFileLoader()
        a, _ = small_csv_pair
        df = benchmark(loader.load, a)
        assert len(df) == 10_000

    def test_csv_load_medium_200k(self, benchmark, medium_csv_pair: tuple[Path, Path]) -> None:
        loader = CSVFileLoader()
        a, _ = medium_csv_pair
        df = benchmark(loader.load, a)
        assert len(df) == 200_000

    def test_csv_compare_identical_200k(
        self,
        benchmark,
        medium_csv_pair: tuple[Path, Path],
        tmp_path: Path,
    ) -> None:
        a, b = medium_csv_pair
        engine = ComparisonEngine()
        engine.register_file_loader(CSVFileLoader())
        out = tmp_path / "csv_bench.xlsx"
        benchmark(engine.compare_files, a, b, out, comparator_name="basic")
