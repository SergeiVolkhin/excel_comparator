"""Characterization tests for ExcelFileLoader and CSVFileLoader."""

from __future__ import annotations

from pathlib import Path
from typing import Any

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


# ---------------------------------------------------------------------------
# CSV loader — characterization tests (pin current behaviour for refactors)
# ---------------------------------------------------------------------------


class TestCSVLoaderEncodingDetection:
    def test_load_windows_1251_cyrillic(self, csv_loader: CSVFileLoader, tmp_path: Path) -> None:
        # Confident chardet result for a cp1251 cyrillic payload.
        f = tmp_path / "ru.csv"
        f.write_bytes("имя,балл\nАлиса,10\nБорис,20\n".encode("cp1251"))
        df = csv_loader.load(f)
        assert list(df.columns) == ["имя", "балл"]
        assert df.iloc[0, 0] == "Алиса"

    def test_load_utf8_with_bom_strips_bom_from_header(
        self, csv_loader: CSVFileLoader, tmp_path: Path
    ) -> None:
        f = tmp_path / "bom.csv"
        f.write_bytes(b"\xef\xbb\xbfid,name\n1,Alice\n")
        df = csv_loader.load(f)
        # Pandas strips the BOM from the header; pin this contract.
        assert list(df.columns) == ["id", "name"]
        assert "\ufeff" not in "".join(df.columns)

    def test_low_confidence_encoding_falls_back_to_utf8(
        self, csv_loader: CSVFileLoader, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Force chardet to report low confidence → loader falls back to UTF-8.
        import src.loaders.csv_loader as csv_mod

        def fake_detect(_data: bytes) -> dict[str, Any]:
            return {"encoding": "ISO-8859-7", "confidence": 0.1}

        monkeypatch.setattr(csv_mod.chardet, "detect", fake_detect)
        f = tmp_path / "low.csv"
        f.write_text("id,name\n1,A\n", encoding="utf-8")
        df = csv_loader.load(f)
        assert list(df.columns) == ["id", "name"]

    def test_detect_encoding_exception_falls_back_to_utf8(
        self, csv_loader: CSVFileLoader, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Force the open() inside _detect_encoding to explode, proving the
        # wrapper's except-clause returns "utf-8" without propagating.
        import src.loaders.csv_loader as csv_mod

        target = tmp_path / "boom.csv"
        target.write_text("id,name\n1,A\n", encoding="utf-8")

        def flaky_open(*_args: Any, **_kwargs: Any) -> Any:
            raise OSError("simulated I/O failure during encoding detect")

        # Injecting "open" as a module attribute shadows the builtin for code
        # inside csv_mod without affecting the rest of the test process.
        monkeypatch.setattr(csv_mod, "open", flaky_open, raising=False)
        assert csv_loader._detect_encoding(target) == "utf-8"


class TestCSVLoaderDelimiterDetection:
    def test_auto_detect_semicolon(self, csv_loader: CSVFileLoader, tmp_path: Path) -> None:
        f = tmp_path / "semi.csv"
        f.write_text("id;name;score\n1;Alice;10\n2;Bob;20\n", encoding="utf-8")
        df = csv_loader.load(f)
        assert list(df.columns) == ["id", "name", "score"]
        assert len(df) == 2

    def test_auto_detect_pipe(self, csv_loader: CSVFileLoader, tmp_path: Path) -> None:
        f = tmp_path / "pipe.csv"
        f.write_text("id|name|score\n1|Alice|10\n2|Bob|20\n", encoding="utf-8")
        df = csv_loader.load(f)
        assert list(df.columns) == ["id", "name", "score"]
        assert len(df) == 2

    def test_auto_detect_tab_on_csv_extension(
        self, csv_loader: CSVFileLoader, tmp_path: Path
    ) -> None:
        f = tmp_path / "tabs.csv"
        f.write_text("id\tname\tscore\n1\tAlice\t10\n2\tBob\t20\n", encoding="utf-8")
        df = csv_loader.load(f)
        assert list(df.columns) == ["id", "name", "score"]
        assert len(df) == 2

    def test_tsv_extension_short_circuits_to_tab(
        self, csv_loader: CSVFileLoader, tmp_path: Path
    ) -> None:
        # .tsv returns a real tab from _detect_separator (post-B.1); pandas
        # splits on it literally.
        f = tmp_path / "a.tsv"
        f.write_text("id\tname\n1\tA\n", encoding="utf-8")
        df = csv_loader.load(f)
        assert list(df.columns) == ["id", "name"]

    def test_detect_separator_exception_returns_comma(
        self, csv_loader: CSVFileLoader, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom(*_args: Any, **_kwargs: Any) -> list[str]:
            raise RuntimeError("scanner bug")

        monkeypatch.setattr(csv_loader, "_read_sample_lines", boom)
        f = tmp_path / "a.csv"
        f.write_text("id,name\n1,A\n", encoding="utf-8")
        # Returns "," (the docstring contract); load still succeeds.
        assert csv_loader._detect_separator(f, "utf-8") == ","

    def test_single_column_file_falls_back_to_comma(
        self, csv_loader: CSVFileLoader, tmp_path: Path
    ) -> None:
        # Every candidate sees avg == 1; _pick_best_separator skips all and
        # returns the hard-coded "," default.
        f = tmp_path / "single.csv"
        f.write_text("solo\nfoo\nbar\n", encoding="utf-8")
        df = csv_loader.load(f)
        assert list(df.columns) == ["solo"]
        assert len(df) == 2


class TestCSVLoaderInternalScoring:
    """Direct unit tests on the scoring helpers — the only way to reach the
    all-blank-lines branch (line 133) without triggering pandas' EmptyDataError
    first through the public load() path.
    """

    def test_score_separators_blank_lines_returns_empty(self) -> None:
        assert CSVFileLoader._score_separators(["", "", ""]) == {}

    def test_score_separators_scores_each_candidate(self) -> None:
        scores = CSVFileLoader._score_separators(["a,b,c", "1,2,3"])
        assert "," in scores
        avg, consistency = scores[","]
        assert avg == 3.0
        assert consistency == 1.0

    def test_pick_best_separator_empty_scores_defaults_to_comma(self) -> None:
        assert CSVFileLoader._pick_best_separator({}) == ","

    def test_pick_best_separator_ignores_avg_le_one(self) -> None:
        # Every candidate has avg <= 1 → "no usable separator" → "," fallback.
        assert CSVFileLoader._pick_best_separator({",": (1.0, 1.0), ";": (1.0, 1.0)}) == ","

    def test_pick_best_separator_picks_highest_value(self) -> None:
        # avg * consistency: "," → 4.0, ";" → 2.0 → "," wins; also exercises
        # the "not better than current best" loop branch for the second entry.
        assert CSVFileLoader._pick_best_separator({",": (4.0, 1.0), ";": (2.0, 1.0)}) == ","


class TestCSVLoaderErrorPaths:
    def test_empty_file_raises_file_load_error(
        self, csv_loader: CSVFileLoader, tmp_path: Path
    ) -> None:
        f = tmp_path / "empty.csv"
        f.write_bytes(b"")
        with pytest.raises(FileLoadError, match="не содержит данных"):
            csv_loader.load(f)

    def test_header_only_file_raises_file_load_error(
        self, csv_loader: CSVFileLoader, tmp_path: Path
    ) -> None:
        f = tmp_path / "headonly.csv"
        f.write_text("id,name\n", encoding="utf-8")
        with pytest.raises(FileLoadError, match=r"пустой|не содержит"):
            csv_loader.load(f)

    def test_unicode_decode_error_wrapped(
        self, csv_loader: CSVFileLoader, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Trick the loader into using the wrong encoding so pd.read_csv raises
        # UnicodeDecodeError from within the engine.
        monkeypatch.setattr(csv_loader, "_detect_encoding", lambda _p: "ascii")
        f = tmp_path / "cyr.csv"
        f.write_bytes("имя,балл\nАлиса,10\n".encode("cp1251"))
        with pytest.raises(FileLoadError, match="Ошибка кодировки"):
            csv_loader.load(f)

    def test_parser_error_wrapped(
        self, csv_loader: CSVFileLoader, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import src.loaders.csv_loader as csv_mod

        def raise_parser(*_args: Any, **_kwargs: Any) -> pd.DataFrame:
            raise pd.errors.ParserError("simulated bad CSV")

        monkeypatch.setattr(csv_mod.pd, "read_csv", raise_parser)
        f = tmp_path / "bad.csv"
        f.write_text("id,name\n1,A\n", encoding="utf-8")
        with pytest.raises(FileLoadError, match="парсинга CSV"):
            csv_loader.load(f)

    def test_generic_exception_wrapped(
        self, csv_loader: CSVFileLoader, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import src.loaders.csv_loader as csv_mod

        def raise_os(*_args: Any, **_kwargs: Any) -> pd.DataFrame:
            raise OSError("disk melted")

        monkeypatch.setattr(csv_mod.pd, "read_csv", raise_os)
        f = tmp_path / "a.csv"
        f.write_text("id,name\n1,A\n", encoding="utf-8")
        with pytest.raises(FileLoadError, match="disk melted"):
            csv_loader.load(f)

    def test_preview_data_exception_returns_empty_df(
        self, csv_loader: CSVFileLoader, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom(*_args: Any, **_kwargs: Any) -> str:
            raise RuntimeError("detect failed")

        monkeypatch.setattr(csv_loader, "_detect_encoding", boom)
        f = tmp_path / "a.csv"
        f.write_text("id,name\n1,A\n", encoding="utf-8")
        df = csv_loader.preview_data(f)
        assert df.empty

    def test_analyze_file_structure_exception_returns_empty_dict(
        self, csv_loader: CSVFileLoader, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom(*_args: Any, **_kwargs: Any) -> str:
            raise RuntimeError("detect failed")

        monkeypatch.setattr(csv_loader, "_detect_encoding", boom)
        f = tmp_path / "a.csv"
        f.write_text("id,name\n1,A\n", encoding="utf-8")
        assert csv_loader.analyze_file_structure(f) == {}


class TestCSVLoaderParamPassthrough:
    def test_header_none_assigns_integer_columns(
        self, csv_loader: CSVFileLoader, tmp_path: Path
    ) -> None:
        f = tmp_path / "noheader.csv"
        f.write_text("1,Alice\n2,Bob\n", encoding="utf-8")
        df = csv_loader.load(f, header=None)
        # Pandas labels columns 0, 1 when header=None.
        assert list(df.columns) == [0, 1]
        assert len(df) == 2

    def test_skiprows_drops_leading_rows(self, csv_loader: CSVFileLoader, tmp_path: Path) -> None:
        f = tmp_path / "skip.csv"
        f.write_text("junk line\nmore junk\nid,name\n1,A\n2,B\n", encoding="utf-8")
        df = csv_loader.load(f, skiprows=2)
        assert list(df.columns) == ["id", "name"]
        assert len(df) == 2

    def test_nrows_limits_rows(self, csv_loader: CSVFileLoader, tmp_path: Path) -> None:
        f = tmp_path / "big.csv"
        f.write_text("id,name\n1,A\n2,B\n3,C\n", encoding="utf-8")
        df = csv_loader.load(f, nrows=1)
        assert len(df) == 1

    def test_comment_lines_skipped(self, csv_loader: CSVFileLoader, tmp_path: Path) -> None:
        f = tmp_path / "commented.csv"
        f.write_text("id,name\n# this is a comment\n1,A\n2,B\n", encoding="utf-8")
        df = csv_loader.load(f, comment="#")
        assert len(df) == 2

    def test_disallowed_kwarg_silently_dropped(
        self, csv_loader: CSVFileLoader, tmp_path: Path
    ) -> None:
        # `engine` is not in allowed_params; the loader fixes it to "python"
        # and never forwards user-supplied engines. Pin this contract: a user
        # asking for engine="c" should not crash and not change the parser.
        f = tmp_path / "a.csv"
        f.write_text("id,name\n1,A\n", encoding="utf-8")
        df = csv_loader.load(f, engine="c")
        assert list(df.columns) == ["id", "name"]
        assert len(df) == 1


class TestCSVLoaderChunkedPath:
    """The chunked path activates above ``_CHUNK_THRESHOLD_BYTES``. We
    exercise it two ways: monkeypatching the threshold to nearly-zero so
    any small file triggers it (fast, always runs), and generating a real
    ~120 MB file (slow, opt-in via ``-m slow``)."""

    def test_chunked_path_taken_with_lowered_threshold(
        self, csv_loader: CSVFileLoader, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(CSVFileLoader, "_CHUNK_THRESHOLD_BYTES", 1)
        f = tmp_path / "tiny.csv"
        f.write_text("id,name\n1,Alice\n2,Bob\n3,Charlie\n", encoding="utf-8")
        df = csv_loader.load(f, chunk_size=2)
        # 3 rows, read as one chunk of 2 + one chunk of 1, concat'd back.
        assert list(df.columns) == ["id", "name"]
        assert len(df) == 3
        assert df.iloc[2]["name"] == "Charlie"

    def test_chunk_size_kwarg_not_forwarded_to_pandas(
        self, csv_loader: CSVFileLoader, tmp_path: Path
    ) -> None:
        # Without the fix the default path would forward chunk_size to
        # pd.read_csv which would return an iterator, breaking the shape
        # assertion. Pins that load() consumes chunk_size and pandas sees
        # no unknown kwargs.
        f = tmp_path / "small.csv"
        f.write_text("id,name\n1,A\n2,B\n", encoding="utf-8")
        df = csv_loader.load(f, chunk_size=10)  # below threshold, ignored
        assert len(df) == 2

    @pytest.mark.slow
    def test_chunked_path_on_120mb_file(self, csv_loader: CSVFileLoader, tmp_path: Path) -> None:
        import pandas as pd

        # Row layout: id (1-7 chars) + "," + "payload-NNNNNNNN-" (17 chars)
        # + 72-byte filler + "\n" -> ~97 bytes/row. 1.5M rows -> ~138 MB,
        # comfortably over the 100 MB chunk-threshold.
        n_rows = 1_500_000
        filler = "x" * 72
        src = pd.DataFrame(
            {
                "id": range(n_rows),
                "value": [f"payload-{i:08d}-{filler}" for i in range(n_rows)],
            }
        )
        f = tmp_path / "big.csv"
        src.to_csv(f, index=False)
        assert f.stat().st_size > 100 * 1024 * 1024

        df = csv_loader.load(f)
        assert len(df) == n_rows
        assert df.iloc[n_rows // 2]["id"] == n_rows // 2


class TestCSVLoaderOnBadLines:
    @pytest.fixture
    def bad_csv(self, tmp_path: Path) -> Path:
        p = tmp_path / "bad.csv"
        p.write_text("a,b,c\n1,2,3\n4,5,6,7,8\n9,10,11\n", encoding="utf-8")
        return p

    def test_default_raises_with_line_number_and_hint(self, bad_csv: Path) -> None:
        loader = CSVFileLoader()
        with pytest.raises(FileLoadError) as exc:
            loader.load(bad_csv)
        msg = str(exc.value)
        assert "line 3" in msg
        assert "--csv-on-bad-lines skip" in msg

    def test_skip_returns_clean_dataframe(self, bad_csv: Path) -> None:
        loader = CSVFileLoader()
        df = loader.load(bad_csv, on_bad_lines="skip")
        assert df.shape == (2, 3)
        assert df["a"].tolist() == [1, 9]

    def test_warn_mode_emits_parser_warning(self, bad_csv: Path) -> None:
        # Suite runs under filterwarnings=error; pytest.warns catches the
        # ParserWarning explicitly so 'warn' can still be covered here.
        loader = CSVFileLoader()
        with pytest.warns(pd.errors.ParserWarning):
            df = loader.load(bad_csv, on_bad_lines="warn")
        assert df.shape == (2, 3)
