# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Large files: about 12× faster end to end.** Two exports of 380 598 ×
  9 (16 MB xlsx each), ignoring row order: 145 s → ≈ 12 s.
  - xlsx/xls are read with python-calamine (`pd.read_excel(engine=
    "calamine")`, 5–7× faster than openpyxl; pandas still infers the
    column types, so the frames are identical — pinned by a test). openpyxl
    stays the fallback when calamine is not installed.
  - Both files load concurrently (`ThreadPoolExecutor`, calamine parses
    without the GIL): about 26 % off the load stage.
  - Full data sheets are written up to `DATA_SHEETS_MAX_ROWS` = 100 000
    rows; above that the report is «Сводка» + «Расхождения» and the
    summary says why. GUI checkbox «Полные листы данных для больших
    файлов», CLI `--full-data-sheets`, `ComparisonSettings.full_data_sheets`
    force them.
  - Row matching runs on integer value codes (`_Codes` in
    `row_matching.py`): per-column `factorize` (raw values for plain numpy
    and text columns, canonical values otherwise), row keys packed as
    mixed-radix numbers, duplicates paired via (group, occurrence) and an
    index lookup, cell differences by comparing codes. Same semantics, all
    existing tests unchanged; 200 000 rows: 1.3 s → 0.65 s.
- **Progress that moves.** The engine reports each loaded file (20 / 40 %),
  the comparison (42–55 %) and the report writing in steps of 10 000 rows
  (55–99 %, through a `progress(share, message)` callback in the formatter
  options) instead of 0/20/30/70/100 with the whole report written after
  «70 % Сравнение выполнено». The CLI progress line no longer leaves
  remnants of a longer previous message.
- **Changed rows are found without key columns.** With
  `ignore_row_order` and no `key_columns`, the rows left without an
  identical row get a second, similarity pass (`_pair_similar_rows` in
  `src/comparators/row_matching.py`). Two rows pair when at least half of
  the columns are equal; candidates are scored by the summed weight of
  their equal values (`log(N / count)` over both files, so a rare id
  outweighs a common 0 or currency). A pair is taken only when it is the
  clear best of both rows; a tie leaves the rows unpaired. Identical
  leftover rows are grouped first, so duplicates pair correctly.
  Candidates come from blocking on shared values, capped at 2 million
  pairs, so the pass stays linear on large files: on 200 000 rows with
  1 % changed it finds all of them in about 1.3 s.
  `row_match["similar"]` counts such pairs; they are part of `modified`.
- `ComparisonResult.row_pairs` (all comparators): the source row of each
  aligned row in both files and its status (`equal`, `modified`,
  `similar`, `only_file1`, `only_file2`).
- Excel: «Расхождения» sheet with only the rows that differ. A changed
  row takes two lines (file 1 and file 2) with the changed cells
  highlighted, the source row number in each file and a «Что изменилось»
  column such as `Sum_in_from_sum_out: 1000 → 100 (-900)`. The sheet
  lists every difference that fits into one Excel sheet. The engine passes
  `first_data_row` to the formatter (header row and CSV `skiprows` taken
  into account).
- Numeric differences are described with their delta, file 2 − file 1,
  computed in `Decimal` (`2414.45 → 2414.5 (+0.05)`).

- **Order-independent comparison** — new `ignore_row_order` option for
  both `BasicComparator` and `AdvancedComparator`
  (`src/comparators/row_matching.py`). Rows are paired by content, or by
  `key_columns` when given, instead of by position, so two exports with
  the same rows in a different order compare as equal. Duplicates pair in
  order of appearance; `8000` equals `8000.0`, NA flavours are equal, a
  midnight datetime equals its ISO date string. The aligned frames keep
  the positional contract, so the Excel / HTML / CSV formatters work
  unchanged (unmatched rows are NA-padded like `advanced` does).
  `metadata["row_match"]` carries matched / modified / only-in-file
  counts, an `order_changed` flag, an `identical` verdict and exact
  (`math.fsum`) per-column totals.
- CLI: `--ignore-row-order` and `--key-columns "dt,idUser"`; the summary
  printout includes the row-matching block.
- Excel summary sheet: row-matching block with the verdict and a
  per-column totals table. HTML report: row-matching stat cards.
- **New one-window GUI** (`src/gui/`): two file cards → «Сравнить» → the
  verdict in the same window. Windows 11 look via **sv-ttk**, light or dark
  following the Windows app theme (dark title bar through DWM); drag and
  drop of files via **tkinterdnd2** (one file onto a card, two files onto
  the window); swap button; inline progress bar instead of a modal dialog;
  green/red result banner with «Открыть отчёт» / «Показать в папке»;
  rarely used options in a collapsible «Дополнительно» block. Both
  libraries are optional at runtime: without them the window falls back to
  the stock theme and to the «Выбрать…» buttons.
- `src/core/result_summary.py`: plain-language verdict for the result
  banner (`summarize`), a report name that never overwrites an earlier
  report (`next_free_path`: `Сравнение (2).xlsx`…), `human_size`.
- `ComparisonSettings.key_columns`; the GUI remembers the last options and
  key columns, and `run_gui_mode` now actually loads `config.json` (it was
  written but never read back).

### Changed

- Help («?» / F1) is a window in the app's own look (`src/gui/help_window.py`,
  light and dark) instead of a plain message box: three numbered steps,
  what each report sheet shows, the settings in one line each and the
  keys. Modal, one instance, closes with «Понятно», Enter or Esc.
- GUI defaults to «Порядок строк не важен» (`ignore_row_order=True` in
  `ComparisonSettings`); the CLI keeps its explicit flag.
- The report goes next to the first file by default instead of
  `Сравнение.xlsx` in the working directory.
- The comparison runs in a worker thread that talks to the window only
  through a queue; tkinter variables are read on the main thread.

- With `ignore_row_order`, `key_columns` now drive real key-based
  alignment (TODO_bugs.md #4). Without it the previous `advanced`
  behaviour — key-based stats only, plus the warning — is unchanged.
- Column splitting moved to `_shared.split_columns()`; `advanced` uses it.
- `numpy` requirement split by environment marker: `<2.0.0` below
  Python 3.13, `>=2.1.0,<3.0.0` on 3.13+ (numpy 1.x has no wheels there).
- `main.run_cli_mode` builds loader options in `_build_loader_options()`
  (complexity back under the `C901` limit).
- Excel data sheets: the «Различия» column describes each change file 1 →
  file 2 on both sheets (the second sheet used to read file 2 → file 1),
  and a row without a pair reads «Только в файле 1 / 2» instead of one
  «value → NULL» per cell. Row-matching labels: «Совпало по ключу, есть
  отличия» → «Изменённые строки (пара найдена)», plus «из них по сходству»
  in the Excel summary, the HTML cards, the CLI printout and the GUI
  banner.
- `ExcelOutputFormatter` writes with XlsxWriter (`constant_memory`) instead
  of openpyxl: rows stream to temp files, so memory stays flat and the
  progress can follow the writing; about 2–3× faster per cell. Text stays
  text (`strings_to_formulas` / `strings_to_urls` off), datetime columns
  without times get `yyyy-mm-dd`, NaN/NaT are empty cells. Sheet names are
  sanitised (`[]:*?/\`) and made unique, so two files with the same name
  (`data.xlsx` from two folders) no longer clash. A failed write leaves
  neither a half-written report nor XlsxWriter's temp files.
- Differences are described via `BasicDifferenceAnalyzer.describe()` (the
  same text as `analyze()`, without building a `DifferenceDetail`), once
  per row for both the data sheets and «Расхождения».
- `_column_totals` sums through `tolist()` instead of a per-element
  generator (same exact `math.fsum` / integer result).
- New dependencies: `python-calamine>=0.4,<1`, `XlsxWriter>=3.2,<4`.

### Removed

- GUI menu bar (Файл / Настройки / Справка, recent-files menu),
  `SettingsDialog`, `ProgressDialog`, `CenteredDialog`, `FileSelector` and
  the basic/advanced combobox: the window always uses `advanced`; help is
  on F1 and the «?» button. `basic` stays available from code.

### Fixed

- **GUI ignored the comparison type.** `MainWindow._run_comparison` never
  passed `comparator_name`, so the engine always used `advanced` whatever
  the combobox showed. Moot now that the window always uses `advanced`.
- Under sv-ttk, colours set on `ttk.Label` styles are overwritten by
  `tk_setPalette` on every style change; `theme.paint_label` copies the
  style colours onto the widget so captions and banners keep them.
- **A changed row was reported as two unrelated rows.** Without key
  columns, a row with one changed cell went to «только в файле 1» and
  «только в файле 2», and the report listed all its cells as differences
  against an empty row (18 differences for one changed cell). It is now
  found by the similarity pass and shows one changed cell.
- Excel and HTML reports and the CLI printout showed `100.00%` similarity
  with differences present (round-half-up); the percentage is now rounded
  down, as in the GUI (`result_summary.floor_percentage`, which also no
  longer turns 57.3 into 57.29).
- Whole numbers that arrive as floats are described without `.0`
  (`998702019`, not `998702019.0`).
- A positional comparison of two large files with millions of differing
  cells (380 598 rows, 1.76 million cells) did not finish in 35 minutes
  and used 3 GB of memory while openpyxl styled every cell; it now takes
  about 2 minutes with flat memory.

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
