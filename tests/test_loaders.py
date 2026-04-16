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

    def test_get_sheet_names_bad_file_returns_empty(
        self, excel_loader: ExcelFileLoader, tmp_path: Path
    ) -> None:
        bad = tmp_path / "bad.xlsx"
        bad.write_bytes(b"not-an-xlsx")
        assert excel_loader.get_sheet_names(bad) == []

    def test_preview_bad_file_returns_empty_df(
        self, excel_loader: ExcelFileLoader, tmp_path: Path
    ) -> None:
        bad = tmp_path / "bad.xlsx"
        bad.write_bytes(b"not-an-xlsx")
        df = excel_loader.preview_data(bad)
        assert df.empty

    def test_load_empty_xlsx_raises(self, excel_loader: ExcelFileLoader, tmp_path: Path) -> None:
        # Produce an xlsx with zero data rows
        import pandas as pd

        empty = pd.DataFrame({"a": []})
        p = tmp_path / "empty.xlsx"
        with pd.ExcelWriter(p, engine="openpyxl") as w:
            empty.to_excel(w, index=False)
        with pytest.raises(FileLoadError):
            excel_loader.load(p)


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

    def test_bad_extension_raises(self, csv_loader: CSVFileLoader, tmp_path: Path) -> None:
        f = tmp_path / "a.xlsx"
        f.write_bytes(b"")
        with pytest.raises(FileLoadError, match="расширение"):
            csv_loader.load(f)

    def test_load_semicolon_separator(self, csv_loader: CSVFileLoader, tmp_path: Path) -> None:
        f = tmp_path / "a.csv"
        f.write_text("id;name\n1;Alice\n2;Bob\n", encoding="utf-8")
        df = csv_loader.load(f, sep=";")
        assert list(df.columns) == ["id", "name"]
        assert len(df) == 2

    def test_load_tsv(self, csv_loader: CSVFileLoader, tmp_path: Path) -> None:
        f = tmp_path / "a.tsv"
        f.write_text("id\tname\n1\tAlice\n2\tBob\n", encoding="utf-8")
        df = csv_loader.load(f)
        assert len(df) == 2

    def test_load_explicit_separator(self, csv_loader: CSVFileLoader, tmp_path: Path) -> None:
        f = tmp_path / "a.csv"
        f.write_text("id|name\n1|Alice\n", encoding="utf-8")
        df = csv_loader.load(f, sep="|")
        assert len(df) == 1

    def test_analyze_file_structure(self, csv_loader: CSVFileLoader, tmp_path: Path) -> None:
        f = tmp_path / "a.csv"
        f.write_text("id,name\n1,A\n2,B\n", encoding="utf-8")
        analysis = csv_loader.analyze_file_structure(f)
        assert analysis["columns"] == 2
        assert analysis["total_rows"] == 2
        assert "encoding" in analysis

    def test_preview(self, csv_loader: CSVFileLoader, tmp_path: Path) -> None:
        f = tmp_path / "a.csv"
        f.write_text("id,name\n1,A\n2,B\n3,C\n", encoding="utf-8")
        df = csv_loader.preview_data(f, max_rows=2)
        assert len(df) == 2

    def test_supported_extensions(self, csv_loader: CSVFileLoader) -> None:
        assert set(csv_loader.get_supported_extensions()) == {".csv", ".txt", ".tsv"}


class TestExcelLoaderPreview:
    def test_preview(
        self, excel_loader: ExcelFileLoader, identical_xlsx_pair: tuple[Path, Path]
    ) -> None:
        a, _ = identical_xlsx_pair
        df = excel_loader.preview_data(a, max_rows=2)
        assert len(df) == 2
