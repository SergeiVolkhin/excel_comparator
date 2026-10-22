"""
Окно справки: как сравнить, что в отчёте и что значат настройки — коротко и по делу
"""

import tkinter as tk
from tkinter import ttk

from .theme import Theme, paint_labels, rounded_image, set_title_bar_theme

#: Ширина текста описаний в половине окна и в разделе «Настройки», пикселей
TEXT_WIDTH = 330
SETTINGS_TEXT_WIDTH = 350

#: Неразрывный пробел: «100 000» и «Сумма: 1000» не разрываются переносом
NBSP = " "

#: Листы отчёта: название и что на нём
REPORT_SHEETS = [
    (
        "Сводка",
        "Итог в цифрах: сколько строк совпало, изменилось и есть только в одном файле.",
    ),
    (
        "Расхождения",
        "Только строки с отличиями: изменённая строка — из обоих файлов, "
        f"изменения подсвечены и подписаны: «Сумма:{NBSP}1000{NBSP}→{NBSP}100{NBSP}(-900)».",
    ),
    (
        "Листы с данными",
        f"Оба файла целиком с подсветкой — для таблиц до 100{NBSP}000 строк.",
    ),
]

#: Настройки: название и что делает
SETTINGS = [
    (
        "Порядок строк не важен",
        "Строки ищутся по содержимому. Выключите — сравнение пойдёт строка за строкой.",
    ),
    (
        "Ключевые столбцы",
        "Например: dt, idUser. По ним строки сопоставляются точно.",
    ),
    (
        "Регистр и пробелы",
        "С этими галочками «ABC», «abc» и « abc » считаются одинаковыми.",
    ),
    (
        "Повреждённые строки CSV",
        "Пропускаются, а не останавливают сравнение.",
    ),
    (
        "Полные листы данных",
        f"Листы с данными и для таблиц больше 100{NBSP}000 строк. Отчёт пишется дольше.",
    ),
    (
        "Куда сохранить отчёт",
        "По умолчанию — рядом с первым файлом. Старые отчёты не перезаписываются.",
    ),
]

#: Клавиши внизу окна
KEYS_HINT = "Enter — сравнить   ·   F1 — справка   ·   Esc — закрыть"


class HelpWindow(tk.Toplevel):
    """Справка в оформлении главного окна; закрывается «Понятно», Enter или Esc"""

    def __init__(self, parent: tk.Tk, theme: Theme, drag_and_drop: bool):
        super().__init__(parent)
        self.withdraw()
        self.title("Справка")
        self.configure(background=theme.palette.bg)
        self.resizable(False, False)
        self.transient(parent)
        self._parent = parent
        self._theme = theme

        style = ttk.Style(self)
        style.configure(
            "HelpBadge.TLabel",
            foreground=theme.palette.on_status,
            font=("Segoe UI", 9, "bold"),
        )
        # Карточки sv-ttk залиты цветом фона окна, поэтому края значка
        # сглаживаются по фону палитры
        accent = theme.palette.accent
        self._badge = rounded_image(
            self, fill=accent, line=accent, bg=theme.palette.bg, radius=11, size=22
        )

        self._build(drag_and_drop)
        paint_labels(self)

        self.protocol("WM_DELETE_WINDOW", self.close)
        for key in ("<Escape>", "<Return>", "<KP_Enter>"):
            self.bind(key, lambda _event: self.close())
        self._show()

    def close(self) -> None:
        self.grab_release()
        self.destroy()

    # ------------------------------------------------------------------
    # Содержимое
    # ------------------------------------------------------------------
    def _build(self, drag_and_drop: bool) -> None:
        body = ttk.Frame(self, padding=(24, 20, 24, 20))
        body.grid(row=0, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1, uniform="half")
        body.columnconfigure(1, weight=1, uniform="half")

        header = ttk.Frame(body)
        header.grid(row=0, column=0, columnspan=2, sticky="ew")
        ttk.Label(header, text="Справка", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text="Программа сравнивает две таблицы Excel или CSV "
            "и сохраняет отчёт с найденными различиями.",
            style="Muted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))

        section, steps = self._section(body, "Как сравнить")
        section.grid(row=1, column=0, sticky="nsew", padx=(0, 8), pady=(18, 0))
        steps.columnconfigure(1, weight=1)
        for number, (title, text) in enumerate(self._steps(drag_and_drop), start=1):
            self._step(steps, number, title, text)

        section, sheets = self._section(body, "Что в отчёте")
        section.grid(row=1, column=1, sticky="nsew", padx=(8, 0), pady=(18, 0))
        sheets.columnconfigure(0, weight=1)
        for row, (title, text) in enumerate(REPORT_SHEETS):
            self._item(sheets, row, 0, title, text)

        section, settings = self._section(body, "Настройки")
        section.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(16, 0))
        settings.columnconfigure((0, 1), weight=1, uniform="settings")
        for index, (title, text) in enumerate(SETTINGS):
            row, column = divmod(index, 2)
            self._item(settings, row, column, title, text, width=SETTINGS_TEXT_WIDTH)

        footer = ttk.Frame(body)
        footer.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(18, 0))
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, text=KEYS_HINT, style="Caption.TLabel").grid(row=0, column=0, sticky="w")
        self._ok = ttk.Button(
            footer, text="Понятно", style="Accent.TButton", width=12, command=self.close
        )
        self._ok.grid(row=0, column=1, sticky="e")

    @staticmethod
    def _steps(drag_and_drop: bool) -> list[tuple[str, str]]:
        choose = (
            "Перетащите их в окно или нажмите «Выбрать…»."
            if drag_and_drop
            else "Нажмите «Выбрать…» на обеих карточках."
        )
        return [
            ("Выберите два файла", f"{choose} Кнопка ⇄ меняет их местами."),
            ("Нажмите «Сравнить»", "Или клавишу Enter. Под кнопкой виден ход сравнения."),
            (
                "Посмотрите итог",
                "Зелёная плашка — совпадают, красная — есть расхождения. "
                "«Открыть отчёт» откроет его в Excel.",
            ),
        ]

    @staticmethod
    def _section(parent: ttk.Frame, title: str) -> tuple[ttk.Frame, ttk.Frame]:
        """Раздел: заголовок и карточка под ним; возвращает (раздел, карточку)"""
        frame = ttk.Frame(parent)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)
        ttk.Label(frame, text=title, style="Strong.TLabel").grid(row=0, column=0, sticky="w")
        card = ttk.Frame(frame, style="Card.TFrame", padding=(16, 12))
        card.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
        return frame, card

    def _step(self, card: ttk.Frame, number: int, title: str, text: str) -> None:
        """Шаг: синий кружок с номером, название и пояснение"""
        row = (number - 1) * 2
        ttk.Label(
            card, image=self._badge, text=str(number), compound="center", style="HelpBadge.TLabel"
        ).grid(row=row, column=0, rowspan=2, sticky="n", padx=(0, 12), pady=(1, 0))
        ttk.Label(card, text=title, style="Strong.TLabel").grid(row=row, column=1, sticky="w")
        ttk.Label(
            card, text=text, style="Muted.TLabel", wraplength=TEXT_WIDTH, justify="left"
        ).grid(row=row + 1, column=1, sticky="w", pady=(0, 0 if number == 3 else 10))

    @staticmethod
    def _item(
        card: ttk.Frame, row: int, column: int, title: str, text: str, width: int = TEXT_WIDTH
    ) -> None:
        """Пункт: название и пояснение под ним"""
        cell = ttk.Frame(card)
        cell.grid(
            row=row,
            column=column,
            sticky="nw",
            padx=(0, 16) if column == 0 else (16, 0),
            pady=(0 if row == 0 else 10, 0),
        )
        ttk.Label(cell, text=title, style="Strong.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(cell, text=text, style="Muted.TLabel", wraplength=width, justify="left").grid(
            row=1, column=0, sticky="w"
        )

    # ------------------------------------------------------------------
    # Показ
    # ------------------------------------------------------------------
    def _show(self) -> None:
        """По центру над главным окном, модально, с кнопкой «Понятно» в фокусе"""
        self.update_idletasks()
        width, height = self.winfo_reqwidth(), self.winfo_reqheight()
        parent = self._parent
        x = parent.winfo_rootx() + (parent.winfo_width() - width) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - height) // 3
        x = min(max(x, 0), max(self.winfo_screenwidth() - width, 0))
        y = min(max(y, 0), max(self.winfo_screenheight() - height - 48, 0))
        self.geometry(f"+{x}+{y}")
        dark = self._theme.palette.name == "dark"
        set_title_bar_theme(self, dark)
        self.deiconify()
        set_title_bar_theme(self, dark)
        self.grab_set()
        self._ok.focus_set()
