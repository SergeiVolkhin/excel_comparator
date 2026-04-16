# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
