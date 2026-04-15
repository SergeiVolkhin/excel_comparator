"""
Виджеты для использования в GUI приложения
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import threading
import logging
from typing import List, Optional, Callable, Tuple


class FileSelector(ttk.Frame):
    """Виджет для выбора файла с поддержкой недавних файлов"""
    
    def __init__(self, parent, label_text: str, supported_extensions: List[str], recent_files: List[str] = None):
        super().__init__(parent)
        
        self.supported_extensions = supported_extensions
        self.recent_files = recent_files or []
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Создаем виджеты
        self.label = ttk.Label(self, text=label_text)
        self.label.grid(row=0, column=0, sticky=tk.W, padx=(0, 10))
        
        self.path_var = tk.StringVar()
        self.path_entry = ttk.Entry(self, textvariable=self.path_var, width=50)
        self.path_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(0, 5))
        
        self.browse_button = ttk.Button(
            self, 
            text="Обзор...", 
            command=self._select_file
        )
        self.browse_button.grid(row=0, column=2, padx=(0, 5))
    
    def _select_file(self) -> None:
        """Открывает диалог выбора файла"""
        # Формируем список типов файлов
        filetypes = []
        if '.xlsx' in self.supported_extensions or '.xls' in self.supported_extensions:
            filetypes.append(("Excel файлы", "*.xlsx *.xls"))
        
        # Добавляем остальные поддерживаемые типы
        for ext in self.supported_extensions:
            if ext not in ['.xlsx', '.xls']:
                filetypes.append((f"{ext.upper()} файлы", f"*{ext}"))
        
        filetypes.append(("Все файлы", "*.*"))
        
        filename = filedialog.askopenfilename(
            title="Выберите файл",
            filetypes=filetypes
        )
        
        if filename:
            self.path_var.set(filename)
    
    def _show_recent_menu(self) -> None:
        """Показывает меню недавних файлов"""
        if not self.recent_files:
            return
        
        menu = tk.Menu(self, tearoff=0)
        
        for file_path in self.recent_files[:10]:
            if Path(file_path).exists():
                file_name = Path(file_path).name
                menu.add_command(
                    label=file_name,
                    command=lambda f=file_path: self.set_path(f)
                )
        
        if menu.index(tk.END) is None:
            menu.add_command(label="(Нет доступных файлов)", state="disabled")
        
        # Показываем меню под кнопкой
        try:
            x = self.recent_button.winfo_rootx()
            y = self.recent_button.winfo_rooty() + self.recent_button.winfo_height()
            menu.post(x, y)
        except Exception as e:
            self.logger.error(f"Ошибка отображения меню: {e}")
    
    def get_path(self) -> str:
        """Возвращает выбранный путь"""
        return self.path_var.get().strip()
    
    def set_path(self, path: str) -> None:
        """Устанавливает путь"""
        self.path_var.set(path)
    
    def clear(self) -> None:
        """Очищает выбранный путь"""
        self.path_var.set("")
    
    def validate(self) -> bool:
        """Проверяет корректность выбранного файла"""
        path = self.get_path()
        if not path:
            return False
        
        file_path = Path(path)
        if not file_path.exists():
            return False
        
        return file_path.suffix.lower() in self.supported_extensions


class CenteredDialog:
    """Базовый класс для диалогов с центрированием"""
    
    def __init__(self, parent, title: str = "Диалог", size: Tuple[int, int] = (400, 300), 
                 resizable: Tuple[bool, bool] = (False, False), modal: bool = True):
        """
        Инициализирует базовый диалог
        
        Args:
            parent: Родительское окно
            title: Заголовок диалога
            size: Кортеж (ширина, высота)
            resizable: Кортеж (resize_x, resize_y)
            modal: Делать ли диалог модальным
        """
        self.parent = parent
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Создаем диалоговое окно
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(title)
        self.dialog.geometry(f"{size[0]}x{size[1]}")
        self.dialog.resizable(resizable[0], resizable[1])
        
        # Делаем диалог модальным при необходимости
        if modal:
            self.dialog.transient(parent)
            self.dialog.grab_set()
        
        # Центрируем диалог
        self._center_dialog()
    
    def _center_dialog(self) -> None:
        """Центрирует диалог относительно родительского окна"""
        self.dialog.update_idletasks()
        
        parent_x = self.parent.winfo_rootx()
        parent_y = self.parent.winfo_rooty()
        parent_width = self.parent.winfo_width()
        parent_height = self.parent.winfo_height()
        
        dialog_width = self.dialog.winfo_width()
        dialog_height = self.dialog.winfo_height()
        
        x = parent_x + (parent_width - dialog_width) // 2
        y = parent_y + (parent_height - dialog_height) // 2
        
        self.dialog.geometry(f"+{x}+{y}")
    
    def show(self) -> None:
        """Показывает диалог и блокирует до закрытия"""
        self.parent.wait_window(self.dialog)
    
    def close(self) -> None:
        """Закрывает диалог"""
        try:
            self.dialog.grab_release()
            self.dialog.destroy()
        except Exception as e:
            self.logger.error(f"Ошибка при закрытии диалога: {e}")


class ProgressDialog(CenteredDialog):
    """Диалог прогресса выполнения операции"""
    
    def __init__(self, parent, title: str = "Выполнение операции"):
        super().__init__(parent, title=title, size=(400, 150), resizable=(False, False), modal=True)
        
        # Переменные состояния
        self._is_closed = False
        
        self._setup_widgets()
    
    def _setup_widgets(self) -> None:
        """Настраивает виджеты диалога"""
        main_frame = ttk.Frame(self.dialog, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Метка с сообщением
        self.message_var = tk.StringVar(value="Инициализация...")
        message_label = ttk.Label(
            main_frame, 
            textvariable=self.message_var,
            font=('Arial', 10)
        )
        message_label.pack(pady=(0, 10))
        
        # Прогресс-бар
        self.progress = ttk.Progressbar(
            main_frame,
            mode='determinate',
            length=350
        )
        self.progress.pack(pady=(0, 10))
        
        # Метка с процентами
        self.percent_var = tk.StringVar(value="0%")
        percent_label = ttk.Label(main_frame, textvariable=self.percent_var)
        percent_label.pack()
        
        # Кнопка отмены (пока скрытая)
        self.cancel_button = ttk.Button(
            main_frame,
            text="Отмена",
            command=self._cancel_operation
        )
        # self.cancel_button.pack(pady=(10, 0))  # Раскомментировать для добавления кнопки отмены
    
    def update_progress(self, current: int, total: int, message: str = "") -> None:
        """Обновляет прогресс"""
        if self._is_closed:
            return
        
        def _update():
            if self._is_closed:
                return
            
            percentage = (current / total) * 100 if total > 0 else 0
            
            self.progress['value'] = percentage
            self.percent_var.set(f"{percentage:.1f}%")
            
            if message:
                self.message_var.set(message)
            
            self.dialog.update()
        
        # Выполняем обновление в главном потоке
        if threading.current_thread() is threading.main_thread():
            _update()
        else:
            self.dialog.after(0, _update)
    
    def close(self) -> None:
        """Закрывает диалог"""
        if self._is_closed:
            return
        
        def _close():
            self._is_closed = True
            # Исправляем ошибку с вызовом super().close()
            # Вместо него используем напрямую метод родительского класса
            CenteredDialog.close(self)
        
        if threading.current_thread() is threading.main_thread():
            _close()
        else:
            self.dialog.after(0, _close)
    
    def _cancel_operation(self) -> None:
        """Отменяет операцию"""
        # Здесь можно добавить логику отмены операции
        self.close()


class SettingsDialog(CenteredDialog):
    """Диалог настроек приложения"""
    
    def __init__(self, parent, config):
        super().__init__(parent, title="Настройки", size=(500, 400), resizable=(True, True), modal=True)
        self.config = config
        
        self._setup_widgets()
    
    def _setup_widgets(self) -> None:
        """Настраивает виджеты диалога"""
        notebook = ttk.Notebook(self.dialog)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Вкладка "Сравнение"
        comparison_frame = ttk.Frame(notebook)
        notebook.add(comparison_frame, text="Сравнение")
        self._setup_comparison_tab(comparison_frame)
        
        # Вкладка "Интерфейс"
        ui_frame = ttk.Frame(notebook)
        notebook.add(ui_frame, text="Интерфейс")
        self._setup_ui_tab(ui_frame)
        
        # Кнопки
        button_frame = ttk.Frame(self.dialog)
        button_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        ttk.Button(
            button_frame,
            text="OK",
            command=self._save_and_close
        ).pack(side=tk.RIGHT, padx=(5, 0))
        
        ttk.Button(
            button_frame,
            text="Отмена",
            command=self.close
        ).pack(side=tk.RIGHT)
        
        ttk.Button(
            button_frame,
            text="Применить",
            command=self._apply_settings
        ).pack(side=tk.RIGHT, padx=(0, 5))
    
    def _setup_comparison_tab(self, parent) -> None:
        """Настраивает вкладку параметров сравнения"""
        # Основные опции
        options_frame = ttk.LabelFrame(parent, text="Основные опции", padding="10")
        options_frame.pack(fill=tk.X, padx=10, pady=10)
        
        self.ignore_case_var = tk.BooleanVar(value=self.config.comparison.ignore_case)
        ttk.Checkbutton(
            options_frame,
            text="Игнорировать регистр символов",
            variable=self.ignore_case_var
        ).pack(anchor=tk.W)
        
        self.ignore_whitespace_var = tk.BooleanVar(value=self.config.comparison.ignore_whitespace)
        ttk.Checkbutton(
            options_frame,
            text="Игнорировать пробелы в начале и конце",
            variable=self.ignore_whitespace_var
        ).pack(anchor=tk.W)
        
        self.enable_list_analysis_var = tk.BooleanVar(value=self.config.comparison.enable_list_analysis)
        ttk.Checkbutton(
            options_frame,
            text="Включить анализ списков",
            variable=self.enable_list_analysis_var
        ).pack(anchor=tk.W)
        
        # Настройки подсветки
        highlight_frame = ttk.LabelFrame(parent, text="Подсветка различий", padding="10")
        highlight_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Label(highlight_frame, text="Цвет подсветки:").pack(anchor=tk.W)
        
        color_frame = ttk.Frame(highlight_frame)
        color_frame.pack(fill=tk.X, pady=5)
        
        self.highlight_color_var = tk.StringVar(value=self.config.comparison.highlight_color)
        color_entry = ttk.Entry(color_frame, textvariable=self.highlight_color_var, width=10)
        color_entry.pack(side=tk.LEFT)
        
        # Цветные кнопки для быстрого выбора
        colors = ["FFFF00", "FFB6C1", "98FB98", "87CEEB", "DDA0DD"]
        for color in colors:
            btn = tk.Button(
                color_frame,
                bg=f"#{color}",
                width=3,
                height=1,
                command=lambda c=color: self.highlight_color_var.set(c)
            )
            btn.pack(side=tk.LEFT, padx=2)
        
        # Разделитель списков
        ttk.Label(highlight_frame, text="Разделитель для анализа списков:").pack(anchor=tk.W, pady=(10, 0))
        
        self.list_separator_var = tk.StringVar(value=self.config.comparison.list_separator)
        ttk.Entry(
            highlight_frame, 
            textvariable=self.list_separator_var, 
            width=5
        ).pack(anchor=tk.W)
    
    def _setup_ui_tab(self, parent) -> None:
        """Настраивает вкладку интерфейса"""
        # Размер окна
        size_frame = ttk.LabelFrame(parent, text="Размер окна", padding="10")
        size_frame.pack(fill=tk.X, padx=10, pady=10)
        
        size_grid = ttk.Frame(size_frame)
        size_grid.pack()
        
        ttk.Label(size_grid, text="Ширина:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
        self.window_width_var = tk.IntVar(value=self.config.gui.window_width)
        ttk.Spinbox(
            size_grid,
            from_=600,
            to=1920,
            textvariable=self.window_width_var,
            width=10
        ).grid(row=0, column=1, padx=(0, 20))
        
        ttk.Label(size_grid, text="Высота:").grid(row=0, column=2, sticky=tk.W, padx=(0, 5))
        self.window_height_var = tk.IntVar(value=self.config.gui.window_height)
        ttk.Spinbox(
            size_grid,
            from_=400,
            to=1080,
            textvariable=self.window_height_var,
            width=10
        ).grid(row=0, column=3)
        
        # Шрифт
        font_frame = ttk.LabelFrame(parent, text="Шрифт", padding="10")
        font_frame.pack(fill=tk.X, padx=10, pady=10)
        
        font_grid = ttk.Frame(font_frame)
        font_grid.pack()
        
        ttk.Label(font_grid, text="Семейство:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
        self.font_family_var = tk.StringVar(value=self.config.gui.font_family)
        font_combo = ttk.Combobox(
            font_grid,
            textvariable=self.font_family_var,
            values=["Arial", "Helvetica", "Times", "Courier", "Verdana"],
            state="readonly",
            width=15
        )
        font_combo.grid(row=0, column=1, padx=(0, 20))
        
        ttk.Label(font_grid, text="Размер:").grid(row=0, column=2, sticky=tk.W, padx=(0, 5))
        self.font_size_var = tk.IntVar(value=self.config.gui.font_size)
        ttk.Spinbox(
            font_grid,
            from_=8,
            to=16,
            textvariable=self.font_size_var,
            width=5
        ).grid(row=0, column=3)
        
        # Другие настройки
        other_frame = ttk.LabelFrame(parent, text="Прочее", padding="10")
        other_frame.pack(fill=tk.X, padx=10, pady=10)
        
        self.auto_save_config_var = tk.BooleanVar(value=self.config.auto_save_config)
        ttk.Checkbutton(
            other_frame,
            text="Автоматически сохранять настройки",
            variable=self.auto_save_config_var
        ).pack(anchor=tk.W)
        
        recent_frame = ttk.Frame(other_frame)
        recent_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Label(recent_frame, text="Количество недавних файлов:").pack(side=tk.LEFT)
        self.max_recent_files_var = tk.IntVar(value=self.config.max_recent_files)
        ttk.Spinbox(
            recent_frame,
            from_=5,
            to=20,
            textvariable=self.max_recent_files_var,
            width=5
        ).pack(side=tk.LEFT, padx=(5, 0))
    
    def _apply_settings(self) -> None:
        """Применяет настройки"""
        try:
            # Настройки сравнения
            self.config.comparison.ignore_case = self.ignore_case_var.get()
            self.config.comparison.ignore_whitespace = self.ignore_whitespace_var.get()
            self.config.comparison.enable_list_analysis = self.enable_list_analysis_var.get()
            self.config.comparison.highlight_color = self.highlight_color_var.get()
            self.config.comparison.list_separator = self.list_separator_var.get()
            
            # Настройки интерфейса
            self.config.gui.window_width = self.window_width_var.get()
            self.config.gui.window_height = self.window_height_var.get()
            self.config.gui.font_family = self.font_family_var.get()
            self.config.gui.font_size = self.font_size_var.get()
            
            # Прочие настройки
            self.config.auto_save_config = self.auto_save_config_var.get()
            self.config.max_recent_files = self.max_recent_files_var.get()
            
            # Валидируем и сохраняем конфигурацию
            self.config.validate()
            self.config.save_config()
            
            messagebox.showinfo("Настройки", "Настройки успешно применены")
        except Exception as e:
            self.logger.error(f"Ошибка при применении настроек: {e}")
            messagebox.showerror("Ошибка", f"Не удалось применить настройки: {e}")
    
    def _save_and_close(self) -> None:
        """Сохраняет настройки и закрывает диалог"""
        self._apply_settings()
        self.close()