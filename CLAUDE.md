# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Modular Excel/CSV comparator (~4000 LOC, Python 3.11+). Two entry points:
`python main.py` (tkinter GUI by default) and `python main.py --cli ...`.
Produces either an xlsx report (with highlighted diffing cells + summary
sheet) or an html report (with pagination for large tables).

README.md and architecture.md are in Russian; design follows SOLID with
`ComparisonEngine` wiring three replaceable protocols.

## Environment

- `.venv/` is the project venv (Python 3.13). On Windows (bash/mingw)
  invoke the interpreter as `./.venv/Scripts/python.exe`. Do not rely on
  the PATH `python` — it resolves to the system interpreter.
- If `.venv` is missing or broken (it was historically pointing at a
  different user's profile), recreate with `py -3.13 -m venv .venv`
  and `./.venv/Scripts/python.exe -m pip install -r requirements-dev.txt`.

## Common commands

Run all unit tests (skip benchmarks):
```bash
./.venv/Scripts/python.exe -m pytest tests/ -q --ignore=tests/test_benchmarks.py
```

Single test:
```bash
./.venv/Scripts/python.exe -m pytest tests/test_engine.py::TestCompareFilesE2E::test_identical_pair_xlsx_output -q
```

Coverage (branch, the standard we hold at ≥85%):
```bash
./.venv/Scripts/python.exe -m pytest tests/ --cov=src --cov-branch --cov-report=term --ignore=tests/test_benchmarks.py
```

Lint / format / type-check (all must pass before committing):
```bash
./.venv/Scripts/python.exe -m ruff check src/ tests/
./.venv/Scripts/python.exe -m ruff format src/ tests/
./.venv/Scripts/python.exe -m mypy src/      # strict mode via pyproject.toml
```

Performance — compare against the stored baseline:
```bash
./.venv/Scripts/python.exe -m pytest tests/test_benchmarks.py --benchmark-only \
    --benchmark-compare=0001_baseline --benchmark-columns=min,mean,max
```
Baseline lives in `.benchmarks/Windows-CPython-3.13-64bit/0001_baseline.json`
(gitignored). After perf changes, re-save under a new name:
`--benchmark-save=<name>`. Treat a ≥10% regression on mean as a blocker.

## Architecture

`ComparisonEngine` (`src/core/engine.py`) is the single composition root.
It holds four registries and delegates through them:

```
IFileLoader  (src/loaders/*)       load(path) -> DataFrame
IComparator  (src/comparators/*)   compare(df1, df2, **opts) -> ComparisonResult
IOutputFormatter (src/formatters/*) format(result, path, **opts) -> None
IValidationRule (src/validators/*)  validate(df1, df2) -> list[str] of error messages
```

The engine registers defaults in `_register_default_components`:
`ExcelFileLoader`, `CSVFileLoader`, `Basic`/`AdvancedComparator`,
`Excel`/`HTML`/`CSVOutputFormatter`. `_determine_formatter` auto-selects
by output suffix (`.xlsx`/`.xls` → excel, `.html`/`.htm` → html,
`.csv` → csv, other → excel).

Validation rules are **empty by default**
(`ValidationRuleFactory.for_csv()` / `.create_standard_validators()` /
`.create_lenient_validators()` / `.create_strict_validators()` return
sets, but nothing wires them in; the comparators do their own
size/shape validation).

`ComparisonResult` (dataclass in `src/core/interfaces.py`) is the
currency between layers: `differences_mask: DataFrame[bool]`,
`file1_data`, `file2_data`, `metadata: dict`. Formatters consume it;
they should not re-read files.

Shared comparator helpers live in `src/comparators/_shared.py`:
- `preprocess_dataframe(df, ignore_case, ignore_whitespace)` — applies
  string-normalization only to object-dtype columns.
- `build_differences_mask(df1, df2)` — NaN-safe vectorised equality
  (`values_differ & ~(isna & isna)`). **Do not reintroduce the old
  `fillna(object_sentinel)` pattern** — it emits pandas FutureWarning
  and will break on future pandas.

`AppConfig` (`src/core/config.py`) is pydantic v2 `BaseModel`. `validate()`
is fire-and-log, never raising, by contract — tests rely on this.
`__setattr__` is overridden to allow the runtime-only `logger` and
`config_path` attributes. Field defaults must stay stable: they are part
of the public contract (checked by `tests/test_config.py`).

## Testing contract

- `filterwarnings = ["error"]` is active in `pyproject.toml`. Any warning
  fails the test suite. If you hit one, fix the underlying code; do not
  add a suppression without documenting it.
- `tests/conftest.py` generates xlsx fixtures into `tmp_path` — never
  commit binary xlsx files. Use `xlsx_to_dict` helper for snapshot
  assertions (zip timestamps make byte-diff unreliable).
- `src/core/interfaces.py` is excluded from coverage (abstract method
  stubs).
- `src/gui/*` is excluded from mypy strict — tkinter callbacks pervade
  `Any`. Do not try to annotate it under strict mode without a wider
  refactor.

## Pre-existing bugs & their status

`TODO_bugs.md` tracks latent bugs found during the characterization
phase. As of the last commit: #1–#3 fixed, #4 (key_columns cell-level
alignment in `AdvancedComparator`) documented as a partial limitation
— passing `key_columns` logs a WARNING and falls back to positional
comparison. Don't silently change this behaviour; the warning and the
docstring in `advanced_comparator.py` are part of the contract.

## Commit conventions

Conventional Commits: `test:`, `refactor:`, `perf:`, `fix:`, `chore:`,
`docs:`. One logical change per commit; tests must be green before each
commit. Bug fixes go in their own `fix:` commits, separate from refactor
work, so history stays bisectable.
