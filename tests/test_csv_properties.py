"""Property-based tests for CSV loading.

Writer roundtrip tests are skipped until the CSV formatter lands in B.5.
The auto-detect invariance property runs against HEAD and pins current
behaviour.
"""

from __future__ import annotations

import string
from pathlib import Path

import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from src.loaders.csv_loader import CSVFileLoader

# The delimiter set agreed for v0.2.0. ``\t`` is excluded on the public
# .csv extension until B.1 fixes the literal-backslash bug (its test is
# xfailed in the integration suite).
_DELIMITERS_FOR_CSV = [",", ";", "|"]


def _safe_text() -> st.SearchStrategy[str]:
    """Ascii text without newlines or any of the candidate delimiters so
    the writer/reader round-trip is not confused by collisions in the
    generated payload."""
    alphabet = [c for c in string.ascii_letters + string.digits if c not in {" "}]
    return st.text(alphabet=alphabet, min_size=1, max_size=10)


@given(
    delimiter=st.sampled_from(_DELIMITERS_FOR_CSV),
    rows=st.lists(
        st.tuples(st.integers(min_value=-1000, max_value=1000), _safe_text()),
        min_size=1,
        max_size=10,
    ),
)
@settings(
    max_examples=30,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_delimiter_auto_detect_round_trip(
    delimiter: str,
    rows: list[tuple[int, str]],
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Auto-detect must pick whichever delimiter was used to write the
    file, as long as the payload does not itself contain that character
    (guaranteed by ``_safe_text``)."""
    tmp = tmp_path_factory.mktemp("csv_prop")
    df = pd.DataFrame(rows, columns=["id", "name"])
    f = tmp / "data.csv"
    df.to_csv(f, sep=delimiter, index=False, lineterminator="\n")

    # dtype=str disables pandas type inference (otherwise digit-only names
    # like "0" come back as int). keep_default_na=False prevents sentinels
    # such as "NaN"/"NULL"/"N/A" from being rewritten to NaN — hypothesis
    # readily generates them in the ascii_letters alphabet.
    loaded = CSVFileLoader().load(f, dtype=str, keep_default_na=False)
    assert list(loaded.columns) == ["id", "name"]
    assert len(loaded) == len(rows)
    assert loaded["name"].tolist() == [r[1] for r in rows]


@given(
    encoding=st.sampled_from(["utf-8", "cp1251", "cp1252"]),
    rows=st.lists(_safe_text(), min_size=1, max_size=5),
)
@settings(
    max_examples=20,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_encoding_round_trip_ascii_payload(
    encoding: str,
    rows: list[str],
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """ASCII payloads round-trip under any of the encodings chardet is
    likely to return. For cyrillic-only payloads the property is weaker
    (chardet can mis-detect) so we keep the alphabet ascii-only."""
    tmp = tmp_path_factory.mktemp("csv_enc")
    f = tmp / "data.csv"
    f.write_bytes(("v\n" + "\n".join(rows) + "\n").encode(encoding))

    # dtype=str prevents int coercion; keep_default_na=False stops pandas
    # from rewriting strings like "NaN"/"NULL" to actual NaN.
    loaded = CSVFileLoader().load(f, dtype=str, keep_default_na=False)
    assert loaded["v"].tolist() == rows


# ---------------------------------------------------------------------------
# Writer → loader roundtrip (CSVOutputFormatter → CSVFileLoader)
# ---------------------------------------------------------------------------


@given(
    delimiter=st.sampled_from(_DELIMITERS_FOR_CSV),
    rows=st.lists(
        st.tuples(st.integers(min_value=-1000, max_value=1000), _safe_text()),
        min_size=1,
        max_size=5,
    ),
)
@settings(
    max_examples=20,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_formatter_to_loader_roundtrip(
    delimiter: str,
    rows: list[tuple[int, str]],
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Write via the formatter, read back via the loader: names survive a
    roundtrip under every agreed delimiter. The ``__status__`` trailing
    column is present after the loader reads the file; we check the first
    two columns only."""
    from src.core.interfaces import ComparisonResult
    from src.formatters.csv_formatter import CSVOutputFormatter

    tmp = tmp_path_factory.mktemp("csv_rt")
    df = pd.DataFrame(rows, columns=["id", "name"])
    mask = pd.DataFrame({c: [False] * len(df) for c in df.columns})
    result = ComparisonResult(
        differences_mask=mask,
        file1_data=df,
        file2_data=df,
        metadata={
            "total_cells": df.size,
            "different_cells": 0,
            "similarity_percentage": 100.0,
            "shape": df.shape,
        },
    )
    out: Path = tmp / "out.csv"
    CSVOutputFormatter().format(result, out, delimiter=delimiter)
    reloaded = CSVFileLoader().load(out, dtype=str, keep_default_na=False)
    assert list(reloaded.columns) == ["id", "name", "__status__"]
    assert reloaded["name"].tolist() == [r[1] for r in rows]
