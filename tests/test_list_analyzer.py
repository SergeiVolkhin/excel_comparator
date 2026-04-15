"""
Тесты для анализатора списков (src/analyzers/list_analyzer.py)
"""

import unittest
from src.analyzers.list_analyzer import ListDifferenceAnalyzer, BasicDifferenceAnalyzer
from src.core.interfaces import DifferenceDetail


class TestListDifferenceAnalyzer(unittest.TestCase):
    """Тесты для анализатора списков"""

    def setUp(self):
        """Инициализация тестов"""
        self.analyzer = ListDifferenceAnalyzer()
        self.basic_analyzer = BasicDifferenceAnalyzer()

    def test_can_analyze(self):
        """Тест метода can_analyze"""
        # Положительные тесты
        self.assertTrue(self.analyzer.can_analyze("a,b,c", "a,b,d"))
        self.assertTrue(self.analyzer.can_analyze("a,b,c", "a,b,c,d"))
        self.assertTrue(self.analyzer.can_analyze("a,b,c", ""))
        
        # Граничные случаи
        self.assertTrue(self.analyzer.can_analyze("a", "a,b"))  # Только во втором есть разделитель
        self.assertFalse(self.analyzer.can_analyze("a", "b"))  # Нет разделителей
        
        # Отрицательные тесты
        self.assertFalse(self.analyzer.can_analyze(123, "a,b,c"))  # Не строка
        self.assertFalse(self.analyzer.can_analyze("a,b,c", 123))  # Не строка
        self.assertFalse(self.analyzer.can_analyze(None, "a,b,c"))  # None

    def test_parse_list(self):
        """Тест метода _parse_list"""
        # Нормальные случаи
        self.assertEqual(self.analyzer._parse_list("a,b,c"), ["a", "b", "c"])
        self.assertEqual(self.analyzer._parse_list("a, b, c"), ["a", "b", "c"])  # С пробелами
        
        # Граничные случаи
        self.assertEqual(self.analyzer._parse_list(""), [])  # Пустая строка
        self.assertEqual(self.analyzer._parse_list(","), [])  # Только разделитель
        self.assertEqual(self.analyzer._parse_list("a"), ["a"])  # Один элемент без разделителя
        self.assertEqual(self.analyzer._parse_list("a,"), ["a"])  # Один элемент с разделителем
        self.assertEqual(self.analyzer._parse_list(",a"), ["a"])  # Разделитель в начале
        
        # Особые случаи
        self.assertEqual(self.analyzer._parse_list("a,,c"), ["a", "c"])  # Пустой элемент пропускается
        self.assertEqual(self.analyzer._parse_list(" , , "), [])  # Только пробелы и разделители

    def test_analyze_identical_lists(self):
        """Тест анализа идентичных списков"""
        result = self.analyzer.analyze("a,b,c", "a,b,c", "test_column")
        
        self.assertIsInstance(result, DifferenceDetail)
        self.assertEqual(result.difference_type, "identical")
        self.assertEqual(result.description, "Списки идентичны")

    def test_analyze_added_elements(self):
        """Тест анализа списков с добавленными элементами"""
        result = self.analyzer.analyze("a,b,c", "a,b,c,d", "test_column")
        
        self.assertIsInstance(result, DifferenceDetail)
        self.assertEqual(result.difference_type, "additions")
        self.assertIn("Добавлено: d", result.description)

    def test_analyze_removed_elements(self):
        """Тест анализа списков с удаленными элементами"""
        result = self.analyzer.analyze("a,b,c,d", "a,b,c", "test_column")
        
        self.assertIsInstance(result, DifferenceDetail)
        self.assertEqual(result.difference_type, "removals")
        self.assertIn("Удалено: d", result.description)

    def test_analyze_mixed_changes(self):
        """Тест анализа списков со смешанными изменениями"""
        result = self.analyzer.analyze("a,b,c,d", "a,b,c,e", "test_column")
        
        self.assertIsInstance(result, DifferenceDetail)
        self.assertEqual(result.difference_type, "mixed_changes")
        self.assertIn("Добавлено: e", result.description)
        self.assertIn("Удалено: d", result.description)

    def test_analyze_reordered_elements(self):
        """Тест анализа списков с изменением порядка"""
        result = self.analyzer.analyze("a,b,c", "c,b,a", "test_column")
        
        self.assertIsInstance(result, DifferenceDetail)
        self.assertEqual(result.difference_type, "reorder")
        self.assertIn("Порядок изменен", result.description)

    def test_analyze_duplicates(self):
        """Тест анализа списков с дубликатами"""
        result = self.analyzer.analyze("a,b,c", "a,b,b,c", "test_column")
        
        self.assertIsInstance(result, DifferenceDetail)
        # Когда добавляется дубликат, это изменение частоты элемента
        self.assertIn("frequency_changes", result.difference_type)
        self.assertIn("Изменения частоты", result.description)

    def test_basic_analyzer(self):
        """Тест базового анализатора"""
        # Тест метода can_analyze (всегда должен возвращать True)
        self.assertTrue(self.basic_analyzer.can_analyze("any", "value"))
        self.assertTrue(self.basic_analyzer.can_analyze(123, None))
        
        # Тест анализа типичных значений
        result = self.basic_analyzer.analyze("old", "new", "test_column")
        self.assertEqual(result.difference_type, "value_change")
        self.assertEqual(result.description, "old → new")
        
        # Тест анализа с None
        result = self.basic_analyzer.analyze(None, "new", "test_column")
        self.assertEqual(result.difference_type, "added")
        self.assertEqual(result.description, "NULL → new")
        
        result = self.basic_analyzer.analyze("old", None, "test_column")
        self.assertEqual(result.difference_type, "removed")
        self.assertEqual(result.description, "old → NULL")
        
        # Тест анализа с разными типами
        result = self.basic_analyzer.analyze(123, "123", "test_column")
        self.assertEqual(result.difference_type, "type_change")


if __name__ == "__main__":
    unittest.main()