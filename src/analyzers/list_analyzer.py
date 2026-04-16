"""
Анализатор различий для данных в виде списков
"""

import logging
from collections import Counter
from typing import Any

import pandas as pd

from ..core.interfaces import DifferenceDetail, IDifferenceAnalyzer


class ListDifferenceAnalyzer(IDifferenceAnalyzer):
    """
    Анализатор для различий в списках (строки, разделенные запятыми)

    Анализирует две строки как списки элементов, разделенных определенным символом.
    Определяет добавленные, удаленные элементы, изменения порядка и дубликаты.
    """

    def __init__(self, separator: str = ","):
        """
        Инициализирует анализатор списков

        Args:
            separator: Символ-разделитель элементов списка
        """
        self.separator = separator
        self.logger = logging.getLogger(self.__class__.__name__)

    def can_analyze(self, old_value: Any, new_value: Any) -> bool:
        """
        Проверяет, может ли анализатор обработать данные значения

        Args:
            old_value: Старое значение
            new_value: Новое значение

        Returns:
            bool: True, если оба значения являются строками и хотя бы одно
                  содержит разделитель списка
        """
        if not (isinstance(old_value, str) and isinstance(new_value, str)):
            return False

        # Проверяем, что хотя бы одно из значений является списком
        return self.separator in old_value or self.separator in new_value

    def analyze(self, old_value: Any, new_value: Any, column: str) -> DifferenceDetail:
        """
        Анализирует различие между двумя списками

        Args:
            old_value: Старое значение (строка с разделителями)
            new_value: Новое значение (строка с разделителями)
            column: Имя столбца, к которому относятся значения

        Returns:
            DifferenceDetail: Детальная информация о различиях

        Raises:
            ValueError: Если значения не могут быть проанализированы как списки
        """
        if not self.can_analyze(old_value, new_value):
            raise ValueError("Значения не могут быть проанализированы как списки")

        old_list = self._parse_list(old_value)
        new_list = self._parse_list(new_value)

        analysis_result = self._analyze_lists(old_list, new_list)
        description = self._generate_description(analysis_result)
        difference_type = self._determine_difference_type(analysis_result)

        return DifferenceDetail(
            column=column,
            old_value=old_value,
            new_value=new_value,
            difference_type=difference_type,
            description=description,
        )

    def _parse_list(self, value: str) -> list[str]:
        """
        Парсит строку в список элементов

        Args:
            value: Строка с разделителями

        Returns:
            List[str]: Список элементов
        """
        if not value:
            return []

        return [item.strip() for item in value.split(self.separator) if item.strip()]

    def _analyze_lists(self, old_list: list[str], new_list: list[str]) -> dict[str, Any]:
        """
        Выполняет детальный анализ различий между списками

        Args:
            old_list: Список элементов из старого значения
            new_list: Список элементов из нового значения

        Returns:
            Dict[str, Any]: Словарь с результатами анализа
        """
        # Используем Counter для более эффективного поиска дубликатов
        old_counter = Counter(old_list)
        new_counter = Counter(new_list)

        # Наборы уникальных элементов
        old_set = set(old_list)
        new_set = set(new_list)

        # Находим дубликаты (элементы, которые встречаются более одного раза)
        old_duplicates = [item for item, count in old_counter.items() if count > 1]
        new_duplicates = [item for item, count in new_counter.items() if count > 1]
        has_duplicates = bool(old_duplicates or new_duplicates)

        # Найти добавленные и удаленные элементы
        added = sorted(list(new_set - old_set))
        removed = sorted(list(old_set - new_set))

        # Найти общие элементы, но с разным количеством повторений
        common_elements = old_set.intersection(new_set)
        frequency_changes = {
            item: (old_counter[item], new_counter[item])
            for item in common_elements
            if old_counter[item] != new_counter[item]
        }

        # Проверка изменения порядка: только если содержимое одинаковое
        order_changed = (
            not added and not removed and len(frequency_changes) == 0 and old_list != new_list
        )

        return {
            "has_duplicates": has_duplicates,
            "old_duplicates": old_duplicates,
            "new_duplicates": new_duplicates,
            "added": added,
            "removed": removed,
            "frequency_changes": frequency_changes,
            "order_changed": order_changed,
            "old_count": len(old_list),
            "new_count": len(new_list),
        }

    def _generate_description(self, analysis: dict[str, Any]) -> str:
        """
        Генерирует описание различий на основе анализа

        Args:
            analysis: Результат анализа списков

        Returns:
            str: Текстовое описание различий
        """
        description_parts = []

        # Анализ дубликатов
        if analysis["has_duplicates"]:
            dup_info = []
            if analysis["old_duplicates"]:
                dup_info.append(f"в старом: {', '.join(analysis['old_duplicates'])}")
            if analysis["new_duplicates"]:
                dup_info.append(f"в новом: {', '.join(analysis['new_duplicates'])}")
            description_parts.append(f"Дубли ({'; '.join(dup_info)})")

        # Анализ добавленных элементов
        if analysis["added"]:
            description_parts.append(f"Добавлено: {', '.join(analysis['added'])}")

        # Анализ удаленных элементов
        if analysis["removed"]:
            description_parts.append(f"Удалено: {', '.join(analysis['removed'])}")

        # Анализ изменения частоты
        if analysis["frequency_changes"]:
            freq_changes = []
            for item, (old_count, new_count) in analysis["frequency_changes"].items():
                freq_changes.append(f"{item}: {old_count}→{new_count}")

            description_parts.append(f"Изменения частоты: {', '.join(freq_changes)}")

        # Анализ изменения порядка
        if analysis["order_changed"]:
            description_parts.append("Порядок изменен")

        # Если списки идентичны
        if not description_parts:
            return "Списки идентичны"

        return "; ".join(description_parts)

    def _determine_difference_type(self, analysis: dict[str, Any]) -> str:
        """
        Определяет тип различия на основе анализа

        Args:
            analysis: Результат анализа списков

        Returns:
            str: Код типа различия
        """
        if analysis["added"] and analysis["removed"]:
            return "mixed_changes"
        elif analysis["added"]:
            return "additions"
        elif analysis["removed"]:
            return "removals"
        elif analysis["frequency_changes"]:
            return "frequency_changes"
        elif analysis["order_changed"]:
            return "reorder"
        elif analysis["has_duplicates"]:
            return "duplicates"
        else:
            return "identical"


class BasicDifferenceAnalyzer(IDifferenceAnalyzer):
    """
    Базовый анализатор для простых различий

    Выполняет базовое сравнение значений, определяя добавление, удаление
    и изменение значений. Используется как анализатор по умолчанию,
    когда специализированные анализаторы не применимы.
    """

    def __init__(self) -> None:
        """Инициализирует базовый анализатор различий"""
        self.logger = logging.getLogger(self.__class__.__name__)

    def can_analyze(self, old_value: Any, new_value: Any) -> bool:
        """
        Может анализировать любые значения

        Args:
            old_value: Старое значение
            new_value: Новое значение

        Returns:
            bool: Всегда возвращает True
        """
        return True

    def analyze(self, old_value: Any, new_value: Any, column: str) -> DifferenceDetail:
        """
        Выполняет базовый анализ различий

        Args:
            old_value: Старое значение
            new_value: Новое значение
            column: Имя столбца, к которому относятся значения

        Returns:
            DifferenceDetail: Детальная информация о различиях
        """
        # Определяем тип различия
        difference_type = self._determine_type(old_value, new_value)

        # Форматируем значения для отображения
        formatted_old = self._format_value(old_value)
        formatted_new = self._format_value(new_value)

        # Создаем описание
        description = f"{formatted_old} → {formatted_new}"

        return DifferenceDetail(
            column=column,
            old_value=old_value,
            new_value=new_value,
            difference_type=difference_type,
            description=description,
        )

    def _determine_type(self, old_value: Any, new_value: Any) -> str:
        """
        Определяет тип различия

        Args:
            old_value: Старое значение
            new_value: Новое значение

        Returns:
            str: Код типа различия
        """
        if pd.isna(old_value) and not pd.isna(new_value):
            return "added"
        elif not pd.isna(old_value) and pd.isna(new_value):
            return "removed"
        elif type(old_value) is not type(new_value):
            return "type_change"
        else:
            return "value_change"

    def _format_value(self, value: Any) -> str:
        """
        Форматирует значение для отображения в описании

        Args:
            value: Значение для форматирования

        Returns:
            str: Отформатированное значение
        """
        if pd.isna(value):
            return "NULL"
        elif isinstance(value, (int, float)):
            return str(value)
        elif isinstance(value, str):
            # Обрезаем длинные строки
            if len(value) > 50:
                return value[:47] + "..."
            return value
        else:
            return str(value)
