# Excel Comparator

Compares two table files — Excel or CSV — cell by cell and writes a report that shows what changed.

It runs as a desktop app (tkinter) or from the command line. Reports come out as `.xlsx` with the differing cells highlighted and a summary sheet, `.html` with side-by-side tables, or `.csv` with a per-row status column.

## Requirements

- Python 3.11 or newer
- pandas, numpy, openpyxl, python-calamine, XlsxWriter, chardet, python-dateutil
- for the GUI: sv-ttk (Windows 11 look) and tkinterdnd2 (drag and drop of files)

The exact version ranges are in [requirements.txt](requirements.txt). The GUI needs tkinter, which ships with the standard CPython installer on Windows and macOS. On Linux install it from your package manager, e.g. `apt install python3-tk`. If sv-ttk or tkinterdnd2 fails to load, the window still opens, with the stock look and without drag and drop.

## Installation

```bash
pip install -r requirements.txt
python main.py
```

`python main.py` with no arguments opens the GUI. For the command line add `--cli`.

## Usage

### GUI

One window, three steps:

1. Drag two files from Explorer onto the window, or click **Выбрать…** (choose) on the "first file" and "second file" cards. `.xlsx`, `.xls`, `.csv`, `.tsv` and `.txt` are accepted. A file dropped on a card goes into that card; two files dropped on the window fill both cards in order. The **⇄** button swaps the files.
2. Click **Сравнить** (compare) or press Enter.
3. The verdict appears in the same window: a green "data matches" or a red "differences found" banner with the counts. **Открыть отчёт** opens the Excel report with the differences highlighted, **Показать в папке** opens its folder.

The **Порядок строк не важен** (row order does not matter) switch is on by default: rows are matched by content (see below). Turn it off to compare rows by position.

Rarely used settings sit in the collapsible **Дополнительно** (more) block:

- **Ключевые столбцы** (key columns) — comma-separated, e.g. `dt, idUser`. Enabled while the row-order switch is on.
- **Ignore case** and **ignore leading/trailing whitespace**.
- **Skip malformed CSV rows** — when on, CSV rows that pandas cannot parse are dropped instead of stopping the load.
- **Отчёт** (report) — where the report goes. By default next to the first file as `Сравнение.xlsx`; an existing report is never overwritten, the next one becomes `Сравнение (2).xlsx`, `Сравнение (3).xlsx`… **Изменить…** sets another path; its extension picks the format (`.xlsx`, `.html`, `.csv`).

The window uses the Windows 11 look and follows the Windows light or dark app theme. The last options and the folder of the last files are remembered between runs. F1 or the **?** button opens a short help.

The window always uses the `advanced` comparator. How `basic` and `advanced` differ (both remain available from code):

- `basic` expects both tables to have the same shape and the same column names. It compares cell to cell and errors out if the structure differs.
- `advanced` handles different row counts and different column sets. It aligns the data and marks rows that exist on only one side.

### Ignoring row order

A normal comparison is positional: row 1 against row 1, row 2 against row 2. Two exports with the same rows in a different order then show almost every cell as different. The ignore-row-order mode (the **Порядок строк не важен** switch in the window, `--ignore-row-order` on the command line) works with `basic` and `advanced` and pairs rows by content:

- **Without key columns** rows are paired in two passes. Identical rows come first. Then, among the rows left over, the tool looks for "the same row, changed": a pair qualifies when at least half of the columns are equal. An equal rare value (a player id, an amount) weighs more than an equal common one (0, a currency, a date). If a row has two equally good candidates it stays unpaired, because a row reported in one file only is better than a wrong pair. Such pairs are marked "по сходству" (by similarity) in the report.
- **With key columns** rows are paired by key, and differences in the other columns are highlighted in the report as in a normal comparison.
- Duplicate rows pair in order of appearance: two equal rows against one give one match and one row only in the first file.
- `8000` equals `8000.0`; empty cells, `NaN` and `None` are equal; a date without a time equals the same date written as text (`2026-09-01`). Numbers stored as text are not compared with numbers.

In the report the rows of the first file keep their order, each next to its match from the second file, and rows found only in the second file come last. The **Сводка** (summary) sheet gets a row-matching block: the verdict (match / differences found), how many rows matched, how many changed rows found their pair (and how many of them by similarity), how many exist in only one file, whether the order differs, and per-file totals of the numeric columns. The totals use `math.fsum`, so row order does not change them. The similarity percentage is rounded down: a single differing cell among tens of thousands shows `99.99%`, not `100.00%`.

The **Расхождения** (differences) sheet, second after the summary, lists only the rows that differ. A changed row takes two lines, one from file 1 and one from file 2. The changed cells are highlighted, the source row number in each file is shown, and a "Что изменилось" (what changed) column reads, for example, `Sum_in_from_sum_out: 1000 → 100 (-900)`. Numeric differences are file 2 − file 1, as in the column totals. A row without a pair takes one line. The sheet lists every difference that fits into one Excel sheet (1,048,576 rows).

### CLI

```bash
python main.py --cli --file1 prod.xlsx --file2 staging.xlsx --output diff.xlsx
```

The CLI always uses the `advanced` comparator. Flags:

- `--file1`, `--file2`, `--output` — required together with `--cli`.
- `--format {xlsx,html,csv}` — force the report format instead of reading it from the output extension.
- `--ignore-case`, `--ignore-whitespace` — same as the GUI checkboxes.
- `--ignore-row-order` — compare without regard to row order (the "ignore row order" checkbox).
- `--key-columns "dt,idUser"` — key columns for `--ignore-row-order`; without them rows match as a whole, and changed rows by similarity.
- `--full-data-sheets` — full data sheets in the Excel report even for tables over 100,000 rows (the "Полные листы данных для больших файлов" checkbox).
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

Two exports of a report whose rows may come in a different order, paired by date and player:

```bash
python main.py --cli --file1 old.xlsx --file2 new.xlsx --output diff.xlsx \
    --ignore-row-order --key-columns "dt,idUser"
```

## Output formats

The format follows the output extension: `.xlsx`/`.xls` → Excel, `.html`/`.htm` → HTML, `.csv` → CSV, anything else → Excel. `--format` overrides that.

- **Excel** — a summary sheet with the statistics (and, when ignoring row order, the row-matching block), the «Расхождения» sheet with only the rows that differ, and two sheets holding the source data with the differing cells highlighted. The «Различия» column on both data sheets describes each change in one direction, file 1 → file 2. The data sheets are written for tables up to 100,000 rows. Above that they need the "Полные листы данных для больших файлов" checkbox or `--full-data-sheets`, and the summary says they were left out. Column widths are sized from the first 200 rows. Text that looks like a formula (`=A1`) or a link stays text. The report is streamed (XlsxWriter): memory does not grow with the table, and the progress shows the writing.
- **HTML** — a summary, per-column difference counts, and the two tables side by side with differences highlighted. Tables over ~1000 rows are split into `_page_N.html` files next to the main one.
- **CSV** — the source columns plus a trailing `__status__` column with `EQUAL`, `MODIFIED`, `ADDED` or `REMOVED`. `ADDED` rows carry the content from the second file. Encoding, delimiter and quoting are options; `diff_only` (via the API) drops the `EQUAL` rows.

CSV and TSV inputs autodetect their encoding (chardet, falling back to UTF-8) and their delimiter (chosen from `,`, `;`, tab and `|`). A byte-order mark is stripped automatically.

## Large files

- **Reading.** `.xlsx` and `.xls` are read with python-calamine (Rust): 5–7× faster than openpyxl with the same column types, because pandas still infers them. Both files load at the same time. Without python-calamine the program falls back to openpyxl, only slower.
- **Comparison.** Rows are matched on integer codes of the values instead of hashing Python objects one by one.
- **Report.** Full data sheets are written up to 100,000 rows (see above), and the report is streamed.
- **Progress** moves through every stage: each file loaded (20 and 40 %), comparison (42–55 %), report writing in steps of 10,000 rows (55–99 %).

Example: two exports of 380,598 rows × 9 columns, 16 MB xlsx each, ignoring row order.

| Version | Time |
|---|---|
| Previous (openpyxl, full data sheets) | 145 s |
| Current | ≈ 12 s: loading ≈ 5 s, comparison ≈ 1.5 s, report under a second |
| Current with `--full-data-sheets` | ≈ 45–80 s, depending on machine load |

## Configuration

On first run the app writes `config.json` to a per-user directory:

- Windows: `%APPDATA%\ExcelComparator\config.json`
- Linux / macOS: `~/.config/excel-comparator/config.json`

It holds the comparison defaults (the window stores the last chosen options and key columns there), the log level and the recent-files list, which the window uses to open the file dialog in the folder of the last file. Saving is automatic; an identical save is skipped, so the file is not rewritten on every action.

```json
{
  "comparison": {
    "ignore_case": false,
    "ignore_whitespace": false,
    "ignore_row_order": true,
    "key_columns": [],
    "full_data_sheets": false,
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
pyinstaller --onefile --windowed --name ExcelComparator --icon assets/app.ico ^
    --add-data "src;src" --collect-data sv_ttk --collect-all tkinterdnd2 main.py
```

The result is `dist/ExcelComparator.exe`. `--collect-data sv_ttk` bundles the theme files and `--collect-all tkinterdnd2` the drag-and-drop library; without them the window opens with the stock look and without drag and drop. On Linux / macOS change the `--add-data` separator from `;` to `:` and the `^` line continuation to `\`.
