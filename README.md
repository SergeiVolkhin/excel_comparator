# 📊 Excel Comparator

> Профессиональное модульное приложение для сравнения Excel файлов с расширяемой архитектурой

## ✨ Особенности

- 🏗️ **Модульная архитектура** - соответствует принципам SOLID
- 🔌 **Расширяемость** - легкое добавление новых компонентов без изменения существующего кода
- 📊 **Множественные форматы** - поддержка Excel, CSV и возможность добавления новых
- 🎯 **Различные алгоритмы сравнения** - точное, нечеткое, числовое, структурное
- 🎨 **Гибкий вывод** - Excel с подсветкой, HTML отчеты, легко добавить новые форматы
- 🖥️ **Современный GUI** - интуитивный интерфейс на tkinter
- ⚙️ **Конфигурируемость** - настройки сохраняются автоматически
- 📝 **Детальное логирование** - полная диагностика процесса сравнения

## 🚀 Быстрый старт

### Установка

```bash
# Клонирование репозитория
git clone https://github.com/your-username/excel-comparator.git
cd excel-comparator

# Установка зависимостей
pip install -r requirements.txt

# Запуск приложения
python main.py
```

### Первое сравнение

1. **Запустите приложение**: `python main.py`
2. **Выберите файлы**: Первый и второй файл для сравнения
3. **Настройте опции**: Выберите тип сравнения и дополнительные параметры
4. **Запустите сравнение**: Нажмите "Сравнить файлы"
5. **Изучите результат**: Откройте созданный отчет

## 📋 Системные требования

- **Python**: **3.11 или выше** (см. `pyproject.toml`, `requires-python = ">=3.11"`)
- **ОС**: Windows, macOS, Linux
- **ОЗУ**: минимум 512 МБ (рекомендуется 2 ГБ для больших файлов;
  с опцией `read_only=True` можно обрабатывать и более крупные —
  см. раздел «Большие файлы»).
- **Дисковое пространство**: 100 МБ

### Установка для разработки

```bash
git clone https://github.com/SergeiVolkhin/excel_comparator.git
cd excel_comparator
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements-dev.txt
pre-commit install   # один раз на клон
```

### Проверки качества

```bash
pytest tests/ -q --ignore=tests/test_benchmarks.py     # unit + property + snapshot
pytest tests/ --cov=src --cov-branch                   # с покрытием (цель ≥ 85%)
ruff check src/ tests/ && ruff format --check src/ tests/
mypy src/                                              # strict режим через pyproject.toml
pytest tests/test_benchmarks.py --benchmark-only       # производительность
```

CI (GitHub Actions) прогоняет те же проверки на Python 3.11 / 3.12 / 3.13
при каждом push и PR в `main`.

## 🚀 Большие файлы

`ExcelFileLoader.load()` принимает опцию `read_only=True`, которая
стримит `.xlsx` через `openpyxl` в потоковом режиме — подходит для
файлов, которые не помещаются в память целиком.

```python
from pathlib import Path
from src.loaders.excel_loader import ExcelFileLoader

loader = ExcelFileLoader()
df = loader.load(Path("huge.xlsx"), read_only=True)
```

Замеры на 10k × 5 xlsx (baseline → после оптимизации):

| Операция                  | Было   | Стало  | Δ     |
|---------------------------|-------:|-------:|------:|
| `ExcelFileLoader.load`    | 193 мс | 164 мс | −15 % |
| `ExcelOutputFormatter`    | 1003 мс| 681 мс | −32 % |
| `engine.compare_files`    | 1397 мс| 1087 мс| −22 % |

Re-run бенчмарков:

```bash
pytest tests/test_benchmarks.py --benchmark-only \
    --benchmark-compare=0001_baseline --benchmark-columns=min,mean,max
```

## 🎯 Режимы сравнения

### 1. Базовое сравнение
Точное побайтовое сравнение данных
```python
# Через API
from src import ComparisonEngine
engine = ComparisonEngine()
result = engine.compare_files(file1, file2, output, comparator_name="basic")
```

### 2. Нечеткое сравнение
Сравнение с учетом схожести текста
```python
# Нечеткое сравнение с порогом 80%
result = engine.compare_files(
    file1, file2, output,
    comparator_name="fuzzy_80",
    comparison_options={'similarity_threshold': 0.8}
)
```

### 3. Числовое сравнение
Сравнение чисел с допустимыми погрешностями
```python
# Числовое сравнение с допусками
result = engine.compare_files(
    file1, file2, output,
    comparator_name="numeric",
    comparison_options={
        'absolute_tolerance': 1e-6,
        'relative_tolerance': 1e-6
    }
)
```

### 4. Структурное сравнение
Анализ структурных различий между файлами
```python
# Структурное сравнение
result = engine.compare_files(file1, file2, output, comparator_name="structural")
```

## 🔧 Архитектура

### Основные компоненты

```
src/
├── core/           # Ядро системы (интерфейсы, движок, конфигурация)
├── loaders/        # Загрузчики файлов (Excel, CSV, ...)
├── comparators/    # Алгоритмы сравнения
├── formatters/     # Форматтеры вывода (Excel, HTML, ...)
├── validators/     # Валидаторы данных
├── analyzers/      # Анализаторы различий
└── gui/           # Графический интерфейс
```

### Принципы дизайна

- **Single Responsibility**: Каждый класс имеет одну ответственность
- **Open/Closed**: Открыт для расширения, закрыт для модификации
- **Dependency Inversion**: Зависимость от абстракций, а не реализаций
- **Interface Segregation**: Специализированные интерфейсы
- **Liskov Substitution**: Все реализации взаимозаменяемы

## 🔌 Расширение функциональности

### Добавление нового загрузчика

```python
from src.core.interfaces import IFileLoader
import pandas as pd

class JSONFileLoader(IFileLoader):
    def can_load(self, file_path: Path) -> bool:
        return file_path.suffix.lower() == '.json'

    def load(self, file_path: Path, **kwargs) -> pd.DataFrame:
        import json
        with open(file_path) as f:
            data = json.load(f)
        return pd.DataFrame(data)

    def get_supported_extensions(self) -> List[str]:
        return ['.json']

# Регистрация в движке
engine.register_file_loader(JSONFileLoader())
```

### Добавление нового компаратора

```python
from src.core.interfaces import IComparator, ComparisonResult

class CustomComparator(IComparator):
    def compare(self, df1: pd.DataFrame, df2: pd.DataFrame, **options) -> ComparisonResult:
        # Ваш алгоритм сравнения
        differences_mask = # ваша логика
        metadata = # ваши метаданные

        return ComparisonResult(differences_mask, df1, df2, metadata)

    def get_name(self) -> str:
        return "Мой компаратор"

# Регистрация в движке
engine.register_comparator("custom", CustomComparator())
```

### Добавление нового форматтера

```python
from src.core.interfaces import IOutputFormatter

class PDFFormatter(IOutputFormatter):
    def format(self, result: ComparisonResult, output_path: Path, **options) -> None:
        # Генерация PDF отчета
        pass

    def get_supported_formats(self) -> List[str]:
        return ['.pdf']

# Регистрация в движке
engine.register_formatter("pdf", PDFFormatter())
```

## ⚙️ Конфигурация

Приложение автоматически создает файл `config.json` с настройками:

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

## 📊 Форматы вывода

### Excel отчет
- 📋 Два листа с исходными данными
- 🎨 Подсветка различающихся ячеек
- 📈 Лист со статистикой и сводкой
- 📝 Столбец с описанием различий

### HTML отчет
- 🌐 Интерактивный веб-интерфейс
- 📊 Графики и диаграммы статистики
- 🎨 Современный дизайн
- 📱 Адаптивная верстка

## 🧪 Тестирование

```bash
# Установка зависимостей для тестирования
pip install pytest pytest-cov

# Запуск тестов
pytest tests/ -v

# Запуск с покрытием кода
pytest tests/ --cov=src --cov-report=html
```

## 📝 Логирование

Приложение ведет подробные логи в файл `excel_comparator.log`:

```python
import logging

# Настройка уровня логирования
logging.getLogger('src').setLevel(logging.DEBUG)

# Просмотр логов в реальном времени
tail -f excel_comparator.log
```

## 🚀 Использование через API

```python
from pathlib import Path
from src import ComparisonEngine, AppConfig

# Создание движка
config = AppConfig()
engine = ComparisonEngine(config)

# Базовое сравнение
result = engine.compare_files(
    file1_path=Path("data1.xlsx"),
    file2_path=Path("data2.xlsx"),
    output_path=Path("comparison_result.xlsx"),
    comparator_name="basic",
    formatter_name="excel"
)

# Получение статистики
print(f"Схожесть: {result.metadata['similarity_percentage']:.1f}%")
print(f"Различий: {result.metadata['different_cells']}")
```

## 📚 Примеры использования

### Пакетное сравнение

```python
import os
from pathlib import Path

def batch_compare(folder1: str, folder2: str, output_folder: str):
    """Сравнение всех файлов в двух папках"""
    engine = ComparisonEngine()

    for file1 in Path(folder1).glob("*.xlsx"):
        file2 = Path(folder2) / file1.name
        if file2.exists():
            output = Path(output_folder) / f"comparison_{file1.stem}.xlsx"

            try:
                result = engine.compare_files(file1, file2, output)
                print(f"✅ {file1.name}: {result.metadata['similarity_percentage']:.1f}% схожести")
            except Exception as e:
                print(f"❌ {file1.name}: {e}")

# Использование
batch_compare("folder1", "folder2", "results")
```

### Настройка расширенного движка

```python
from src.loaders.csv_loader import CSVFileLoader
from src.comparators.advanced_comparator import FuzzyComparator
from src.formatters.html_formatter import HTMLOutputFormatter

def setup_extended_engine():
    """Настройка движка с дополнительными компонентами"""
    engine = ComparisonEngine()

    # Добавляем CSV поддержку
    engine.register_file_loader(CSVFileLoader())

    # Добавляем нечеткое сравнение
    engine.register_comparator("fuzzy", FuzzyComparator(0.85))

    # Добавляем HTML вывод
    engine.register_formatter("html", HTMLOutputFormatter())

    return engine

engine = setup_extended_engine()
```

## 🤝 Участие в разработке

1. **Fork** репозитория
2. **Создайте** ветку для новой функции (`git checkout -b feature/amazing-feature`)
3. **Зафиксируйте** изменения (`git commit -m 'Add amazing feature'`)
4. **Отправьте** в ветку (`git push origin feature/amazing-feature`)
5. **Откройте** Pull Request

### Стандарты кодирования

- Используйте **Black** для форматирования кода
- Добавляйте **type hints** для всех функций
- Пишите **docstrings** для всех публичных методов
- Покрывайте новый код **тестами**

## 🐛 Сообщение об ошибках

Если вы нашли ошибку, пожалуйста:

1. Проверьте, что ошибка еще не сообщалась в [Issues](https://github.com/your-username/excel-comparator/issues)
2. Создайте новый Issue с подробным описанием
3. Приложите логи из `excel_comparator.log`
4. Укажите версию Python и ОС

## 📄 Лицензия

Этот проект лицензирован под MIT License - см. файл [LICENSE](LICENSE) для подробностей.

## 🙏 Благодарности

- **pandas** - за мощную библиотеку обработки данных
- **openpyxl** - за работу с Excel файлами
- **tkinter** - за кроссплатформенный GUI
- Всем контрибьюторам проекта

## 📞 Поддержка

- 📧 Email: support@excelcomparator.com
- 💬 Discussions: [GitHub Discussions](https://github.com/your-username/excel-comparator/discussions)
- 📖 Wiki: [Документация](https://github.com/your-username/excel-comparator/wiki)

---

**Excel Comparator** - делает сравнение файлов простым и мощным! 🚀
