"""
HTML форматтер для вывода результатов сравнения
"""

import logging
import math
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar

import pandas as pd

from ..core.exceptions import ApplicationError
from ..core.interfaces import ComparisonResult, IOutputFormatter

#: Default rows-per-page threshold before the report switches to a
#: paginated structure (one index + N page files).
DEFAULT_HTML_PAGE_SIZE: int = 1000

#: Default highlight color for cell differences in single-page HTML.
DEFAULT_HIGHLIGHT_COLOR: str = "FFFF00"


class HTMLOutputFormatter(IOutputFormatter):
    """Форматтер для вывода результатов сравнения в HTML"""

    SUPPORTED_FORMATS: ClassVar[list[str]] = [".html", ".htm"]

    def __init__(self, config: Any = None) -> None:
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)

        # Настройки стилей
        self.highlight_color = (
            getattr(config.comparison, "highlight_color", DEFAULT_HIGHLIGHT_COLOR)
            if config
            else DEFAULT_HIGHLIGHT_COLOR
        )

        # Настройки пагинации для больших таблиц
        self.page_size = (
            getattr(config.comparison, "max_differences_display", DEFAULT_HTML_PAGE_SIZE)
            if config
            else DEFAULT_HTML_PAGE_SIZE
        )
        self.enable_pagination = True

    def format(
        self, result: ComparisonResult, output_path: Path, **options: Any
    ) -> None:
        """Форматирует и сохраняет результат сравнения в HTML"""
        try:
            self.logger.info(f"Создание HTML отчета: {output_path}")

            # Определяем размеры данных
            total_rows = len(result.file1_data)
            self.logger.info(f"Размер данных: {total_rows} строк")

            # Для маленьких таблиц используем прямой подход
            if total_rows <= self.page_size or not self.enable_pagination:
                self.logger.info("Используем прямую генерацию HTML (без пагинации)")
                html_content = self._generate_html_report(result, options)

                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(html_content)
            else:
                # Для больших таблиц используем потоковую запись и пагинацию
                self.logger.info(
                    f"Используем потоковую генерацию HTML с пагинацией (размер страницы: {self.page_size})"
                )
                self._generate_paginated_html_report(result, output_path, options)

            self.logger.info(f"HTML отчет успешно создан: {output_path}")

        except Exception as e:
            self.logger.error(f"Ошибка создания HTML отчета: {e}", exc_info=True)
            raise ApplicationError(f"Не удалось создать HTML отчет: {e}") from e

    def get_supported_formats(self) -> list[str]:
        """Возвращает список поддерживаемых форматов"""
        return self.SUPPORTED_FORMATS.copy()

    def _generate_paginated_html_report(
        self, result: ComparisonResult, output_path: Path, options: dict[str, Any]
    ) -> None:
        """Генерирует многостраничный HTML отчет для больших таблиц"""
        file1_name = options.get("file1_name", "Файл 1")
        file2_name = options.get("file2_name", "Файл 2")
        total_rows = len(result.file1_data)

        # Создаем временную директорию для многостраничного отчета
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)

            # Вычисляем количество страниц
            num_pages = math.ceil(total_rows / self.page_size)
            self.logger.info(f"Создание {num_pages} страниц HTML отчета")

            # Создаем главную страницу
            index_html = temp_dir_path / "index.html"
            self._generate_index_page(index_html, result, file1_name, file2_name, num_pages)

            # Создаем страницы с данными
            for page_num in range(num_pages):
                start_row = page_num * self.page_size
                end_row = min(start_row + self.page_size, total_rows)

                # Извлекаем фрагмент данных для текущей страницы
                page_data1 = result.file1_data.iloc[start_row:end_row].copy()
                page_data2 = result.file2_data.iloc[start_row:end_row].copy()
                page_mask = result.differences_mask.iloc[start_row:end_row].copy()

                # Создаем временный результат для этой страницы
                page_result = ComparisonResult(
                    differences_mask=page_mask,
                    file1_data=page_data1,
                    file2_data=page_data2,
                    metadata=result.metadata.copy(),
                )

                # Обновляем метаданные для отображения информации о странице
                page_result.metadata["page_info"] = {
                    "current_page": page_num + 1,
                    "total_pages": num_pages,
                    "start_row": start_row + 1,
                    "end_row": end_row,
                    "total_rows": total_rows,
                }

                # Генерируем HTML для текущей страницы
                page_options = options.copy()
                page_options["page_num"] = page_num + 1
                page_options["num_pages"] = num_pages

                page_html = temp_dir_path / f"page_{page_num + 1}.html"
                with open(page_html, "w", encoding="utf-8") as f:
                    page_content = self._generate_html_report(page_result, page_options)
                    f.write(page_content)

                self.logger.info(f"Создана страница {page_num + 1} из {num_pages}")

            # Копируем файлы из временной директории в конечную
            if output_path.suffix.lower() in [".html", ".htm"]:
                # Если указан один файл, то это будет главная страница
                shutil.copy2(index_html, output_path)

                # Другие страницы помещаем рядом
                output_dir = output_path.parent
                base_name = output_path.stem

                for page_num in range(num_pages):
                    src_page = temp_dir_path / f"page_{page_num + 1}.html"
                    dst_page = output_dir / f"{base_name}_page_{page_num + 1}.html"
                    shutil.copy2(src_page, dst_page)
            else:
                # Если указана директория, копируем всё туда
                if not output_path.exists():
                    output_path.mkdir(parents=True)

                for html_file in temp_dir_path.glob("*.html"):
                    shutil.copy2(html_file, output_path / html_file.name)

    def _generate_index_page(
        self,
        output_file: Path,
        result: ComparisonResult,
        file1_name: str,
        file2_name: str,
        num_pages: int,
    ) -> None:
        """Генерирует главную страницу для многостраничного отчета"""
        html_parts = [
            self._generate_html_header(),
            self._generate_summary_section(result, file1_name, file2_name),
            self._generate_statistics_section(result),
            self._generate_pagination_section(num_pages),
            self._generate_html_footer(),
        ]

        with open(output_file, "w", encoding="utf-8") as f:
            f.write("\n".join(html_parts))

    def _generate_pagination_section(self, num_pages: int) -> str:
        """Генерирует секцию с навигацией по страницам"""
        links = []
        for page_num in range(1, num_pages + 1):
            links.append(
                f'<a href="page_{page_num}.html" class="page-link">Страница {page_num}</a>'
            )

        return f"""
        <section class="pagination">
            <h2>📄 Навигация по страницам</h2>
            <div class="pagination-links">
                {" | ".join(links)}
            </div>
        </section>
        """

    def _generate_html_report(self, result: ComparisonResult, options: dict[str, Any]) -> str:
        """Генерирует HTML отчет"""

        file1_name = options.get("file1_name", "Файл 1")
        file2_name = options.get("file2_name", "Файл 2")

        # Проверяем, является ли это частью многостраничного отчета
        is_paged_report = "page_num" in options and "num_pages" in options

        html_parts = [
            self._generate_html_header(),
            self._generate_summary_section(result, file1_name, file2_name),
        ]

        # Добавляем информацию о странице, если это часть многостраничного отчета
        if is_paged_report:
            page_info = result.metadata.get("page_info", {})
            page_html = f"""
            <div class="page-info">
                <p>Страница {page_info.get("current_page", 1)} из {page_info.get("total_pages", 1)}</p>
                <p>Строки {page_info.get("start_row", 1)}-{page_info.get("end_row", self.page_size)} из {page_info.get("total_rows", 0)}</p>
                <p><a href="index.html">← Вернуться к сводке</a></p>
            </div>
            """
            html_parts.append(page_html)
        else:
            # Если это одностраничный отчет, добавляем секцию статистики
            html_parts.append(self._generate_statistics_section(result))

        # Добавляем секцию сравнения данных
        html_parts.append(self._generate_data_comparison_section(result, file1_name, file2_name))

        # Добавляем навигацию по страницам, если это часть многостраничного отчета
        if is_paged_report:
            page_num = options["page_num"]
            num_pages = options["num_pages"]

            navigation = f"""
            <div class="page-navigation">
                {f'<a href="page_{page_num - 1}.html" class="nav-link">← Предыдущая</a>' if page_num > 1 else ""}
                <a href="index.html" class="nav-link">На главную</a>
                {f'<a href="page_{page_num + 1}.html" class="nav-link">Следующая →</a>' if page_num < num_pages else ""}
            </div>
            """
            html_parts.append(navigation)

        # Добавляем подвал
        html_parts.append(self._generate_html_footer())

        return "\n".join(html_parts)

    def _generate_html_header(self) -> str:
        """Генерирует заголовок HTML документа"""
        return f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Отчет сравнения файлов</title>
    <style>
        {self._get_css_styles()}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>📊 Отчет сравнения файлов</h1>
            <p class="timestamp">Создано: {datetime.now().strftime("%d.%m.%Y %H:%M:%S")}</p>
        </header>"""

    def _generate_summary_section(
        self, result: ComparisonResult, file1_name: str, file2_name: str
    ) -> str:
        """Генерирует секцию с общей информацией"""

        metadata = result.metadata

        return f"""
        <section class="summary">
            <h2>📋 Общая информация</h2>
            <div class="info-grid">
                <div class="info-item">
                    <label>Первый файл:</label>
                    <span>{file1_name}</span>
                </div>
                <div class="info-item">
                    <label>Второй файл:</label>
                    <span>{file2_name}</span>
                </div>
                <div class="info-item">
                    <label>Размер данных:</label>
                    <span>{metadata.get("shape", "N/A")}</span>
                </div>
                <div class="info-item">
                    <label>Тип сравнения:</label>
                    <span>{metadata.get("comparison_type", "basic")}</span>
                </div>
            </div>
        </section>
        """

    def _generate_statistics_section(self, result: ComparisonResult) -> str:
        """Генерирует секцию со статистикой"""

        metadata = result.metadata
        total_cells = metadata.get("total_cells", 0)
        different_cells = metadata.get("different_cells", 0)
        similarity = metadata.get("similarity_percentage", 0)

        # Определяем цвет для индикатора схожести
        if similarity >= 90:
            similarity_class = "high"
        elif similarity >= 70:
            similarity_class = "medium"
        else:
            similarity_class = "low"

        stats_html = f"""
        <section class="statistics">
            <h2>📈 Статистика сравнения</h2>
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-value">{total_cells}</div>
                    <div class="stat-label">Всего ячеек</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{different_cells}</div>
                    <div class="stat-label">Различий</div>
                </div>
                <div class="stat-card similarity-{similarity_class}">
                    <div class="stat-value">{similarity:.1f}%</div>
                    <div class="stat-label">Схожесть</div>
                </div>
        """

        # Добавляем дополнительную статистику если есть
        if "fuzzy_matches" in metadata:
            stats_html += f"""
                <div class="stat-card">
                    <div class="stat-value">{metadata["fuzzy_matches"]}</div>
                    <div class="stat-label">Нечетких совпадений</div>
                </div>
            """

        stats_html += """
            </div>
        """

        # Добавляем детальную статистику по столбцам
        if hasattr(result, "differences_mask"):
            column_stats = self._generate_column_statistics(result.differences_mask)
            stats_html += f"""
            <div class="column-stats">
                <h3>Различия по столбцам</h3>
                {column_stats}
            </div>
            """

        stats_html += "</section>"

        return stats_html

    def _generate_column_statistics(self, differences_mask: pd.DataFrame) -> str:
        """Генерирует статистику по столбцам"""

        column_stats = []
        total_rows = len(differences_mask)

        for col in differences_mask.columns:
            diff_count = differences_mask[col].sum()
            diff_percentage = (diff_count / total_rows) * 100 if total_rows > 0 else 0

            if diff_count > 0:
                column_stats.append(f"""
                <div class="column-stat">
                    <span class="column-name">{col}</span>
                    <span class="column-count">{diff_count} ({diff_percentage:.1f}%)</span>
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: {diff_percentage}%"></div>
                    </div>
                </div>
                """)

        if not column_stats:
            return "<p>Различий по столбцам не найдено</p>"

        return "\n".join(column_stats)

    def _generate_data_comparison_section(
        self, result: ComparisonResult, file1_name: str, file2_name: str
    ) -> str:
        """Генерирует секцию с данными сравнения"""

        # Создаем таблицы с подсветкой различий
        table1_html = self._create_data_table(
            result.file1_data, result.differences_mask, f"Данные: {file1_name}"
        )
        table2_html = self._create_data_table(
            result.file2_data, result.differences_mask, f"Данные: {file2_name}"
        )

        return f"""
        <section class="data-comparison">
            <h2>📄 Сравнение данных</h2>
            <div class="tables-container">
                <div class="table-wrapper">
                    {table1_html}
                </div>
                <div class="table-wrapper">
                    {table2_html}
                </div>
            </div>
        </section>
        """

    def _create_data_table(self, data: pd.DataFrame, mask: pd.DataFrame, title: str) -> str:
        """Создает HTML таблицу с данными и подсветкой"""

        # Ограничиваем количество отображаемых строк для производительности
        max_rows = self.page_size

        if len(data) > max_rows and "page_info" not in data.attrs:
            display_data = data.head(max_rows)
            display_mask = mask.head(max_rows)
            truncated_note = (
                f"<p class='truncated-note'>⚠️ Показаны первые {max_rows} строк из {len(data)}</p>"
            )
        else:
            display_data = data
            display_mask = mask
            truncated_note = ""

        # Создаем заголовок таблицы
        table_html = f"""
        <div class="data-table">
            <h3>{title}</h3>
            {truncated_note}
            <div class="table-scroll">
                <table>
                    <thead>
                        <tr>
                            <th>#</th>
        """

        # Добавляем заголовки столбцов
        for col in display_data.columns:
            table_html += f"<th>{col}</th>"

        table_html += "</tr></thead><tbody>"

        # Добавляем строки данных
        for idx, (row_idx, row) in enumerate(display_data.iterrows()):
            table_html += f"<tr><td class='row-index'>{idx + 1}</td>"

            for col in display_data.columns:
                value = row[col]
                is_different = (
                    display_mask.at[row_idx, col] if row_idx in display_mask.index else False
                )

                # Форматируем значение
                if pd.isna(value):
                    formatted_value = '<span class="null-value">NULL</span>'
                else:
                    formatted_value = str(value)

                # Применяем стиль для различающихся ячеек
                cell_class = "different" if is_different else ""
                table_html += f'<td class="{cell_class}">{formatted_value}</td>'

            table_html += "</tr>"

        table_html += "</tbody></table></div></div>"

        return table_html

    def _generate_html_footer(self) -> str:
        """Генерирует подвал HTML документа"""
        return """
        <footer>
            <p>Создано с помощью Excel Comparator v1.0</p>
        </footer>
    </div>
    <script>
        // Добавляем интерактивность
        document.addEventListener('DOMContentLoaded', function() {
            // Подсветка строк при наведении
            const rows = document.querySelectorAll('tbody tr');
            rows.forEach(row => {
                row.addEventListener('mouseenter', function() {
                    this.style.backgroundColor = '#f0f8ff';
                });
                row.addEventListener('mouseleave', function() {
                    this.style.backgroundColor = '';
                });
            });
        });
    </script>
</body>
</html>
        """

    def _get_css_styles(self) -> str:
        """Возвращает CSS стили для HTML отчета"""
        return f"""
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            background-color: #f5f5f5;
        }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
            background-color: white;
            min-height: 100vh;
        }}
        
        header {{
            text-align: center;
            margin-bottom: 30px;
            padding: 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border-radius: 10px;
        }}
        
        header h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
        }}
        
        .timestamp {{
            opacity: 0.9;
            font-size: 0.9em;
        }}
        
        section {{
            margin-bottom: 30px;
            padding: 20px;
            background-color: white;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        
        h2 {{
            color: #4a5568;
            margin-bottom: 20px;
            font-size: 1.8em;
        }}
        
        h3 {{
            color: #5a6c7d;
            margin-bottom: 15px;
            font-size: 1.3em;
        }}
        
        .info-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 15px;
        }}
        
        .info-item {{
            display: flex;
            justify-content: space-between;
            padding: 10px;
            background-color: #f8f9fa;
            border-radius: 5px;
        }}
        
        .info-item label {{
            font-weight: bold;
            color: #495057;
        }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }}
        
        .stat-card {{
            text-align: center;
            padding: 20px;
            background: linear-gradient(135deg, #74b9ff 0%, #0984e3 100%);
            color: white;
            border-radius: 10px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        }}
        
        .stat-card.similarity-high {{
            background: linear-gradient(135deg, #00b894 0%, #00a085 100%);
        }}
        
        .stat-card.similarity-medium {{
            background: linear-gradient(135deg, #fdcb6e 0%, #e17055 100%);
        }}
        
        .stat-card.similarity-low {{
            background: linear-gradient(135deg, #fd79a8 0%, #e84393 100%);
        }}
        
        .stat-value {{
            font-size: 2.5em;
            font-weight: bold;
            margin-bottom: 5px;
        }}
        
        .stat-label {{
            font-size: 0.9em;
            opacity: 0.9;
        }}
        
        .column-stats {{
            margin-top: 20px;
        }}
        
        .column-stat {{
            display: flex;
            align-items: center;
            margin-bottom: 10px;
            padding: 8px;
            background-color: #f8f9fa;
            border-radius: 5px;
        }}
        
        .column-name {{
            flex: 1;
            font-weight: bold;
            color: #495057;
        }}
        
        .column-count {{
            margin-right: 10px;
            color: #6c757d;
        }}
        
        .progress-bar {{
            width: 100px;
            height: 8px;
            background-color: #e9ecef;
            border-radius: 4px;
            overflow: hidden;
        }}
        
        .progress-fill {{
            height: 100%;
            background: linear-gradient(90deg, #fd79a8, #e84393);
            transition: width 0.3s ease;
        }}
        
        .tables-container {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }}
        
        @media (max-width: 1200px) {{
            .tables-container {{
                grid-template-columns: 1fr;
            }}
        }}
        
        .table-wrapper {{
            background-color: #f8f9fa;
            border-radius: 8px;
            padding: 15px;
        }}
        
        .data-table h3 {{
            margin-bottom: 10px;
            color: #495057;
        }}
        
        .truncated-note {{
            color: #856404;
            background-color: #fff3cd;
            padding: 8px;
            border-radius: 4px;
            margin-bottom: 10px;
            font-size: 0.9em;
        }}
        
        .table-scroll {{
            overflow-x: auto;
            max-height: 600px;
            overflow-y: auto;
            border: 1px solid #dee2e6;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.9em;
        }}
        
        thead {{
            position: sticky;
            top: 0;
            background-color: #f8f9fa;
            z-index: 10;
        }}
        
        th, td {{
            padding: 8px 12px;
            text-align: left;
            border-bottom: 1px solid #dee2e6;
        }}
        
        th {{
            background-color: #e9ecef;
            color: #495057;
            font-weight: bold;
            user-select: none;
        }}
        
        .row-index {{
            font-weight: bold;
            background-color: #f8f9fa;
            position: sticky;
            left: 0;
            z-index: 5;
        }}
        
        td.different {{
            background-color: #{self.highlight_color};
        }}
        
        .null-value {{
            color: #6c757d;
            font-style: italic;
        }}
        
        footer {{
            text-align: center;
            padding: 20px;
            color: #6c757d;
            font-size: 0.9em;
        }}
        
        /* Стили для пагинации */
        .pagination {{
            text-align: center;
        }}
        
        .pagination-links {{
            display: flex;
            flex-wrap: wrap;
            justify-content: center;
            gap: 10px;
            margin-top: 20px;
        }}
        
        .page-link {{
            display: inline-block;
            padding: 8px 15px;
            background-color: #f8f9fa;
            color: #495057;
            text-decoration: none;
            border-radius: 5px;
            transition: all 0.3s ease;
        }}
        
        .page-link:hover {{
            background-color: #e9ecef;
            transform: translateY(-2px);
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }}
        
        .page-info {{
            background-color: #e9ecef;
            padding: 10px;
            margin-bottom: 20px;
            border-radius: 5px;
            text-align: center;
        }}
        
        .page-navigation {{
            display: flex;
            justify-content: center;
            gap: 20px;
            margin: 20px 0;
        }}
        
        .nav-link {{
            display: inline-block;
            padding: 10px 20px;
            background-color: #6c5ce7;
            color: white;
            text-decoration: none;
            border-radius: 5px;
            transition: all 0.3s ease;
        }}
        
        .nav-link:hover {{
            background-color: #5341d6;
            transform: translateY(-2px);
            box-shadow: 0 3px 10px rgba(0,0,0,0.2);
        }}
        """
