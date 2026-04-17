"""CLI characterization tests.

Covers argument parsing and end-to-end CSV-centric invocations of
``run_cli_mode`` against generated files. The existing argparse-based
CLI is kept; new flags added in B.8 are verified here.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

import main as cli_main


@pytest.fixture
def patch_argv(monkeypatch: pytest.MonkeyPatch) -> Any:
    def _apply(argv: list[str]) -> None:
        monkeypatch.setattr(sys, "argv", ["main.py", *argv])

    return _apply


class TestArgumentParsing:
    def test_defaults_for_new_flags(self, patch_argv: Any) -> None:
        patch_argv(["--cli", "--file1", "a", "--file2", "b", "--output", "c.xlsx"])
        args = cli_main.parse_arguments()
        assert args.format is None
        assert args.csv_encoding is None
        assert args.csv_delimiter is None
        assert args.csv_skip_rows is None
        assert args.chunk_size is None
        assert args.csv_on_bad_lines is None

    def test_format_choice_accepted(self, patch_argv: Any) -> None:
        patch_argv(
            [
                "--cli",
                "--file1",
                "a",
                "--file2",
                "b",
                "--output",
                "c.csv",
                "--format",
                "csv",
            ]
        )
        assert cli_main.parse_arguments().format == "csv"

    def test_format_invalid_choice_rejected(self, patch_argv: Any) -> None:
        patch_argv(["--cli", "--format", "pdf"])
        with pytest.raises(SystemExit):
            cli_main.parse_arguments()

    def test_csv_flag_passthrough(self, patch_argv: Any) -> None:
        patch_argv(
            [
                "--cli",
                "--file1",
                "a",
                "--file2",
                "b",
                "--output",
                "c.csv",
                "--csv-encoding",
                "cp1251",
                "--csv-delimiter",
                ";",
                "--csv-skip-rows",
                "3",
                "--chunk-size",
                "10000",
                "--csv-on-bad-lines",
                "skip",
            ]
        )
        args = cli_main.parse_arguments()
        assert args.csv_encoding == "cp1251"
        assert args.csv_delimiter == ";"
        assert args.csv_skip_rows == 3
        assert args.chunk_size == 10000
        assert args.csv_on_bad_lines == "skip"


class TestRunCLIMode:
    """End-to-end: small CSV pair → CSV report via run_cli_mode."""

    def _make_args(self, **overrides: Any) -> Any:
        from argparse import Namespace

        defaults = dict(
            gui=False,
            cli=True,
            file1=None,
            file2=None,
            output=None,
            ignore_case=False,
            ignore_whitespace=False,
            format=None,
            csv_encoding=None,
            csv_delimiter=None,
            csv_skip_rows=None,
            chunk_size=None,
            csv_on_bad_lines=None,
            log_level="INFO",
        )
        defaults.update(overrides)
        return Namespace(**defaults)

    def test_csv_input_csv_output(self, tmp_path: Path) -> None:
        df = pd.DataFrame({"id": [1, 2, 3], "name": ["A", "B", "C"]})
        a = tmp_path / "a.csv"
        b = tmp_path / "b.csv"
        df.to_csv(a, index=False)
        df.to_csv(b, index=False)
        out = tmp_path / "r.csv"

        cli_main.run_cli_mode(self._make_args(file1=str(a), file2=str(b), output=str(out)))
        assert out.exists()
        # The __status__ column is CSVOutputFormatter's contract.
        header = out.read_text(encoding="utf-8").splitlines()[0]
        assert "__status__" in header

    def test_csv_input_xlsx_output_with_format_override(self, tmp_path: Path) -> None:
        df = pd.DataFrame({"id": [1, 2], "name": ["A", "B"]})
        a = tmp_path / "a.csv"
        b = tmp_path / "b.csv"
        df.to_csv(a, index=False)
        df.to_csv(b, index=False)
        # Output path is .report (unknown suffix); --format xlsx forces excel.
        out = tmp_path / "r.report"

        cli_main.run_cli_mode(
            self._make_args(
                file1=str(a),
                file2=str(b),
                output=str(out),
                format="xlsx",
            )
        )
        assert out.exists()
        # Raw xlsx signature — zip PK header.
        assert out.read_bytes()[:2] == b"PK"

    def test_csv_delimiter_override(self, tmp_path: Path) -> None:
        df = pd.DataFrame({"id": [1, 2], "name": ["A", "B"]})
        a = tmp_path / "a.csv"
        b = tmp_path / "b.csv"
        df.to_csv(a, sep=";", index=False)
        df.to_csv(b, sep=";", index=False)
        out = tmp_path / "r.csv"

        cli_main.run_cli_mode(
            self._make_args(
                file1=str(a),
                file2=str(b),
                output=str(out),
                csv_delimiter=";",
            )
        )
        assert out.exists()

    def test_missing_files_exit_code(self, tmp_path: Path) -> None:
        with pytest.raises(SystemExit) as exc:
            cli_main.run_cli_mode(
                self._make_args(
                    file1=str(tmp_path / "nope.csv"),
                    file2=str(tmp_path / "also-missing.csv"),
                    output=str(tmp_path / "r.csv"),
                )
            )
        assert exc.value.code == 1
