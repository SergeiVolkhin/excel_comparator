# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-04-16

CSV promoted to a first-class input and output format in parity with
Excel. Loader extended, new output formatter, CSV-specific validators,
CLI flags. Two latent bugs in the delimiter auto-detect fixed.

### Added

- **`CSVOutputFormatter`** (`src/formatters/csv_formatter.py`). Writes
  comparison results to CSV with a trailing `__status__` column
  (`EQUAL` / `MODIFIED` / `ADDED` / `REMOVED`). Options: `encoding`
  (incl. `utf-8-sig` for BOM), `delimiter`, `quoting` (csv.QUOTE_*),
  `lineterminator`, `diff_only=True` (drop equal rows). Registered by
  default under the `"csv"` key.
- **Chunked CSV loading**. `CSVFileLoader.load()` switches to a pandas
  chunk iterator when the file exceeds 100 MB (default 50 000 rows per
  chunk; override via `chunk_size=`). Keeps peak memory bounded to one
  chunk instead of the usual ~3× file-size pandas materialisation.
- **CSV-specific validators** (`src/validators/csv_validators.py`):
  - `CSVRowCountRatioValidator` — flags implausible row-count imbalances
    (>100× by default), a common symptom of a wrong delimiter choice.
  - `CSVSingleColumnCollapseValidator` — flags a one-column object
    DataFrame whose sample rows still contain CSV delimiters.
  - `ValidationRuleFactory.for_csv(config)` bundles standard rules +
    the CSV-specific ones.
- **CLI flags** (additive, existing flags unchanged):
  - `--format {xlsx,html,csv}` — override suffix-based formatter
    auto-detection.
  - `--csv-encoding ENC`, `--csv-delimiter SEP`, `--csv-skip-rows N`,
    `--chunk-size N` — forwarded to the CSV loader.
- **Expanded `CSVFileLoader.load()` docstring** listing every
  first-class kwarg, auto-detected defaults, and the pinned
  `engine="python"`.
- **Integration tests** (`tests/test_csv_integration.py`) — CSV↔CSV
  across delimiters / encodings / ignore_case / ignore_whitespace, and
  CSV↔Excel in both directions.
- **Snapshot tests** (`tests/test_csv_formatter.py`) — pin the
  `__status__` column contract, ADDED/REMOVED row swap, writer
  options, and `diff_only` mode.
- **Hypothesis property tests** (`tests/test_csv_properties.py`) —
  delimiter auto-detect invariance, encoding round-trip, and
  formatter→loader roundtrip.
- **CLI tests** (`tests/test_cli.py`) covering the new flags and
  `run_cli_mode` end-to-end with CSV inputs and outputs.
- **CSV benchmarks** in `tests/test_benchmarks.py` (10k load,
  200k load, 200k compare).

### Changed

- **`ComparisonEngine` default composition** now includes
  `CSVFileLoader` and `CSVOutputFormatter`. Callers that previously
  registered `CSVFileLoader` manually still work — the extra
  registration is a harmless duplicate.
  Breaking for code that introspects `get_available_formatters()` (set
  grows from `{excel, html}` to `{excel, html, csv}`) or
  `get_supported_file_extensions()` (now also `.csv/.txt/.tsv`).
- `engine._determine_formatter` maps `.csv` → `"csv"`.

### Fixed

- **`_SEPARATOR_CANDIDATES` tab literal (bug B1).** The candidate list
  held the two-char string `"\\t"` (backslash + t), so the scorer's
  `line.split(sep)` never matched a real tab. Tab-delimited `.csv`
  files fell through to the comma fallback. The `.tsv` short-circuit
  worked only by accident, via `engine="python"` regex rewriting.
  Replaced with a genuine tab character in both places.
- **Space delimiter candidate (bug B2).** Dropped `" "` from the
  scoring set: consistent spacing between columns produced false
  positives that overrode the intended delimiter.
- **`StandardComparisonStrategy.execute` double-kwarg.** The strategy
  did `options.get("formatter_name")` while still passing `**options`
  through to `engine.compare_files`, which accepts `formatter_name`
  explicitly. Triggered `TypeError: multiple values for keyword
  argument 'formatter_name'` once the CLI started populating that
  key. Switched to `pop` for both `comparator_name` and
  `formatter_name`.
- **`main.py` stdout reconfiguration** now only runs from `__main__`;
  importing the module under pytest no longer closes the captured
  stdout.

### Test suite

- Grew from **144** pytest cases to **223** (all green) plus 2 slow
  tests (opt-in via `-m slow`). Branch coverage:
  - `src/loaders/csv_loader.py`: 80 % → **99 %**.
  - `src/formatters/csv_formatter.py`: new, **100 %**.
  - `src/validators/csv_validators.py`: new, **97 %**.
  - Total: 89 % → **91 %**.

## [0.1.0] - 2026-04-16

First tagged release. Baseline snapshot of the codebase after the
three-phase refactor: safety net (characterization tests), structural
cleanup (types, pydantic-settings, dedupe), and infrastructure
(pre-commit + CI + docs). Public API preserved throughout.

### Added

- `ExcelFileLoader.load(..., read_only=True)` streams xlsx through
  openpyxl's read-only mode. Memory use is now O(rows) instead of full
  workbook materialisation; ~15 % faster wall-time on 10k×5.
- Pre-commit config (`.pre-commit-config.yaml`) wiring ruff, mypy,
  hygiene hooks and a pre-push pytest smoke test.
- GitHub Actions CI (`.github/workflows/ci.yml`) running lint, strict
  mypy and test matrix on Python 3.11 / 3.12 / 3.13.
- Latent-bug register (`TODO_bugs.md`) with statuses.
- Baseline pytest-benchmark suite and benchmark comparison workflow.
- Hypothesis property-based tests for value comparison and preprocessing.
- Snapshot tests for xlsx/html output using `openpyxl → dict` to avoid
  zip-timestamp noise.
- Fixture-driven xlsx generation in `tests/conftest.py` (no binary
  artefacts committed).

### Changed

- **Minimum Python bumped to 3.11** (was 3.8). Modern type-hint syntax
  (`list[str]`, `X | None`) used throughout.
- `AppConfig` migrated from `@dataclass` to `pydantic.BaseModel`. Public
  field names, defaults and method signatures preserved.
- `BasicComparator` / `AdvancedComparator` share `_shared.py` helpers
  (`preprocess_dataframe`, `build_differences_mask`) — duplicated
  logic removed.
- `ExcelOutputFormatter` iterates only over diff positions
  (`mask.values.nonzero()`) instead of the full rows × cols grid.
  10k×5 format time: **1003 ms → 681 ms (−32 %)**.
- `engine.compare_files` split into load / validate / compare / format
  helpers; each < 30 lines with cyclomatic complexity ≤ 10.
- Magic numbers extracted to named constants (`SHEET_NAME_MAX_LEN`,
  `DEFAULT_HTML_PAGE_SIZE`, `DEFAULT_HIGHLIGHT_COLOR`).

### Fixed

- `ExcelFileLoader.get_sheet_names` no longer leaks a file handle
  (`pd.ExcelFile` is now context-managed; xlsx path uses
  `load_workbook(read_only=True)`). *(TODO_bugs #1)*
- Diff-mask construction no longer triggers pandas
  `FutureWarning: Downcasting object dtype arrays on .fillna ...`.
  Replaced `fillna(object_sentinel)` with a NaN-safe vectorised
  expression. *(TODO_bugs #2)*
- `preprocess_dataframe` under `ignore_case`/`ignore_whitespace` now
  correctly skips numeric columns; NaN detection switched from
  `astype(str) != 'nan'` to `notna()`. *(TODO_bugs #3)*
- `AdvancedComparator.compare(key_columns=...)` now emits a WARNING
  explaining that cell-level alignment still falls back to positional
  comparison (previously this limitation was silent). *(TODO_bugs #4,
  partial: full key-based alignment tracked as a planned feature.)*

### Tooling / Infra

- `pyproject.toml` introduced: project metadata, dev deps, ruff config,
  mypy strict config, pytest config with `filterwarnings = ["error"]`.
- `requirements-dev.txt` for pip-only workflows.
- Branch coverage goal: **≥ 85 %** on main modules (currently 88 %).

### Test suite

- Grew from **9 unittest cases** to **144 pytest cases** (characterization,
  snapshots, property-based, regressions, benchmarks).
- Regression tests added for each fixed latent bug.
