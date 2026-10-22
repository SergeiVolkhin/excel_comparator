"""
Главное окно: два файла → «Сравнить» → итог в том же окне
"""

import logging
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk
from typing import Any

from ..comparators.row_matching import parse_key_columns
from ..core.config import AppConfig
from ..core.engine import ComparisonEngine, StandardComparisonStrategy
from ..core.exceptions import FileLoadError
from ..core.interfaces import ProgressReporter
from ..core.result_summary import DEFAULT_REPORT_NAME, next_free_path, summarize
from .help_window import HelpWindow
from .theme import apply_theme, make_app_icon, paint_labels, set_title_bar_theme
from .widgets import ElidedLabel, Expander, FileCard, ProgressRow, ResultPanel

#: Как часто окно забирает события фонового сравнения, мс
POLL_INTERVAL_MS = 50

#: Ширина содержимого окна по умолчанию, пикселей
CONTENT_MIN_WIDTH = 640

#: Действия перетаскивания (значения tkinterdnd2.COPY / REFUSE_DROP)
DROP_COPY = "copy"
DROP_REFUSE = "refuse_drop"


class _QueueObserver:
    """Передаёт прогресс из фонового потока в очередь окна"""

    def __init__(self, events: "queue.Queue[tuple[str, Any]]") -> None:
        self._events = events

    def on_progress(self, current: int, total: int, message: str = "") -> None:
        self._events.put(("progress", (current, total, message)))

    def on_error(self, error: Exception) -> None:
        """Ошибку окно получает из потока сравнения"""

    def on_completion(self, message: str = "") -> None:
        """Итог окно получает из потока сравнения"""


class MainWindow:
    """Главное окно приложения"""

    def __init__(self, config: AppConfig):
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)

        self.engine = ComparisonEngine(config)
        self.strategy = StandardComparisonStrategy(self.engine)

        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title("Excel Comparator")
        self.dnd_enabled = self._enable_drag_and_drop()
        self.theme = apply_theme(self.root)
        self.root.iconphoto(True, make_app_icon(self.root, self.theme))

        self._manual_report: Path | None = None
        self._last_report: Path | None = None
        self._last_pair: tuple[Path, Path] | None = None
        self._file1_seen = ""
        self._events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._running = False
        self._lockable: list[ttk.Widget] = []
        self._help: HelpWindow | None = None

        self._build()
        self._register_drop_targets()
        self._bind_keys()
        self._refresh()
        self._show_window()
        self.logger.info("Главное окно инициализировано")

    # ------------------------------------------------------------------
    # Построение окна
    # ------------------------------------------------------------------
    def _build(self) -> None:
        main = ttk.Frame(self.root, padding=(24, 20, 24, 24))
        main.grid(row=0, column=0, sticky="nsew")
        self._main_frame = main
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main.columnconfigure(0, weight=1, minsize=CONTENT_MIN_WIDTH)

        self._build_header(main).grid(row=0, column=0, sticky="ew")
        self._build_files(main).grid(row=1, column=0, sticky="ew", pady=(18, 0))
        self._build_row_order(main).grid(row=2, column=0, sticky="ew", pady=(16, 0))
        self.more = self._build_more(main)
        self.more.grid(row=3, column=0, sticky="ew", pady=(12, 0))

        self.compare_button = ttk.Button(
            main, text="Сравнить", style="Big.Accent.TButton", command=self.start_comparison
        )
        self.compare_button.grid(row=4, column=0, sticky="ew", pady=(18, 0))

        self.progress = ProgressRow(main)
        self.progress.grid(row=5, column=0, sticky="ew", pady=(14, 0))
        self.progress.grid_remove()

        self.result_panel = ResultPanel(
            main,
            self.theme,
            on_open_report=self.open_report,
            on_show_folder=self.show_report_in_folder,
        )
        self.result_panel.grid(row=6, column=0, sticky="ew", pady=(16, 0))
        self.result_panel.grid_remove()

        # Цвета подписей — из их стилей (см. paint_label)
        paint_labels(self.root)

    def _build_header(self, parent: ttk.Frame) -> ttk.Frame:
        header = ttk.Frame(parent)
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="Сравнение двух таблиц", style="Title.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        hint = (
            "Перетащите два файла в окно или нажмите «Выбрать…»"
            if self.dnd_enabled
            else "Выберите два файла Excel или CSV"
        )
        ttk.Label(header, text=hint, style="Muted.TLabel").grid(
            row=1, column=0, sticky="w", pady=(2, 0)
        )
        ttk.Button(header, text="?", width=3, style="Toolbutton", command=self.show_help).grid(
            row=0, column=1, rowspan=2, sticky="ne"
        )
        return header

    def _build_files(self, parent: ttk.Frame) -> ttk.Frame:
        files = ttk.Frame(parent)
        files.columnconfigure(0, weight=1, uniform="cards")
        files.columnconfigure(2, weight=1, uniform="cards")

        self.file1_card = self._file_card(files, "Первый файл")
        self.file1_card.grid(row=0, column=0, sticky="nsew")

        self.swap_button = ttk.Button(
            files, text="⇄", width=3, style="Toolbutton", command=self.swap_files
        )
        self.swap_button.grid(row=0, column=1, padx=8)
        self._lockable.append(self.swap_button)

        self.file2_card = self._file_card(files, "Второй файл")
        self.file2_card.grid(row=0, column=2, sticky="nsew")
        return files

    def _file_card(self, parent: ttk.Frame, title: str) -> FileCard:
        card = FileCard(
            parent,
            title,
            on_change=self._on_files_changed,
            initial_dir=self._initial_dir,
            drop_hint=self.dnd_enabled,
        )
        self._lockable.append(card.browse_button)
        return card

    def _build_row_order(self, parent: ttk.Frame) -> ttk.Frame:
        frame = ttk.Frame(parent)
        self.ignore_row_order_var = tk.BooleanVar(value=self.config.comparison.ignore_row_order)
        switch = ttk.Checkbutton(
            frame,
            text="Порядок строк не важен",
            style="Switch.TCheckbutton",
            variable=self.ignore_row_order_var,
            command=self._refresh,
        )
        switch.grid(row=0, column=0, sticky="w")
        self._lockable.append(switch)
        self._row_order_hint = ttk.Label(frame, style="Caption.TLabel")
        self._row_order_hint.grid(row=1, column=0, sticky="w", padx=(4, 0))
        return frame

    def _build_more(self, parent: ttk.Frame) -> Expander:
        more = Expander(parent, "Дополнительно", on_toggle=self._fit_height)
        body = more.body

        ttk.Label(body, text="Ключевые столбцы", style="Caption.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        self.key_columns_var = tk.StringVar(value=", ".join(self.config.comparison.key_columns))
        self.key_columns_entry = ttk.Entry(body, textvariable=self.key_columns_var)
        self.key_columns_entry.grid(row=1, column=0, sticky="ew", pady=(2, 0))
        ttk.Label(
            body,
            text="Через запятую, например: dt, idUser. Пусто — строки сравниваются целиком",
            style="Caption.TLabel",
        ).grid(row=2, column=0, sticky="w", pady=(2, 0))

        self._build_checks(body).grid(row=3, column=0, sticky="w", pady=(10, 0))

        ttk.Label(body, text="Отчёт", style="Caption.TLabel").grid(
            row=4, column=0, sticky="w", pady=(10, 0)
        )
        report = ttk.Frame(body)
        report.grid(row=5, column=0, sticky="ew", pady=(2, 0))
        report.columnconfigure(0, weight=1)
        self.report_label = ElidedLabel(report)
        self.report_label.grid(row=0, column=0, sticky="ew")
        change = ttk.Button(report, text="Изменить…", command=self.choose_report_path)
        change.grid(row=0, column=1, padx=(8, 0))
        self._lockable.append(change)
        return more

    def _build_checks(self, parent: ttk.Frame) -> ttk.Frame:
        checks = ttk.Frame(parent)
        settings = self.config.comparison
        self.ignore_case_var = tk.BooleanVar(value=settings.ignore_case)
        self.ignore_whitespace_var = tk.BooleanVar(value=settings.ignore_whitespace)
        self.skip_bad_lines_var = tk.BooleanVar(value=False)
        self.full_data_sheets_var = tk.BooleanVar(value=settings.full_data_sheets)
        items = [
            ("Игнорировать регистр", self.ignore_case_var, 0, 0),
            ("Игнорировать пробелы по краям", self.ignore_whitespace_var, 0, 1),
            ("Пропускать повреждённые строки CSV", self.skip_bad_lines_var, 1, 0),
            ("Полные листы данных для больших файлов", self.full_data_sheets_var, 1, 1),
        ]
        for text, variable, row, column in items:
            check = ttk.Checkbutton(checks, text=text, variable=variable)
            check.grid(row=row, column=column, sticky="w", padx=(0, 16))
            self._lockable.append(check)
        return checks

    def _bind_keys(self) -> None:
        self.root.bind("<Return>", self.start_comparison)
        self.root.bind("<F1>", lambda _e: self.show_help())
        self.root.bind("<Control-q>", lambda _e: self.root.quit())

    def _show_window(self) -> None:
        """Размер по содержимому, по центру экрана; высота подстраивается сама"""
        self.root.update_idletasks()
        width = self.root.winfo_reqwidth()
        height = self.root.winfo_reqheight()
        x = max((self.root.winfo_screenwidth() - width) // 2, 0)
        y = max((self.root.winfo_screenheight() - height) // 3, 0)
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.root.minsize(width, 1)
        self.root.resizable(True, False)
        dark = self.theme.palette.name == "dark"
        set_title_bar_theme(self.root, dark)
        self.root.deiconify()
        set_title_bar_theme(self.root, dark)

    def _fit_height(self) -> None:
        """Подгоняет высоту окна под содержимое, ширину оставляет как есть"""
        self.root.update_idletasks()
        width = self.root.winfo_width()
        if width > 1:
            self.root.geometry(f"{width}x{self.root.winfo_reqheight()}")

    # ------------------------------------------------------------------
    # Состояние окна
    # ------------------------------------------------------------------
    def _refresh(self) -> None:
        row_order = self.ignore_row_order_var.get()
        self._row_order_hint.configure(
            text="Строки ищутся по содержимому, их порядок в файлах может отличаться"
            if row_order
            else "Строки сравниваются по номеру: первая с первой, вторая со второй"
        )
        keys_enabled = row_order and not self._running
        self.key_columns_entry.state(["!disabled"] if keys_enabled else ["disabled"])

        target = self._report_target()
        self.report_label.set_text(
            str(target) if target else f"Рядом с первым файлом: {DEFAULT_REPORT_NAME}"
        )

        ready = bool(self.file1_card.path and self.file2_card.path) and not self._running
        self.compare_button.state(["!disabled"] if ready else ["disabled"])

    def _report_target(self) -> Path | None:
        """Куда сохранить отчёт: выбранный вручную путь или свободное имя рядом с первым файлом"""
        if self._manual_report is not None:
            return self._manual_report
        if not self.file1_card.path:
            return None
        return next_free_path(Path(self.file1_card.path).parent)

    def _on_files_changed(self) -> None:
        if self.file1_card.path != self._file1_seen:
            # Ручной путь отчёта относится к прежней паре файлов
            self._file1_seen = self.file1_card.path
            self._manual_report = None
        if not self._running:
            self.result_panel.grid_remove()
        self._refresh()
        self._fit_height()

    def _initial_dir(self) -> str:
        """Папка для диалога выбора: рядом с уже выбранными или последними файлами"""
        candidates = [self.file1_card.path, self.file2_card.path, *self.config.recent_files]
        for candidate in candidates:
            if candidate and Path(candidate).parent.is_dir():
                return str(Path(candidate).parent)
        return str(Path.home())

    def _set_running(self, running: bool) -> None:
        self._running = running
        for widget in self._lockable:
            widget.state(["disabled"] if running else ["!disabled"])
        if running:
            self.result_panel.grid_remove()
            self.progress.begin()
            self.progress.grid()
            self.compare_button.configure(text="Сравнение…")
        else:
            self.progress.finish()
            self.progress.grid_remove()
            self.compare_button.configure(text="Сравнить")
        self._refresh()
        self._fit_height()

    # ------------------------------------------------------------------
    # Действия пользователя
    # ------------------------------------------------------------------
    def swap_files(self) -> None:
        first, second = self.file1_card.path, self.file2_card.path
        self.file1_card.set_path(second, notify=False)
        self.file2_card.set_path(first, notify=False)
        self._on_files_changed()

    def set_report_path(self, path: str) -> None:
        """Отчёт в заданный файл (например, из --output)"""
        self._manual_report = Path(path)
        self._refresh()

    def choose_report_path(self) -> None:
        target = self._report_target() or Path(self._initial_dir()) / DEFAULT_REPORT_NAME
        filename = filedialog.asksaveasfilename(
            parent=self.root,
            title="Куда сохранить отчёт",
            initialdir=str(target.parent),
            initialfile=target.name,
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx"), ("HTML", "*.html"), ("CSV", "*.csv")],
        )
        if filename:
            self._manual_report = Path(filename)
            self._refresh()

    def start_comparison(self, _event: Any = None) -> None:
        if self._running or not (self.file1_card.path and self.file2_card.path):
            return
        file1, file2 = Path(self.file1_card.path), Path(self.file2_card.path)
        missing = next((path for path in (file1, file2) if not path.is_file()), None)
        if missing is not None:
            self._show_failure("Файл не найден", str(missing))
            return

        output = self._report_target()
        options = self._collect_options()
        self._remember_options()
        self._last_pair = (file1, file2)
        self._set_running(True)

        reporter = ProgressReporter()
        reporter.add_observer(_QueueObserver(self._events))
        threading.Thread(
            target=self._compare_in_background,
            args=(file1, file2, output, reporter, options),
            daemon=True,
        ).start()
        self.root.after(POLL_INTERVAL_MS, self._poll_events)

    def open_report(self) -> None:
        path = self._last_report
        if path is None or not path.exists():
            self._show_failure("Отчёт не найден", "Сравните файлы ещё раз, чтобы создать отчёт.")
            return
        try:
            if sys.platform == "win32":
                os.startfile(path)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(path)])
        except OSError as e:
            self._show_failure("Не удалось открыть отчёт", str(e))

    def show_report_in_folder(self) -> None:
        path = self._last_report
        if path is None or not path.exists():
            self._show_failure("Отчёт не найден", "Сравните файлы ещё раз, чтобы создать отчёт.")
            return
        if sys.platform == "win32":
            subprocess.Popen(f'explorer /select,"{path}"')
        else:
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(path.parent)])

    def show_help(self) -> None:
        """Справка: одно окно; повторное нажатие «?» / F1 поднимает его"""
        if self._help is not None and self._help.winfo_exists():
            self._help.lift()
            self._help.focus_set()
            return
        self._help = HelpWindow(self.root, self.theme, self.dnd_enabled)

    # ------------------------------------------------------------------
    # Сравнение
    # ------------------------------------------------------------------
    def _collect_options(self) -> dict[str, Any]:
        """Опции читаются в главном потоке: tkinter-переменные нельзя трогать из фонового"""
        ignore_row_order = self.ignore_row_order_var.get()
        comparison: dict[str, Any] = {
            "ignore_case": self.ignore_case_var.get(),
            "ignore_whitespace": self.ignore_whitespace_var.get(),
            "ignore_row_order": ignore_row_order,
        }
        key_columns = parse_key_columns(self.key_columns_var.get())
        if ignore_row_order and key_columns:
            comparison["key_columns"] = key_columns
        loader = {"on_bad_lines": "skip"} if self.skip_bad_lines_var.get() else {}
        return {
            "comparator_name": "advanced",
            "comparison_options": comparison,
            "loader_options": loader,
            "format_options": {"full_data_sheets": self.full_data_sheets_var.get()},
        }

    def _remember_options(self) -> None:
        settings = self.config.comparison
        settings.ignore_case = self.ignore_case_var.get()
        settings.ignore_whitespace = self.ignore_whitespace_var.get()
        settings.ignore_row_order = self.ignore_row_order_var.get()
        settings.key_columns = parse_key_columns(self.key_columns_var.get())
        settings.full_data_sheets = self.full_data_sheets_var.get()

    def _compare_in_background(
        self,
        file1: Path,
        file2: Path,
        output: Path,
        reporter: ProgressReporter,
        options: dict[str, Any],
    ) -> None:
        try:
            result = self.strategy.execute(
                file1, file2, output, progress_reporter=reporter, **options
            )
        except Exception as e:
            self.logger.error(f"Ошибка сравнения: {e}")
            self._events.put(("failed", e))
            return
        self._events.put(("done", (result, output)))

    def _poll_events(self) -> None:
        try:
            while True:
                kind, payload = self._events.get_nowait()
                if kind == "progress":
                    current, _total, message = payload
                    self.progress.update_progress(int(current), str(message))
                elif kind == "done":
                    self._on_comparison_done(*payload)
                elif kind == "failed":
                    self._on_comparison_failed(payload)
        except queue.Empty:
            pass
        if self._running:
            self.root.after(POLL_INTERVAL_MS, self._poll_events)

    def _on_comparison_done(self, result: Any, output: Path) -> None:
        self._last_report = output
        self._set_running(False)
        self.result_panel.show_summary(summarize(result.metadata))
        self._show_result_panel()
        if self._last_pair is not None:
            for path in self._last_pair:
                self.config.add_recent_file(str(path))

    def _on_comparison_failed(self, error: Exception) -> None:
        self._set_running(False)
        self._show_failure("Не удалось сравнить файлы", _friendly_error(error))

    def _show_failure(self, headline: str, message: str) -> None:
        self.result_panel.show_error(headline, message)
        self._show_result_panel()

    def _show_result_panel(self) -> None:
        self.result_panel.grid()
        self._fit_height()

    # ------------------------------------------------------------------
    # Перетаскивание файлов
    # ------------------------------------------------------------------
    def _enable_drag_and_drop(self) -> bool:
        try:
            from tkinterdnd2 import TkinterDnD

            TkinterDnD.require(self.root)
        except Exception as e:  # окно работает и без перетаскивания
            self.logger.warning(f"Перетаскивание файлов недоступно: {e}")
            return False
        return True

    def _register_drop_targets(self) -> None:
        if not self.dnd_enabled:
            return
        from tkinterdnd2 import DND_FILES

        for card in (self.file1_card, self.file2_card):
            card.drop_target_register(DND_FILES)
            card.dnd_bind("<<DropEnter>>", lambda _e, c=card: self._on_drag_over(c, True))
            card.dnd_bind("<<DropLeave>>", lambda _e, c=card: self._on_drag_over(c, False))
            card.dnd_bind("<<Drop>>", lambda e, c=card: self._on_drop(e, c))
        # Сам Tk-корень не умеет принимать файлы (tkinterdnd2 расширяет только
        # виджеты), поэтому файлы мимо карточек принимает рамка на всё окно
        self._main_frame.drop_target_register(DND_FILES)
        self._main_frame.dnd_bind("<<Drop>>", lambda e: self._on_drop(e, None))

    def _on_drag_over(self, card: FileCard, active: bool) -> str:
        if self._running:
            return DROP_REFUSE
        card.set_drop_highlight(active)
        return DROP_COPY

    def _on_drop(self, event: Any, card: FileCard | None) -> str:
        if card is not None:
            card.set_drop_highlight(False)
        if self._running:
            return DROP_REFUSE
        paths = self._supported_files(self.root.tk.splitlist(event.data))
        if not paths:
            self._show_failure(
                "Этот файл не подходит", "Нужен файл Excel или CSV: .xlsx, .xls, .csv, .tsv, .txt"
            )
            return DROP_COPY
        if card is not None:
            other = self.file2_card if card is self.file1_card else self.file1_card
            card.set_path(paths[0], notify=False)
            if len(paths) > 1:
                other.set_path(paths[1], notify=False)
        else:
            self._place_dropped(paths)
        self._on_files_changed()
        return DROP_COPY

    def _place_dropped(self, paths: list[str]) -> None:
        """Два файла — в обе карточки по порядку; один — в первую пустую"""
        if len(paths) > 1:
            self.file1_card.set_path(paths[0], notify=False)
            self.file2_card.set_path(paths[1], notify=False)
        elif not self.file1_card.path:
            self.file1_card.set_path(paths[0], notify=False)
        else:
            self.file2_card.set_path(paths[0], notify=False)

    def _supported_files(self, raw_paths: Any) -> list[str]:
        extensions = set(self.engine.get_supported_file_extensions())
        return [
            str(path)
            for path in (Path(p) for p in raw_paths if p)
            if path.is_file() and path.suffix.lower() in extensions
        ]

    # ------------------------------------------------------------------
    def run(self) -> None:
        """Запускает главный цикл приложения"""
        try:
            self.logger.info("Запуск главного цикла приложения")
            self.root.mainloop()
        finally:
            # Сохраняем конфигурацию при выходе
            if self.config.auto_save_config:
                self.config.save_config()
            self.logger.info("Приложение завершено")


def _friendly_error(error: Exception) -> str:
    """Понятное сообщение: занятый отчёт — частая причина ошибки записи"""
    if isinstance(error, FileLoadError):
        return str(error)
    current: BaseException | None = error
    while current is not None:
        if isinstance(current, PermissionError):
            return (
                "Файл отчёта открыт в другой программе. Закройте его в Excel "
                "и нажмите «Сравнить» ещё раз."
            )
        current = current.__cause__ or current.__context__
    return str(error)
