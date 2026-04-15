"""Characterization tests for ExcelFileLoader and CSVFileLoader."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.core.exceptions import FileLoadError
from src.loaders.csv_loader import CSVFileLoader
from src.loaders.excel_loader import ExcelFileLoader


# ---------------------------------------------------------------------------
# Excel loader
# ---------------------------------------------------------------------------


@pytest.fixture
def excel_loader() -> ExcelFileLoader:
    return ExcelFileLoader()


class TestExcelLoaderCanLoad:
    @pytest.mark.parametrize(
        ("name", "expected"),
        [("a.xlsx", True), ("a.xls", True), ("A.XLSX", True), ("a.csv", False), ("a.txt", False)],
    )
    def test_can_load(self, excel_loader: ExcelFileLoader, name: str, expected: bool) -> None:
        assert excel_loader.can_load(Path(name)) is expected

    def test_supported_extensions(self, excel_loader: ExcelFileLoader) -> None:
        assert excel_loader.get_supported_extensions() == [".xlsx", ".xls"]


class TestExcelLoaderLoad:
    def test_load_default_sheet(
        self, excel_loader: ExcelFileLoader, identical_xlsx_pair: tuple[Path, Path]
    ) -> None:
        a, _ = identical_xlsx_pair
        df = excel_loader.load(a)
        assert isinstance(df, pd.DataFrame)
        assert list(df.columns) == ["id", "name", "score"]
        assert len(df) == 4

    def test_load_named_sheet(
        self, excel_loader: ExcelFileLoader, multi_sheet_xlsx_pair: tuple[Path, Path]
    ) -> None:
        a, _ = multi_sheet_xlsx_pair
        df = excel_loader.load(a, sheet_name="Extra")
        assert len(df) == 2

    def test_missing_file_raises(self, excel_loader: ExcelFileLoader, tmp_path: Path) -> None:
        with pytest.raises(FileLoadError, match="не существует"):
            excel_loader.load(tmp_path / "nope.xlsx")

    def test_bad_extension_raises(self, excel_loader: ExcelFileLoader, tmp_path: Path) -> None:
        f = tmp_path / "a.csv"
        f.write_text("a,b\n1,2\n")
        with pytest.raises(FileLoadError, match="расширение"):
            excel_loader.load(f)

    def test_get_sheet_names(
        self, excel_loader: ExcelFileLoader, multi_sheet_xlsx_pair: tuple[Path, Path]
    ) -> None:
        a, _ = multi_sheet_xlsx_pair
        sheets = excel_loader.get_sheet_names(a)
        assert set(sheets) == {"Main", "Extra"}


# ---------------------------------------------------------------------------
# CSV loader
# ---------------------------------------------------------------------------


@pytest.fixture
def csv_loader() -> CSVFileLoader:
    return CSVFileLoader()


class TestCSVLoader:
    def test_can_load(self, csv_loader: CSVFileLoader) -> None:
        assert csv_loader.can_load(Path("a.csv"))
        assert csv_loader.can_load(Path("a.tsv"))
        assert csv_loader.can_load(Path("a.txt"))
        assert not csv_loader.can_load(Path("a.xlsx"))

    def test_load_basic_csv(self, csv_loader: CSVFileLoader, tmp_path: Path) -> None:
        f = tmp_path / "a.csv"
        f.write_text("id,name\n1,Alice\n2,Bob\n", encoding="utf-8")
        df = csv_loader.load(f)
        assert list(df.columns) == ["id", "name"]
        assert len(df) == 2

    def test_missing_file_raises(self, csv_loader: CSVFileLoader, tmp_path: Path) -> None:
        with pytest.raises(FileLoadError):
            csv_loader.load(tmp_path / "nope.csv")
