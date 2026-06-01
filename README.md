# Excel Comparator

Compares two table files — Excel or CSV — cell by cell and writes a report that shows what changed.

It runs as a desktop app (tkinter) or from the command line. Reports come out as `.xlsx` with the differing cells highlighted and a summary sheet, `.html` with side-by-side tables, or `.csv` with a per-row status column.

## Requirements

- Python 3.11 or newer
- pandas, numpy, openpyxl, chardet, python-dateutil

The exact version ranges are in [requirements.txt](requirements.txt). The GUI needs tkinter, which ships with the standard CPython installer on Windows and macOS. On Linux install it from your package manager, e.g. `apt install python3-tk`.

## Installation

```bash
pip install -r requirements.txt
python main.py
```

`python main.py` with no arguments opens the GUI. For the command line add `--cli`.

## Usage

### GUI

Pick the first file, the second file, and an output name. The file pickers accept `.xlsx`, `.xls`, `.csv`, `.tsv` and `.txt`. The output extension decides the report format (`.xlsx`, `.html` or `.csv`).

The **Опции сравнения** (comparison options) box has:

- **Тип сравнения** (comparison type) — `basic` or `advanced`.
- **Игнорировать регистр** (ignore case).
- **Игнорировать пробелы** (ignore whitespace).
- **Пропускать повреждённые строки** (skip malformed rows) — off by default. When on, CSV rows that pandas cannot parse are dropped and counted instead of stopping the load. Left off, a broken CSV fails with an error, which is the strict default.

Click **Сравнить файлы** to run. When it finishes, a dialog reports the total cell count, the number of differing cells and a similarity percentage.

`basic` and `advanced` differ in how much mismatch they tolerate:

- `basic` expects both tables to have the same shape and the same column names. It compares cell to cell and errors out if the structure differs.
- `advanced` handles different row counts and different column sets. It aligns the data and marks rows that exist on only one side.

### CLI

```bash
python main.py --cli --file1 prod.xlsx --file2 staging.xlsx --output diff.xlsx
```

The CLI always uses the `advanced` comparator. Flags:

- `--file1`, `--file2`, `--output` — required together with `--cli`.
- `--format {xlsx,html,csv}` — force the report format instead of reading it from the output extension.
- `--ignore-case`, `--ignore-whitespace` — same as the GUI checkboxes.
- `--csv-encoding ENC` — force an input encoding instead of autodetecting with chardet.
- `--csv-delimiter SEP` — force the delimiter instead of autodetecting it.
- `--csv-skip-rows N` — skip the first N rows of each CSV.
- `--chunk-size N` — rows per chunk when a CSV is over 100 MB (default 50000).
- `--csv-on-bad-lines {error,skip,warn}` — `error` stops on a malformed row (default), `skip` drops it silently, `warn` drops it and logs how many were dropped.
- `--log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}`.

A CSV run with a forced delimiter and encoding, skipping broken rows:

```bash
python main.py --cli \
    --file1 prod.csv --file2 staging.csv --output diff.csv \
    --csv-delimiter ";" --csv-encoding cp1251 --csv-on-bad-lines skip
```

## Output formats

The format follows the output extension: `.xlsx`/`.xls` → Excel, `.html`/`.htm` → HTML, `.csv` → CSV, anything else → Excel. `--format` overrides that.

- **Excel** — two sheets holding the source data with the differing cells highlighted, plus a summary sheet with the statistics. Column widths are sized from the first 200 rows. Above 20,000 rows the formatter logs a warning suggesting an HTML report instead, because per-cell styling slows down at that size.
- **HTML** — a summary, per-column difference counts, and the two tables side by side with differences highlighted. Tables over ~1000 rows are split into `_page_N.html` files next to the main one.
- **CSV** — the source columns plus a trailing `__status__` column with `EQUAL`, `MODIFIED`, `ADDED` or `REMOVED`. `ADDED` rows carry the content from the second file. Encoding, delimiter and quoting are options; `diff_only` (via the API) drops the `EQUAL` rows.

CSV and TSV inputs autodetect their encoding (chardet, falling back to UTF-8) and their delimiter (chosen from `,`, `;`, tab and `|`). A byte-order mark is stripped automatically.

## Configuration

On first run the app writes `config.json` to a per-user directory:

- Windows: `%APPDATA%\ExcelComparator\config.json`
- Linux / macOS: `~/.config/excel-comparator/config.json`

It holds the comparison defaults, the GUI window size and font, the log level and the recent-files list. Saving is automatic; an identical save is skipped, so the file is not rewritten on every action.

```json
{
  "comparison": {
    "ignore_case": false,
    "ignore_whitespace": false,
    "highlight_color": "FFFF00",
    "max_differences_display": 1000,
    "enable_list_analysis": true,
    "list_separator": ","
  },
  "gui": {
    "window_width": 800,
    "window_height": 600,
    "theme": "default",
    "font_family": "Arial",
    "font_size": 10
  },
  "log_level": "INFO",
  "auto_save_config": true,
  "recent_files": [],
  "max_recent_files": 10
}
```

Runtime logs are written to `logs/app.log` under the working directory.

## Development

Create a virtual environment and install the dev dependencies:

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux / macOS
pip install -r requirements-dev.txt
```

The checks that gate a commit:

```bash
python -m pytest tests/ -q --ignore=tests/test_benchmarks.py   # unit + property + snapshot tests
python -m pytest tests/ --cov=src --cov-branch                 # branch coverage, held at >=85%
python -m ruff check src/ tests/
python -m ruff format --check src/ tests/
python -m mypy src/                                            # strict
python -m pytest tests/test_benchmarks.py --benchmark-only     # performance
```

`ComparisonEngine` (`src/core/engine.py`) wires together the replaceable parts: file loaders (`src/loaders`), comparators (`src/comparators`), output formatters (`src/formatters`) and validators (`src/validators`). Adding an input format or a comparison strategy means writing one class against the matching interface and registering it on the engine.

### Standalone binary

Build a single-file Windows executable with PyInstaller:

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name ExcelComparator --add-data "src;src" main.py
```

The result is `dist/ExcelComparator.exe`. On Linux / macOS change the `--add-data` separator from `;` to `:`.
