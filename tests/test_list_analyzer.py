"""Tests for src/analyzers/list_analyzer.py (pytest style)."""

from __future__ import annotations

import pytest

from src.analyzers.list_analyzer import BasicDifferenceAnalyzer, ListDifferenceAnalyzer
from src.core.interfaces import DifferenceDetail


@pytest.fixture
def list_analyzer() -> ListDifferenceAnalyzer:
    return ListDifferenceAnalyzer()


@pytest.fixture
def basic_analyzer() -> BasicDifferenceAnalyzer:
    return BasicDifferenceAnalyzer()


class TestListDifferenceAnalyzerCanAnalyze:
    @pytest.mark.parametrize(
        ("v1", "v2", "expected"),
        [
            ("a,b,c", "a,b,d", True),
            ("a,b,c", "a,b,c,d", True),
            ("a,b,c", "", True),
            ("a", "a,b", True),
            ("a", "b", False),
            (123, "a,b,c", False),
            ("a,b,c", 123, False),
            (None, "a,b,c", False),
        ],
    )
    def test_can_analyze(
        self, list_analyzer: ListDifferenceAnalyzer, v1: object, v2: object, expected: bool
    ) -> None:
        assert list_analyzer.can_analyze(v1, v2) is expected


class TestListDifferenceAnalyzerParseList:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("a,b,c", ["a", "b", "c"]),
            ("a, b, c", ["a", "b", "c"]),
            ("", []),
            (",", []),
            ("a", ["a"]),
            ("a,", ["a"]),
            (",a", ["a"]),
            ("a,,c", ["a", "c"]),
            (" , , ", []),
        ],
    )
    def test_parse_list(
        self, list_analyzer: ListDifferenceAnalyzer, raw: str, expected: list[str]
    ) -> None:
        assert list_analyzer._parse_list(raw) == expected


class TestListDifferenceAnalyzerAnalyze:
    def test_identical(self, list_analyzer: ListDifferenceAnalyzer) -> None:
        result = list_analyzer.analyze("a,b,c", "a,b,c", "test_column")
        assert isinstance(result, DifferenceDetail)
        assert result.difference_type == "identical"
        assert result.description == "Списки идентичны"

    def test_additions(self, list_analyzer: ListDifferenceAnalyzer) -> None:
        result = list_analyzer.analyze("a,b,c", "a,b,c,d", "test_column")
        assert result.difference_type == "additions"
        assert "Добавлено: d" in result.description

    def test_removals(self, list_analyzer: ListDifferenceAnalyzer) -> None:
        result = list_analyzer.analyze("a,b,c,d", "a,b,c", "test_column")
        assert result.difference_type == "removals"
        assert "Удалено: d" in result.description

    def test_mixed_changes(self, list_analyzer: ListDifferenceAnalyzer) -> None:
        result = list_analyzer.analyze("a,b,c,d", "a,b,c,e", "test_column")
        assert result.difference_type == "mixed_changes"
        assert "Добавлено: e" in result.description
        assert "Удалено: d" in result.description

    def test_reorder(self, list_analyzer: ListDifferenceAnalyzer) -> None:
        result = list_analyzer.analyze("a,b,c", "c,b,a", "test_column")
        assert result.difference_type == "reorder"
        assert "Порядок изменен" in result.description

    def test_duplicates_frequency_changes(self, list_analyzer: ListDifferenceAnalyzer) -> None:
        result = list_analyzer.analyze("a,b,c", "a,b,b,c", "test_column")
        assert "frequency_changes" in result.difference_type
        assert "Изменения частоты" in result.description


class TestBasicDifferenceAnalyzer:
    def test_always_can_analyze(self, basic_analyzer: BasicDifferenceAnalyzer) -> None:
        assert basic_analyzer.can_analyze("any", "value") is True
        assert basic_analyzer.can_analyze(123, None) is True

    def test_value_change(self, basic_analyzer: BasicDifferenceAnalyzer) -> None:
        result = basic_analyzer.analyze("old", "new", "test_column")
        assert result.difference_type == "value_change"
        assert result.description == "old → new"

    def test_added(self, basic_analyzer: BasicDifferenceAnalyzer) -> None:
        result = basic_analyzer.analyze(None, "new", "test_column")
        assert result.difference_type == "added"
        assert result.description == "NULL → new"

    def test_removed(self, basic_analyzer: BasicDifferenceAnalyzer) -> None:
        result = basic_analyzer.analyze("old", None, "test_column")
        assert result.difference_type == "removed"
        assert result.description == "old → NULL"

    def test_type_change(self, basic_analyzer: BasicDifferenceAnalyzer) -> None:
        result = basic_analyzer.analyze(123, "123", "test_column")
        assert result.difference_type == "type_change"
