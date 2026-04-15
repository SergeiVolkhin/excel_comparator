# 📁 Структура проекта Excel Comparator

## Обзор архитектуры

Данный проект представляет собой профессиональное модульное приложение для сравнения Excel файлов, построенное согласно принципам SOLID, особенно принципу Open/Closed (OCP).

```
excel_comparator/
├── main.py                          # 🚀 Точка входа в приложение
├── requirements.txt                 # 📋 Зависимости Python
├── config.json                      # ⚙️  Конфигурационный файл (создается автоматически)
├── excel_comparator.log            # 📝 Лог файл (создается автоматически)
├── README.md                       # 📖 Документация проекта
├── project_structure.md            # 📁 Данный файл
├── architecture.md                 # 🏗️  Описание архитектуры
└── src/                            # 📦 Исходный код
    ├── __init__.py
    ├── core/                       # 🔧 Ядро системы
    │   ├── __init__.py
    │   ├── interfaces.py           # 🔌 Базовые интерфейсы (ABC)
    │   ├── exceptions.py           # ❌ Пользовательские исключения
    │   ├── config.py              # ⚙️  Система конфигурации
    │   └── engine.py              # 🎯 Движок сравнения
    ├── loaders/                    # 📥 Загрузчики файлов
    │   ├── __init__.py
    │   ├── excel_loader.py        # 📊 Загрузчик Excel (.xlsx, .xls)
    │   └── csv_loader.py          # 📄 Загрузчик CSV (.csv, .tsv, .txt)
    ├── comparators/                # ⚖️  Компараторы
    │   ├── __init__.py
    │   ├── basic_comparator.py    # 🔍 Базовое точное сравнение
    │   └── advanced_comparator.py # 🧠 Продвинутые алгоритмы сравнения
    ├── analyzers/                  # 🔬 Анализаторы различий
    │   ├── __init__.py
    │   └── list_analyzer.py       # 📝 Анализ списков и текста
    ├── formatters/                 # 🎨 Форматтеры вывода
    │   ├── __init__.py
    │   ├── excel_formatter.py     # 📊 Вывод в Excel
    │   └── html_formatter.py      # 🌐 Вывод в HTML
    ├── validators/                 # ✅ Валидаторы данных
    │   ├── __init__.py
    │   └── base_validators.py     # 🛡️  Базовые правила валидации
    └── gui/                       # 🖥️  Графический интерфейс
        ├── __init__.py
        ├── main_window.py         # 🏠 Главное окно приложения
        └── widgets.py             # 🎛️  Пользовательские виджеты
```

## 📋 Описание модулей

### 🔧 Core (Ядро системы)

- **interfaces.py**: Определяет контракты для всех компонентов системы
- **exceptions.py**: Иерархия пользовательских исключений
- **config.py**: Система конфигурации с автосохранением
- **engine.py**: Центральный движок, координирующий работу всех компонентов

### 📥 Loaders (Загрузчики)

- **excel_loader.py**: Загрузка Excel файлов с поддержкой .xlsx и .xls
- **csv_loader.py**: Загрузка CSV с автоопределением кодировки и разделителей

### ⚖️ Comparators (Компараторы)

- **basic_comparator.py**: Точное побайтовое сравнение
- **advanced_comparator.py**: 
  - Нечеткое сравнение с порогом схожести
  - Числовое сравнение с допусками
  - Структурный анализ

### 🔬 Analyzers (Анализаторы)

- **list_analyzer.py**: Детальный анализ различий в списках и строках

### 🎨 Formatters (Форматтеры)

- **excel_formatter.py**: Создание отчетов в формате Excel с подсветкой
- **html_formatter.py**: Интерактивные HTML отчеты с статистикой

### ✅ Validators (Валидаторы)

- **base_validators.py**: Набор правил для проверки корректности данных

### 🖥️ GUI (Графический интерфейс)

- **main_window.py**: Главное окно с полным функционалом
- **widgets.py**: Переиспользуемые компоненты интерфейса

## 🔌 Принципы расширяемости

### 1. **Open/Closed Principle**
Новые функции добавляются без изменения существующего кода:

```python
# Добавление нового загрузчика
class JSONLoader(IFileLoader):
    def can_load(self, file_path: Path) -> bool:
        return file_path.suffix.lower() == '.json'
    
    def load(self, file_path: Path, **kwargs) -> pd.DataFrame:
        # Реализация загрузки JSON
        pass

# Регистрация в движке
engine.register_file_loader(JSONLoader())
```

### 2. **Dependency Inversion Principle**
Компоненты зависят от абстракций, а не от конкретных реализаций:

```python
# Движок работает с интерфейсами
class ComparisonEngine:
    def __init__(self):
        self._comparators: Dict[str, IComparator] = {}
        self._formatters: Dict[str, IOutputFormatter] = {}
```

### 3. **Single Responsibility Principle**
Каждый класс отвечает за одну задачу:
- Загрузчики только загружают
- Компараторы только сравнивают
- Форматтеры только форматируют

## 🚀 Примеры расширения

### Добавление нового компаратора

```python
class SemanticComparator(IComparator):
    \"\"\"Семантическое сравнение с использованием NLP\"\"\"
    
    def compare(self, df1: pd.DataFrame, df2: pd.DataFrame, **options) -> ComparisonResult:
        # Семантический анализ текста
        pass
    
    def get_name(self) -> str:
        return "Семантическое сравнение"

# Регистрация
engine.register_comparator("semantic", SemanticComparator())
```

### Добавление нового форматтера

```python
class PDFFormatter(IOutputFormatter):
    \"\"\"Экспорт в PDF\"\"\"
    
    def format(self, result: ComparisonResult, output_path: Path, **options) -> None:
        # Генерация PDF отчета
        pass
    
    def get_supported_formats(self) -> List[str]:
        return ['.pdf']

# Регистрация
engine.register_formatter("pdf", PDFFormatter())
```

## 🛠️ Технологический стек

- **Python 3.8+**: Основной язык
- **pandas**: Обработка данных
- **openpyxl**: Работа с Excel
- **tkinter**: Графический интерфейс
- **chardet**: Определение кодировки
- **logging**: Система логирования

## 📈 Возможности для развития

1. **Плагинная система**: Динамическая загрузка модулей
2. **API сервер**: REST API для удаленного сравнения
3. **Базы данных**: Поддержка сравнения таблиц БД
4. **Машинное обучение**: ИИ для анализа паттернов различий
5. **Облачная интеграция**: Работа с облачными хранилищами
6. **Командная строка**: CLI интерфейс для автоматизации

## 🔒 Безопасность и надежность

- Валидация всех входных данных
- Обработка исключений на всех уровнях
- Логирование операций
- Ограничения на размер файлов
- Защита от переполнения памяти

## 📊 Мониторинг и диагностика

- Подробное логирование в файл
- Отчеты о производительности
- Статистика использования
- Диагностика ошибок с контекстом