"""
Виджеты главного окна: карточка файла, раскрывающийся блок, прогресс и панель результата
"""

import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog, ttk
from tkinter import font as tkfont

from ..core.result_summary import ResultSummary, human_size
from .theme import Theme, paint_label

#: Типы файлов в диалоге выбора
FILE_TYPES = [
    ("Таблицы Excel и CSV", "*.xlsx *.xls *.csv *.tsv *.txt"),
    ("Excel", "*.xlsx *.xls"),
    ("CSV", "*.csv *.tsv *.txt"),
    ("Все файлы", "*.*"),
]

ELLIPSIS = "…"


def elide_middle(text: str, font: tkfont.Font, max_px: int) -> str:
    """Сокращает текст посередине под ширину: «Процедура Ser…Africa.xlsx»"""
    if max_px <= 0 or font.measure(text) <= max_px:
        return text
    best = ELLIPSIS
    low, high = 0, len(text)
    while low <= high:
        keep = (low + high) // 2
        head, tail = (keep + 1) // 2, keep // 2
        candidate = text[:head] + ELLIPSIS + (text[len(text) - tail :] if tail else "")
        if font.measure(candidate) <= max_px:
            best, low = candidate, keep + 1
        else:
            high = keep - 1
    return best


class ElidedLabel(ttk.Label):
    """Надпись, которая сокращает длинный текст посередине под ширину ячейки"""

    def __init__(self, parent, text: str = "", **kwargs):
        # width=1: ширину задаёт сетка, а не длина текста — иначе длинное имя
        # файла растягивало бы окно
        super().__init__(parent, width=1, **kwargs)
        self._full_text = text
        self.bind("<Configure>", self._fit)
        self._fit()

    def set_text(self, text: str) -> None:
        self._full_text = text
        self._fit()

    def set_style(self, style: str) -> None:
        self.configure(style=style)
        paint_label(self)
        self._fit()

    def _fit(self, _event=None) -> None:
        width = self.winfo_width()
        if width <= 1:
            self.configure(text=self._full_text)
            return
        self.configure(text=elide_middle(self._full_text, self._font(), width - 4))

    def _font(self) -> tkfont.Font:
        style = str(self.cget("style")) or "TLabel"
        name = ttk.Style(self).lookup(style, "font") or "TkDefaultFont"
        try:
            return tkfont.nametofont(name)
        except tk.TclError:
            return tkfont.Font(root=self, font=name)


class FileCard(ttk.Frame):
    """Карточка файла: имя, папка и размер, кнопка «Выбрать…»; принимает перетаскивание"""

    def __init__(
        self,
        parent,
        title: str,
        on_change: Callable[[], None],
        initial_dir: Callable[[], str],
        drop_hint: bool,
    ):
        super().__init__(parent, style="Card.TFrame", padding=(14, 12))
        self._path = ""
        self._on_change = on_change
        self._initial_dir = initial_dir
        self._empty_text = "Перетащите файл сюда" if drop_hint else "Файл не выбран"
        self.columnconfigure(0, weight=1)

        ttk.Label(self, text=title, style="Caption.TLabel").grid(row=0, column=0, sticky="w")
        self._name = ElidedLabel(self, style="Muted.TLabel")
        self._name.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        self._meta = ElidedLabel(self, style="Caption.TLabel")
        self._meta.grid(row=2, column=0, sticky="ew")
        self.browse_button = ttk.Button(self, text="Выбрать…", command=self.browse)
        self.browse_button.grid(row=3, column=0, sticky="e", pady=(12, 0))
        self._render()

    @property
    def path(self) -> str:
        return self._path

    def set_path(self, path: str, notify: bool = True) -> None:
        self._path = str(Path(path)) if path else ""
        self._render()
        if notify:
            self._on_change()

    def browse(self) -> None:
        filename = filedialog.askopenfilename(
            parent=self,
            title="Выберите файл",
            initialdir=self._initial_dir(),
            filetypes=FILE_TYPES,
        )
        if filename:
            self.set_path(filename)

    def set_drop_highlight(self, active: bool) -> None:
        self.configure(style="Drop.Card.TFrame" if active else "Card.TFrame")

    def _render(self) -> None:
        if not self._path:
            self._name.set_style("Muted.TLabel")
            self._name.set_text(self._empty_text)
            self._meta.set_text("Excel или CSV")
            return
        path = Path(self._path)
        size = human_size(path.stat().st_size) if path.is_file() else "файл не найден"
        self._name.set_style("Strong.TLabel")
        self._name.set_text(path.name)
        self._meta.set_text(f"{path.parent} · {size}")


class Expander(ttk.Frame):
    """Раскрывающийся блок, например «Дополнительно»"""

    def __init__(self, parent, title: str, on_toggle: Callable[[], None]):
        super().__init__(parent, style="Card.TFrame", padding=4)
        self.columnconfigure(0, weight=1)
        self._title = title
        self._on_toggle = on_toggle
        self._open = False
        self._header = ttk.Button(self, style="Expander.Toolbutton", command=self.toggle)
        self._header.grid(row=0, column=0, sticky="ew")
        self.body = ttk.Frame(self, padding=(10, 4, 10, 10))
        self.body.columnconfigure(0, weight=1)
        self._render()

    @property
    def is_open(self) -> bool:
        return self._open

    def toggle(self) -> None:
        self._open = not self._open
        self._render()
        self._on_toggle()

    def _render(self) -> None:
        self._header.configure(text=("▾   " if self._open else "▸   ") + self._title)
        if self._open:
            self.body.grid(row=1, column=0, sticky="ew")
        else:
            self.body.grid_remove()


class ProgressRow(ttk.Frame):
    """Полоса прогресса и строка состояния под кнопкой «Сравнить»"""

    def __init__(self, parent):
        super().__init__(parent)
        self.columnconfigure(0, weight=1)
        self._bar = ttk.Progressbar(self, mode="indeterminate", maximum=100)
        self._bar.grid(row=0, column=0, sticky="ew")
        self._text = ttk.Label(self, style="Caption.TLabel")
        self._text.grid(row=1, column=0, sticky="w", pady=(4, 0))

    def begin(self) -> None:
        """Пока файлы загружаются, точного процента нет — бегущая полоса"""
        self._bar.configure(mode="indeterminate", value=0)
        self._bar.start(15)
        self._text.configure(text="Загрузка файлов…")

    def update_progress(self, percent: int, message: str) -> None:
        if percent <= 0:
            return
        self._bar.stop()
        self._bar.configure(mode="determinate", value=percent)
        self._text.configure(text=f"{message.rstrip('.')} · {percent} %")

    def finish(self) -> None:
        self._bar.stop()


class ResultPanel(ttk.Frame):
    """Итог сравнения: цветная плашка со значком, заголовком, цифрами и кнопками"""

    def __init__(
        self,
        parent,
        theme: Theme,
        on_open_report: Callable[[], None],
        on_show_folder: Callable[[], None],
    ):
        super().__init__(parent, style="Success.TFrame", padding=(16, 14))
        self._theme = theme
        self.columnconfigure(1, weight=1)

        self._icon = ttk.Label(self, compound="center", font=("Segoe UI", 9, "bold"))
        self._icon.grid(row=0, column=0, rowspan=2, sticky="n", padx=(0, 12), pady=(1, 0))
        self._title = ttk.Label(self)
        self._title.grid(row=0, column=1, sticky="w")
        self._details = ttk.Label(self, justify="left")
        self._details.grid(row=1, column=1, sticky="ew", pady=(2, 0))

        self._actions = ttk.Frame(self)
        self._actions.grid(row=2, column=1, sticky="w", pady=(12, 0))
        self._open = ttk.Button(self._actions, text="Открыть отчёт", command=on_open_report)
        self._open.grid(row=0, column=0)
        self._folder = ttk.Button(self._actions, text="Показать в папке", command=on_show_folder)
        self._folder.grid(row=0, column=1, padx=(8, 0))

        self.bind("<Configure>", self._wrap_details)

    def show_summary(self, summary: ResultSummary) -> None:
        kind = "Success" if summary.ok else "Error"
        self._apply(kind, "✓" if summary.ok else "✕", summary.headline, summary.details)
        self._actions.grid()

    def show_error(self, headline: str, message: str) -> None:
        self._apply("Error", "!", headline, message)
        self._actions.grid_remove()

    def _apply(self, kind: str, glyph: str, headline: str, details: str) -> None:
        self.configure(style=f"{kind}.TFrame")
        icon = self._theme.status_icons.get(kind)
        self._icon.configure(style=f"{kind}Icon.TLabel", image=icon or "", text=glyph)
        self._title.configure(style=f"{kind}Title.TLabel", text=headline)
        self._details.configure(style=f"{kind}.TLabel", text=details)
        for label in (self._icon, self._title, self._details):
            paint_label(label)
        self._actions.configure(style=f"{kind}Flat.TFrame")
        self._open.configure(style=f"{kind}.Accent.TButton")
        self._folder.configure(style=f"{kind}.TButton")

    def _wrap_details(self, event) -> None:
        self._details.configure(wraplength=max(event.width - 80, 200))
