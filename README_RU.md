# Excel Comparator

Сравнивает два табличных файла — Excel или CSV — по ячейкам и пишет отчёт с найденными различиями.

Работает как настольное приложение (tkinter) или из командной строки. Отчёт сохраняется в `.xlsx` с подсветкой различающихся ячеек и листом сводки, в `.html` с таблицами рядом, либо в `.csv` с колонкой статуса по каждой строке.

## Требования

- Python 3.11 или новее
- pandas, numpy, openpyxl, chardet, python-dateutil

Точные диапазоны версий — в [requirements.txt](requirements.txt). Графическому интерфейсу нужен tkinter: на Windows и macOS он входит в стандартный установщик CPython, на Linux ставится из пакетного менеджера, например `apt install python3-tk`.

## Установка

```bash
pip install -r requirements.txt
python main.py
```

Запуск `python main.py` без аргументов открывает графический интерфейс. Для командной строки добавьте `--cli`.

## Использование

### Графический интерфейс

Выберите первый файл, второй файл и имя для результата. Поля выбора принимают `.xlsx`, `.xls`, `.csv`, `.tsv` и `.txt`. Расширение выходного файла задаёт формат отчёта (`.xlsx`, `.html` или `.csv`).

В блоке **Опции сравнения**:

- **Тип сравнения** — `basic` или `advanced`.
- **Игнорировать регистр**.
- **Игнорировать пробелы**.
- **Пропускать повреждённые строки** — по умолчанию выключено. Если включить, строки CSV, которые pandas не смог разобрать, отбрасываются и подсчитываются, а не прерывают загрузку. При выключенной галочке битый CSV завершается ошибкой — это строгий режим по умолчанию.

Кнопка **Сравнить файлы** запускает сравнение. По завершении окно показывает общее число ячеек, число различающихся ячеек и процент схожести.

Чем отличаются `basic` и `advanced`:

- `basic` ждёт, что обе таблицы одного размера и с одинаковыми именами столбцов. Сравнивает ячейку с ячейкой и завершается ошибкой, если структура расходится.
- `advanced` работает с разным числом строк и разными наборами столбцов. Выравнивает данные и помечает строки, которые есть только в одном файле.

### Командная строка

```bash
python main.py --cli --file1 prod.xlsx --file2 staging.xlsx --output diff.xlsx
```

В режиме CLI всегда берётся компаратор `advanced`. Флаги:

- `--file1`, `--file2`, `--output` — обязательны вместе с `--cli`.
- `--format {xlsx,html,csv}` — задать формат отчёта вместо определения по расширению.
- `--ignore-case`, `--ignore-whitespace` — то же, что галочки в интерфейсе.
- `--csv-encoding ENC` — задать кодировку входа вместо автоопределения через chardet.
- `--csv-delimiter SEP` — задать разделитель вместо автоопределения.
- `--csv-skip-rows N` — пропустить первые N строк каждого CSV.
- `--chunk-size N` — строк в чанке, когда CSV больше 100 МБ (по умолчанию 50000).
- `--csv-on-bad-lines {error,skip,warn}` — `error` прерывает на битой строке (по умолчанию), `skip` молча её отбрасывает, `warn` отбрасывает и пишет в лог число отброшенных.
- `--log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}`.

CSV с заданным разделителем и кодировкой, с пропуском битых строк:

```bash
python main.py --cli \
    --file1 prod.csv --file2 staging.csv --output diff.csv \
    --csv-delimiter ";" --csv-encoding cp1251 --csv-on-bad-lines skip
```

## Форматы вывода

Формат определяется расширением выходного файла: `.xlsx`/`.xls` → Excel, `.html`/`.htm` → HTML, `.csv` → CSV, прочее → Excel. Флаг `--format` это переопределяет.

- **Excel** — два листа с исходными данными и подсветкой различающихся ячеек плюс лист сводки со статистикой. Ширина столбцов считается по первым 200 строкам. На таблицах больше 20 000 строк форматтер пишет в лог предупреждение с советом взять HTML: поячеечная подсветка на таком объёме замедляется.
- **HTML** — сводка, число различий по столбцам и две таблицы рядом с подсветкой расхождений. Таблицы больше ~1000 строк разбиваются на файлы `_page_N.html` рядом с основным.
- **CSV** — исходные столбцы плюс завершающая колонка `__status__` со значениями `EQUAL`, `MODIFIED`, `ADDED` или `REMOVED`. Строки `ADDED` берут содержимое из второго файла. Кодировка, разделитель и quoting задаются опциями; `diff_only` (через API) убирает строки `EQUAL`.

Для входных CSV и TSV кодировка определяется автоматически (chardet, при неуверенности — UTF-8), разделитель выбирается из `,`, `;`, табуляции и `|`. BOM снимается сам.

## Конфигурация

При первом запуске приложение пишет `config.json` в каталог пользователя:

- Windows: `%APPDATA%\ExcelComparator\config.json`
- Linux / macOS: `~/.config/excel-comparator/config.json`

Там лежат настройки сравнения по умолчанию, размер окна и шрифт интерфейса, уровень логирования и список недавних файлов. Сохранение идёт автоматически; одинаковая запись пропускается, поэтому файл не переписывается на каждое действие.

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

Логи времени выполнения пишутся в `logs/app.log` в рабочем каталоге.

## Разработка

Создайте виртуальное окружение и поставьте зависимости для разработки:

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux / macOS
pip install -r requirements-dev.txt
```

Проверки перед коммитом:

```bash
python -m pytest tests/ -q --ignore=tests/test_benchmarks.py   # модульные + property + snapshot тесты
python -m pytest tests/ --cov=src --cov-branch                 # покрытие веток, держим >=85%
python -m ruff check src/ tests/
python -m ruff format --check src/ tests/
python -m mypy src/                                            # строгий режим
python -m pytest tests/test_benchmarks.py --benchmark-only     # производительность
```

`ComparisonEngine` (`src/core/engine.py`) связывает сменные части: загрузчики файлов (`src/loaders`), компараторы (`src/comparators`), форматтеры вывода (`src/formatters`) и валидаторы (`src/validators`). Чтобы добавить входной формат или способ сравнения, пишут один класс под нужный интерфейс и регистрируют его в движке.

### Отдельный исполняемый файл

Сборка одного `.exe` под Windows через PyInstaller:

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name ExcelComparator --add-data "src;src" main.py
```

Результат — `dist/ExcelComparator.exe`. На Linux / macOS поменяйте разделитель в `--add-data` с `;` на `:`.
