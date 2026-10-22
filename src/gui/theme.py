"""
Оформление окна: тема Windows 11 (sv-ttk), светлая или тёмная по настройке Windows
"""

import ctypes
import logging
import sys
import tkinter as tk
from dataclasses import dataclass, field
from tkinter import ttk

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Palette:
    """Цвета поверх темы sv-ttk; фон совпадает с фоном окна темы"""

    name: str
    bg: str
    fg: str
    muted: str
    accent: str
    success: str
    success_bg: str
    success_line: str
    error: str
    error_bg: str
    error_line: str
    on_status: str  # цвет галочки/крестика внутри круглого значка


LIGHT = Palette(
    name="light",
    bg="#fafafa",
    fg="#1c1c1c",
    muted="#5f5f5f",
    accent="#005fb8",
    success="#0f7b0f",
    success_bg="#dff6dd",
    success_line="#c9e8c5",
    error="#c42b1c",
    error_bg="#fde7e9",
    error_line="#f3cbd0",
    on_status="#ffffff",
)

DARK = Palette(
    name="dark",
    bg="#1c1c1c",
    fg="#fafafa",
    muted="#b8b8b8",
    accent="#57c8ff",
    success="#6ccb5f",
    success_bg="#393d1b",
    success_line="#4a5024",
    error="#ff99a4",
    error_bg="#442726",
    error_line="#5a3534",
    on_status="#000000",
)


@dataclass
class Theme:
    """Палитра и картинки, созданные для конкретного окна"""

    palette: Palette
    status_icons: dict[str, tk.PhotoImage] = field(default_factory=dict)
    images: list[tk.PhotoImage] = field(default_factory=list)  # держим ссылки от сборщика мусора


def windows_prefers_dark() -> bool:
    """Тёмная ли тема приложений в настройках Windows"""
    if sys.platform != "win32":
        return False
    try:
        import winreg

        key = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as handle:
            value, _ = winreg.QueryValueEx(handle, "AppsUseLightTheme")
        return int(value) == 0
    except OSError:
        return False


def apply_theme(root: tk.Tk) -> Theme:
    """Включает тему sv-ttk и настраивает стили окна"""
    palette = DARK if windows_prefers_dark() else LIGHT
    try:
        import sv_ttk

        sv_ttk.set_theme(palette.name, root)
    except Exception as e:  # тема не загрузилась — окно остаётся рабочим
        logger.warning(f"Тема sv-ttk недоступна, используется стандартная: {e}")
        ttk.Style(root).theme_use("clam")
        palette = LIGHT

    root.configure(background=palette.bg)
    theme = Theme(palette=palette)
    _configure_styles(root, theme)
    return theme


def paint_label(label: ttk.Label) -> None:
    """Переносит цвета стиля надписи в саму надпись.

    В теме sv-ttk цвета из стиля для ttk.Label не действуют: при изменении
    стилей sv-ttk вызывает tk_setPalette, и тот прописывает надписям с
    незаданными цветами цвета палитры. Цвета, заданные самому виджету, он не
    трогает, поэтому копируем их из стиля — стиль остаётся единственным местом,
    где цвета определены.
    """
    style_name = str(label.cget("style")) or "TLabel"
    style = ttk.Style(label)
    colors = {key: style.lookup(style_name, key) for key in ("background", "foreground")}
    label.configure(**{key: value for key, value in colors.items() if value})


def paint_labels(widget: tk.Misc) -> None:
    """paint_label для всех надписей внутри widget"""
    for child in widget.winfo_children():
        if isinstance(child, ttk.Label):
            paint_label(child)
        paint_labels(child)


def set_title_bar_theme(root: tk.Misc, dark: bool) -> None:
    """Тёмный или светлый заголовок окна Windows 10/11 (DWM): главного или диалога"""
    if sys.platform != "win32":
        return
    try:
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        value = ctypes.c_int(1 if dark else 0)
        # 20 — DWMWA_USE_IMMERSIVE_DARK_MODE, 19 — тот же атрибут в Windows 10 до 20H1
        for attribute in (20, 19):
            result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)
            )
            if result == 0:
                break
    except Exception as e:
        logger.debug(f"Не удалось настроить заголовок окна: {e}")


def make_app_icon(root: tk.Tk, theme: Theme) -> tk.PhotoImage:
    """Иконка окна: две таблицы на синем скруглённом квадрате"""
    accent = LIGHT.accent
    icon = rounded_image(root, fill=accent, line=accent, bg="", radius=7, size=32)
    for left in (6, 17):
        icon.put("#ffffff", to=(left, 8, left + 9, 24))
        for top in (12, 16, 20):
            icon.put(accent, to=(left + 1, top, left + 8, top + 1))
    theme.images.append(icon)
    return icon


def rounded_image(
    root: tk.Tk, fill: str, line: str, bg: str, radius: int, size: int, width: int = 1
) -> tk.PhotoImage:
    """Скруглённый прямоугольник со сглаженными краями.

    ``bg`` — цвет, с которым смешиваются края; пустая строка — края прозрачные.
    """
    image = tk.PhotoImage(master=root, width=size, height=size)
    fill_rgb, line_rgb = _rgb(fill), _rgb(line)
    bg_rgb = _rgb(bg) if bg else None
    rows = []
    for y in range(size):
        row = []
        for x in range(size):
            outer, inner = _coverage(x, y, size, radius, width)
            row.append(_pixel(outer, inner, fill_rgb, line_rgb, bg_rgb))
        rows.append("{" + " ".join(row) + "}")
    image.put(" ".join(rows))
    if bg_rgb is None:
        for y in range(size):
            for x in range(size):
                if _coverage(x, y, size, radius, width)[0] < 0.5:
                    image.transparency_set(x, y, True)
    return image


def _configure_styles(root: tk.Tk, theme: Theme) -> None:
    style = ttk.Style(root)
    p = theme.palette

    style.configure("Title.TLabel", font="SunValleySubtitleFont")
    style.configure("Muted.TLabel", foreground=p.muted)
    style.configure("Caption.TLabel", foreground=p.muted, font="SunValleyCaptionFont")
    style.configure("Strong.TLabel", font="SunValleyBodyStrongFont")
    style.configure("Big.Accent.TButton", font="SunValleyBodyStrongFont", padding=(12, 8))
    style.configure("Expander.Toolbutton", anchor="w", padding=(10, 6))

    _panel_style(root, style, theme, "DropCard", "Drop.Card.TFrame", p.bg, p.accent, width=2)
    for kind, fill, line, color in (
        ("Success", p.success_bg, p.success_line, p.success),
        ("Error", p.error_bg, p.error_line, p.error),
    ):
        _panel_style(root, style, theme, f"{kind}Panel", f"{kind}.TFrame", fill, line)
        style.configure(f"{kind}Flat.TFrame", background=fill)
        style.configure(f"{kind}.TLabel", background=fill, foreground=p.fg)
        style.configure(
            f"{kind}Title.TLabel", background=fill, foreground=color, font="SunValleyBodyStrongFont"
        )
        style.configure(f"{kind}.TButton", background=fill)
        style.configure(f"{kind}.Accent.TButton", background=fill)
        style.configure(f"{kind}Icon.TLabel", background=fill, foreground=p.on_status)
        icon = rounded_image(root, fill=color, line=color, bg=fill, radius=11, size=22)
        theme.images.append(icon)
        theme.status_icons[kind] = icon


def _panel_style(
    root: tk.Tk,
    style: ttk.Style,
    theme: Theme,
    element: str,
    style_name: str,
    fill: str,
    line: str,
    width: int = 1,
) -> None:
    """Стиль рамки-плашки из скруглённой картинки (как Card.TFrame в sv-ttk)"""
    image = rounded_image(
        root, fill=fill, line=line, bg=theme.palette.bg, radius=6, size=24, width=width
    )
    theme.images.append(image)
    # padding=4 — как у Card.TFrame, чтобы содержимое не сдвигалось при смене стиля
    style.element_create(f"{element}.field", "image", image, border=8, padding=4, sticky="nsew")
    style.layout(
        style_name,
        [
            (
                f"{element}.field",
                {
                    "sticky": "nsew",
                    "children": [(f"{element}.padding", {"sticky": "nsew", "expand": 1})],
                },
            )
        ],
    )


def _coverage(x: int, y: int, size: int, radius: int, width: int) -> tuple[float, float]:
    """Доля пикселя внутри внешнего и внутреннего контура (сглаживание 4×4)"""
    steps = 4
    outer = inner = 0
    for sy in range(steps):
        for sx in range(steps):
            px = x + (sx + 0.5) / steps
            py = y + (sy + 0.5) / steps
            if _inside(px, py, 0, size, radius):
                outer += 1
                if _inside(px, py, width, size - width, max(radius - width, 0)):
                    inner += 1
    total = steps * steps
    return outer / total, inner / total


def _inside(px: float, py: float, low: float, high: float, radius: float) -> bool:
    dx = max(low + radius - px, 0.0, px - (high - radius))
    dy = max(low + radius - py, 0.0, py - (high - radius))
    return dx * dx + dy * dy <= radius * radius and low <= px <= high and low <= py <= high


def _pixel(
    outer: float,
    inner: float,
    fill: tuple[int, int, int],
    line: tuple[int, int, int],
    bg: tuple[int, int, int] | None,
) -> str:
    base = bg if bg is not None else line
    border = outer - inner
    rest = 1.0 - outer if bg is not None else 0.0
    if bg is None and outer > 0:
        border, inner_share = border / outer, inner / outer
    else:
        inner_share = inner
    channels = [
        round(f * inner_share + li * border + b * rest)
        for f, li, b in zip(fill, line, base, strict=True)
    ]
    red, green, blue = (min(255, max(0, c)) for c in channels)
    return f"#{red:02x}{green:02x}{blue:02x}"


def _rgb(color: str) -> tuple[int, int, int]:
    value = color.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
