"""
Главное окно приложения с GUI
"""

import logging
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from ..core.config import AppConfig
from ..core.engine import ComparisonEngine, StandardComparisonStrategy
from ..core.interfaces import IProgressObserver, ProgressReporter
from .widgets import FileSelector, ProgressDialog, SettingsDialog


class ProgressDialogObserver(IProgressObserver):
    """Реализация наблюдателя прогресса для GUI"""

    def __init__(self, progress_dialog: ProgressDialog):
        self.progress_dialog = progress_dialog

    def on_progress(self, current: int, total: int, message: str = "") -> None:
        """Вызывается при обновлении прогресса"""
        self.progress_dialog.update_progress(current, total, message)

    def on_error(self, error: Exception) -> None:
        """Вызывается при возникновении ошибки"""
        self.progress_dialog.close()
        messagebox.showerror("Ошибка", str(error))

    def on_completion(self, message: str = "") -> None:
        """Вызывается при завершении операции"""
        self.progress_dialog.close()
        messagebox.showinfo("Готово", message)


class MainWindow:
    """Главное окно приложения"""

    def __init__(self, config: AppConfig):
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)

        # Создаем движок сравнения
        self.engine = ComparisonEngine(config)
        self.strategy = StandardComparisonStrategy(self.engine)

        # Создаем главное окно
        self.root = tk.Tk()
        self.root.title("Excel Comparator - сравнение файлов")
        self.root.geometry(f"{config.gui.window_width}x{config.gui.window_height}")

        # Настраиваем стиль
        self.style = ttk.Style()
        self.style.theme_use("clam")

        # Инициализируем интерфейс
        self._setup_menu()
        self._setup_widgets()
        self._setup_bindings()

        # Центрируем окно
        self._center_window()

        self.logger.info("Главное окно инициализировано")

    def _setup_menu(self) -> None:
        """Настраивает меню приложения"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        # Меню "Файл"
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Файл", menu=file_menu)
        file_menu.add_command(
            label="Новое сравнение", command=self._new_comparison, accelerator="Ctrl+N"
        )
        file_menu.add_separator()

        # Подменю "Недавние файлы"
        self.recent_menu = tk.Menu(file_menu, tearoff=0)
        file_menu.add_cascade(label="Недавние файлы", menu=self.recent_menu)
        self._update_recent_menu()

        file_menu.add_separator()
        file_menu.add_command(label="Выход", command=self.root.quit, accelerator="Ctrl+Q")

        # Меню "Настройки"
        settings_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Настройки", menu=settings_menu)
        settings_menu.add_command(label="Параметры сравнения...", command=self._show_settings)
        settings_menu.add_command(label="Настройки интерфейса...", command=self._show_ui_settings)
        settings_menu.add_command(label="Сбросить настройки", command=self._reset_settings)

        # Меню "Справка"
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Справка", menu=help_menu)
        help_menu.add_command(label="О программе", command=self._show_about)
        help_menu.add_command(label="Справка", command=self._show_help)

    def _setup_widgets(self) -> None:
        """Настраивает виджеты интерфейса"""
        # Главный фрейм
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Настраиваем растягивание
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)

        # Заголовок
        title_label = ttk.Label(
            main_frame,
            text="Сравнение Excel файлов",
            font=(self.config.gui.font_family, 16, "bold"),
        )
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 20))

        # Селекторы файлов
        self.file1_selector = FileSelector(
            main_frame,
            "Первый файл:",
            self.engine.get_supported_file_extensions(),
            self.config.get_recent_files(),
        )
        self.file1_selector.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)

        self.file2_selector = FileSelector(
            main_frame,
            "Второй файл:",
            self.engine.get_supported_file_extensions(),
            self.config.get_recent_files(),
        )
        self.file2_selector.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)

        # Селектор выходного файла
        ttk.Label(main_frame, text="Сохранить результат как:").grid(
            row=3, column=0, sticky=tk.W, pady=(20, 5)
        )

        output_frame = ttk.Frame(main_frame)
        output_frame.grid(row=4, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        output_frame.columnconfigure(0, weight=1)

        self.output_var = tk.StringVar(value="Сравнение.xlsx")
        self.output_entry = ttk.Entry(output_frame, textvariable=self.output_var)
        self.output_entry.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=(0, 5))

        ttk.Button(output_frame, text="Обзор...", command=self._select_output_file).grid(
            row=0, column=1
        )

        # Опции сравнения
        options_frame = ttk.LabelFrame(main_frame, text="Опции сравнения", padding="10")
        options_frame.grid(row=5, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(20, 10))
        options_frame.columnconfigure(1, weight=1)

        # Тип сравнения
        ttk.Label(options_frame, text="Тип сравнения:").grid(
            row=0, column=0, sticky=tk.W, padx=(0, 10)
        )

        self.comparator_var = tk.StringVar(value="basic")
        comparator_combo = ttk.Combobox(
            options_frame,
            textvariable=self.comparator_var,
            values=self.engine.get_available_comparators(),
            state="readonly",
        )
        comparator_combo.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(0, 10))

        # Чекбоксы для опций
        self.ignore_case_var = tk.BooleanVar(value=self.config.comparison.ignore_case)
        ttk.Checkbutton(
            options_frame, text="Игнорировать регистр", variable=self.ignore_case_var
        ).grid(row=1, column=0, sticky=tk.W, pady=5)

        self.ignore_whitespace_var = tk.BooleanVar(value=self.config.comparison.ignore_whitespace)
        ttk.Checkbutton(
            options_frame, text="Игнорировать пробелы", variable=self.ignore_whitespace_var
        ).grid(row=1, column=1, sticky=tk.W, pady=5)

        # Кнопки управления
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=6, column=0, columnspan=3, pady=(20, 0))

        self.compare_button = ttk.Button(
            button_frame,
            text="Сравнить файлы",
            command=self._start_comparison,
            style="Accent.TButton",
        )
        self.compare_button.pack(side=tk.LEFT, padx=(0, 10))

        ttk.Button(button_frame, text="Очистить", command=self._clear_fields).pack(
            side=tk.LEFT, padx=(0, 10)
        )

        ttk.Button(button_frame, text="Настройки", command=self._show_settings).pack(side=tk.LEFT)

        # Статусная строка
        self.status_var = tk.StringVar(value="Готов к работе")
        status_bar = ttk.Label(
            main_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W
        )
        status_bar.grid(row=7, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(20, 0))

    def _setup_bindings(self) -> None:
        """Настраивает горячие клавиши"""
        self.root.bind("<Control-n>", lambda e: self._new_comparison())
        self.root.bind("<Control-q>", lambda e: self.root.quit())
        self.root.bind("<F1>", lambda e: self._show_help())

    def _center_window(self) -> None:
        """Центрирует окно на экране"""
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def _new_comparison(self) -> None:
        """Начинает новое сравнение"""
        self._clear_fields()
        self.status_var.set("Готов к новому сравнению")

    def _clear_fields(self) -> None:
        """Очищает все поля"""
        self.file1_selector.clear()
        self.file2_selector.clear()
        self.output_var.set("Сравнение.xlsx")
        self.status_var.set("Поля очищены")

    def _select_output_file(self) -> None:
        """Выбирает файл для сохранения результата"""
        filename = filedialog.asksaveasfilename(
            title="Сохранить результат как",
            defaultextension=".xlsx",
            filetypes=[("Excel файлы", "*.xlsx"), ("Все файлы", "*.*")],
        )
        if filename:
            self.output_var.set(filename)

    def _start_comparison(self) -> None:
        """Запускает процесс сравнения в отдельном потоке"""
        # Валидация полей
        file1_path = self.file1_selector.get_path()
        file2_path = self.file2_selector.get_path()
        output_path = self.output_var.get()

        if not all([file1_path, file2_path, output_path]):
            messagebox.showerror("Ошибка", "Заполните все поля!")
            return

        if not Path(file1_path).exists():
            messagebox.showerror("Ошибка", f"Файл не найден: {file1_path}")
            return

        if not Path(file2_path).exists():
            messagebox.showerror("Ошибка", f"Файл не найден: {file2_path}")
            return

        # Отключаем кнопку сравнения
        self.compare_button.config(state="disabled")
        self.status_var.set("Выполняется сравнение...")

        # Создаем диалог прогресса
        progress_dialog = ProgressDialog(self.root, "Сравнение файлов")

        # Создаем прогресс репортер и наблюдателя
        progress_reporter = ProgressReporter()
        progress_observer = ProgressDialogObserver(progress_dialog)
        progress_reporter.add_observer(progress_observer)

        # Запускаем сравнение в отдельном потоке
        thread = threading.Thread(
            target=self._run_comparison,
            args=(file1_path, file2_path, output_path, progress_reporter),
            daemon=True,
        )
        thread.start()

    def _run_comparison(
        self,
        file1_path: str,
        file2_path: str,
        output_path: str,
        progress_reporter: ProgressReporter,
    ) -> None:
        """Выполняет сравнение в отдельном потоке"""
        try:
            # Подготавливаем опции
            options = {
                "comparison_options": {
                    "ignore_case": self.ignore_case_var.get(),
                    "ignore_whitespace": self.ignore_whitespace_var.get(),
                }
            }

            # Выполняем сравнение
            result = self.strategy.execute(
                Path(file1_path),
                Path(file2_path),
                Path(output_path),
                progress_reporter=progress_reporter,
                **options,
            )

            # Добавляем файлы в список недавних
            self.config.add_recent_file(file1_path)
            self.config.add_recent_file(file2_path)
            self._update_recent_menu()

            # Показываем статистику
            self._show_comparison_stats(result)

        except Exception as e:
            progress_reporter.report_error(e)
            self.logger.error(f"Ошибка сравнения: {e}")
        finally:
            # Включаем кнопку сравнения обратно
            self.root.after(0, lambda: self.compare_button.config(state="normal"))
            self.root.after(0, lambda: self.status_var.set("Готов к работе"))

    def _show_comparison_stats(self, result) -> None:
        """Показывает статистику сравнения"""
        stats_text = (
            f"Сравнение завершено!\n\n"
            f"Общее количество ячеек: {result.metadata['total_cells']}\n"
            f"Ячеек с различиями: {result.metadata['different_cells']}\n"
            f"Процент схожести: {result.metadata['similarity_percentage']:.2f}%"
        )

        self.root.after(0, lambda: messagebox.showinfo("Результат сравнения", stats_text))

    def _update_recent_menu(self) -> None:
        """Обновляет меню недавних файлов"""
        self.recent_menu.delete(0, tk.END)

        recent_files = self.config.get_recent_files()
        if not recent_files:
            self.recent_menu.add_command(label="(Пусто)", state="disabled")
        else:
            for file_path in recent_files[:10]:  # Показываем только последние 10
                file_name = Path(file_path).name
                self.recent_menu.add_command(
                    label=file_name, command=lambda f=file_path: self._load_recent_file(f)
                )

    def _load_recent_file(self, file_path: str) -> None:
        """Загружает недавний файл"""
        if Path(file_path).exists():
            # Определяем, в какой селектор загружать
            if not self.file1_selector.get_path():
                self.file1_selector.set_path(file_path)
            elif not self.file2_selector.get_path():
                self.file2_selector.set_path(file_path)
            else:
                # Если оба заполнены, спрашиваем пользователя
                choice = messagebox.askyesno(
                    "Замена файла", "Оба файла уже выбраны. Заменить первый файл?"
                )
                if choice:
                    self.file1_selector.set_path(file_path)
                else:
                    self.file2_selector.set_path(file_path)
        else:
            messagebox.showerror("Ошибка", f"Файл не найден: {file_path}")

    def _show_settings(self) -> None:
        """Показывает диалог настроек"""
        dialog = SettingsDialog(self.root, self.config)
        self.root.wait_window(dialog.dialog)

    def _show_ui_settings(self) -> None:
        """Показывает настройки интерфейса"""
        messagebox.showinfo("Информация", "Настройки интерфейса будут добавлены в следующей версии")

    def _reset_settings(self) -> None:
        """Сбрасывает настройки на значения по умолчанию"""
        confirm = messagebox.askyesno(
            "Сброс настроек",
            "Вы уверены, что хотите сбросить все настройки на значения по умолчанию?",
        )
        if confirm:
            self.config.reset_to_defaults()
            messagebox.showinfo("Сброс настроек", "Настройки сброшены на значения по умолчанию")

    def _show_about(self) -> None:
        """Показывает информацию о программе"""
        about_text = (
            "Excel Comparator v1.0\n\n"
            "Программное обеспечение для сравнения Excel файлов\n\n"
            "Особенности:\n"
            "• Модульная архитектура\n"
            "• Расширяемость через плагины\n"
            "• Поддержка различных форматов\n"
            "• Детальный анализ различий\n\n"
            "© 2025 Volkhin Sergei"
        )
        messagebox.showinfo("О программе", about_text)

    def _show_help(self) -> None:
        """Показывает справку"""
        help_text = (
            "Инструкция по использованию:\n\n"
            "1. Выберите первый файл для сравнения\n"
            "2. Выберите второй файл для сравнения\n"
            "3. Укажите имя файла для сохранения результата\n"
            "4. При необходимости настройте опции сравнения\n"
            "5. Нажмите 'Сравнить файлы'\n\n"
            "Горячие клавиши:\n"
            "Ctrl+N - Новое сравнение\n"
            "Ctrl+Q - Выход\n"
            "F1 - Справка\n\n"
            "Типы сравнения:\n"
            "Basic\n"
            "- Требует одинакового размера таблиц (строки и столбцы)\n"
            "- Требует идентичных имен столбцов в обоих файлах\n"
            "- Выдает ошибку, если структура файлов различается\n\n"
            "Простое сравнение:\n"
            "- Сравнивает данные ячейка к ячейке\n"
            "- Подсвечивает различающиеся ячейки\n"
            "- Выдает статистику различий\n\n"
            "Advanced:\n"
            "- Поддерживает файлы с разным количеством строк\n"
            "- Может работать с файлами, имеющими разные наборы столбцов\n"
            "- Автоматически выравнивает данные для корректного сравнения\n\n"
            "Расширенная аналитика:\n"
            "- Определяет общие столбцы и выполняет сравнение по ним\n"
            "- Показывает, какие данные присутствуют только в одном из файлов\n"
            "- Создает более детальную статистику о структурных различиях\n"
        )
        messagebox.showinfo("Справка", help_text)

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
