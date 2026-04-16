"""Integration tests for CSV support through the ComparisonEngine.

Pinned contracts:

* ``CSVFileLoader`` is not registered by default on HEAD — every test
  explicitly registers it so these tests survive the B.9 commit (which
  promotes it to a default) without needing changes.
* ``ComparisonResult.metadata["similarity_percentage"]`` is the primary
  signal asserted; ``differences_mask`` is checked directly for cell-level
  outcomes.
* Output format still lives on the xlsx/html path until B.5 lands; until
  then CSV inputs with ``.xlsx`` output are how we exercise the glue.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.core.engine import ComparisonEngine
from src.loaders.csv_loader import CSVFileLoader

from .conftest import _write_csv

# ---------------------------------------------------------------------------
# Engine fixture with CSV loader registered
# ---------------------------------------------------------------------------


@pytest.fixture
def engine_with_csv() -> ComparisonEngine:
    engine = ComparisonEngine()
    engine.register_file_loader(CSVFileLoader())
    return engine


def _base_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "id": [1, 2, 3],
            "name": ["Alice", "Bob", "Charlie"],
            "score": [10, 20, 30],
        }
    )


# ---------------------------------------------------------------------------
# A.2 — CSV ↔ CSV through the engine
# ---------------------------------------------------------------------------


class TestCSVvsCSV:
    def test_identical_comma_utf8(self, engine_with_csv: ComparisonEngine, csv_dir: Path) -> None:
        a = _write_csv(csv_dir / "a.csv", _base_df())
        b = _write_csv(csv_dir / "b.csv", _base_df())
        out = csv_dir / "report.xlsx"
        result = engine_with_csv.compare_files(a, b, out)
        assert result.metadata["similarity_percentage"] == 100.0
        assert result.differences_mask.values.sum() == 0
        assert out.exists()

    def test_identical_semicolon(self, engine_with_csv: ComparisonEngine, csv_dir: Path) -> None:
        a = _write_csv(csv_dir / "a.csv", _base_df(), sep=";")
        b = _write_csv(csv_dir / "b.csv", _base_df(), sep=";")
        result = engine_with_csv.compare_files(a, b, csv_dir / "r.xlsx")
        assert result.metadata["similarity_percentage"] == 100.0

    def test_identical_pipe(self, engine_with_csv: ComparisonEngine, csv_dir: Path) -> None:
        a = _write_csv(csv_dir / "a.csv", _base_df(), sep="|")
        b = _write_csv(csv_dir / "b.csv", _base_df(), sep="|")
        result = engine_with_csv.compare_files(a, b, csv_dir / "r.xlsx")
        assert result.metadata["similarity_percentage"] == 100.0

    def test_identical_tab_on_tsv_extension(
        self, engine_with_csv: ComparisonEngine, csv_dir: Path
    ) -> None:
        # .tsv path short-circuits in _detect_separator so the bug-B1 literal
        # "\\t" is interpreted as a tab by pandas (engine="python"). Pins that
        # .tsv mixed with other CSV-family extensions works end-to-end today.
        a = _write_csv(csv_dir / "a.tsv", _base_df(), sep="\t")
        b = _write_csv(csv_dir / "b.tsv", _base_df(), sep="\t")
        result = engine_with_csv.compare_files(a, b, csv_dir / "r.xlsx")
        assert result.metadata["similarity_percentage"] == 100.0

    def test_identical_tab_on_csv_extension(
        self, engine_with_csv: ComparisonEngine, csv_dir: Path
    ) -> None:
        a = _write_csv(csv_dir / "a.csv", _base_df(), sep="\t")
        b = _write_csv(csv_dir / "b.csv", _base_df(), sep="\t")
        result = engine_with_csv.compare_files(a, b, csv_dir / "r.xlsx")
        assert result.metadata["similarity_percentage"] == 100.0

    def test_value_diff_detected(self, engine_with_csv: ComparisonEngine, csv_dir: Path) -> None:
        df_a = _base_df()
        df_b = _base_df()
        df_b.loc[1, "name"] = "Robert"
        df_b.loc[2, "score"] = 99
        a = _write_csv(csv_dir / "a.csv", df_a)
        b = _write_csv(csv_dir / "b.csv", df_b)
        result = engine_with_csv.compare_files(a, b, csv_dir / "r.xlsx")
        assert result.metadata["different_cells"] == 2
        assert result.differences_mask.loc[1, "name"]
        assert result.differences_mask.loc[2, "score"]

    def test_encoding_mismatch_same_data_compares_equal(
        self, engine_with_csv: ComparisonEngine, csv_dir: Path
    ) -> None:
        # File1 UTF-8, file2 cp1251 — chardet detects each correctly, strings
        # are normalised on the way in, so the comparator sees the same data.
        a = _write_csv(csv_dir / "a.csv", _base_df(), encoding="utf-8")
        b = _write_csv(csv_dir / "b.csv", _base_df(), encoding="cp1251")
        result = engine_with_csv.compare_files(a, b, csv_dir / "r.xlsx")
        assert result.metadata["similarity_percentage"] == 100.0

    def test_nan_on_both_sides_counts_equal(
        self, engine_with_csv: ComparisonEngine, csv_dir: Path
    ) -> None:
        # Matches the xlsx NaN parity that _shared.build_differences_mask
        # guarantees (NaN vs NaN is NOT a difference).
        df = pd.DataFrame({"id": [1, 2, 3], "name": ["A", None, "C"]})
        a = _write_csv(csv_dir / "a.csv", df)
        b = _write_csv(csv_dir / "b.csv", df)
        result = engine_with_csv.compare_files(a, b, csv_dir / "r.xlsx")
        assert result.metadata["similarity_percentage"] == 100.0

    def test_ignore_case_option(self, engine_with_csv: ComparisonEngine, csv_dir: Path) -> None:
        df_a = pd.DataFrame({"id": [1], "name": ["Alice"]})
        df_b = pd.DataFrame({"id": [1], "name": ["ALICE"]})
        a = _write_csv(csv_dir / "a.csv", df_a)
        b = _write_csv(csv_dir / "b.csv", df_b)
        result = engine_with_csv.compare_files(
            a,
            b,
            csv_dir / "r.xlsx",
            comparison_options={"ignore_case": True},
        )
        assert result.metadata["similarity_percentage"] == 100.0

    def test_ignore_whitespace_option(
        self, engine_with_csv: ComparisonEngine, csv_dir: Path
    ) -> None:
        df_a = pd.DataFrame({"id": [1], "name": ["  Alice  "]})
        df_b = pd.DataFrame({"id": [1], "name": ["Alice"]})
        a = _write_csv(csv_dir / "a.csv", df_a)
        b = _write_csv(csv_dir / "b.csv", df_b)
        result = engine_with_csv.compare_files(
            a,
            b,
            csv_dir / "r.xlsx",
            comparison_options={"ignore_whitespace": True},
        )
        assert result.metadata["similarity_percentage"] == 100.0


# ---------------------------------------------------------------------------
# A.3 — CSV ↔ Excel (mixed formats)
# ---------------------------------------------------------------------------


class TestCSVxlsxMixedFormats:
    def test_identical_csv_vs_xlsx(
        self,
        engine_with_csv: ComparisonEngine,
        csv_dir: Path,
        xlsx_dir: Path,
    ) -> None:
        df = _base_df()
        csv_file = _write_csv(csv_dir / "a.csv", df)
        xlsx_file = xlsx_dir / "b.xlsx"
        with pd.ExcelWriter(xlsx_file, engine="openpyxl") as w:
            df.to_excel(w, sheet_name="Sheet1", index=False)
        result = engine_with_csv.compare_files(csv_file, xlsx_file, csv_dir / "r.xlsx")
        assert result.metadata["similarity_percentage"] == 100.0

    def test_identical_xlsx_vs_csv(
        self,
        engine_with_csv: ComparisonEngine,
        csv_dir: Path,
        xlsx_dir: Path,
    ) -> None:
        df = _base_df()
        xlsx_file = xlsx_dir / "a.xlsx"
        with pd.ExcelWriter(xlsx_file, engine="openpyxl") as w:
            df.to_excel(w, sheet_name="Sheet1", index=False)
        csv_file = _write_csv(csv_dir / "b.csv", df)
        result = engine_with_csv.compare_files(xlsx_file, csv_file, csv_dir / "r.xlsx")
        assert result.metadata["similarity_percentage"] == 100.0

    def test_value_diff_csv_vs_xlsx_mask_matches_one_cell(
        self,
        engine_with_csv: ComparisonEngine,
        csv_dir: Path,
        xlsx_dir: Path,
    ) -> None:
        df_a = _base_df()
        df_b = _base_df()
        df_b.loc[0, "score"] = 999
        csv_file = _write_csv(csv_dir / "a.csv", df_a)
        xlsx_file = xlsx_dir / "b.xlsx"
        with pd.ExcelWriter(xlsx_file, engine="openpyxl") as w:
            df_b.to_excel(w, sheet_name="Sheet1", index=False)
        result = engine_with_csv.compare_files(csv_file, xlsx_file, csv_dir / "r.xlsx")
        assert result.metadata["different_cells"] == 1
        assert result.differences_mask.loc[0, "score"]

    def test_mixed_formats_output_html(
        self,
        engine_with_csv: ComparisonEngine,
        csv_dir: Path,
        xlsx_dir: Path,
    ) -> None:
        df = _base_df()
        csv_file = _write_csv(csv_dir / "a.csv", df)
        xlsx_file = xlsx_dir / "b.xlsx"
        with pd.ExcelWriter(xlsx_file, engine="openpyxl") as w:
            df.to_excel(w, sheet_name="Sheet1", index=False)
        out = csv_dir / "report.html"
        engine_with_csv.compare_files(csv_file, xlsx_file, out)
        assert out.exists()
