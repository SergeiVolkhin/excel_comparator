"""CSV-specific validation rules.

The generic :class:`IValidationRule` interface only sees DataFrames
(already loaded, already decoded). A "CSV-specific" rule therefore can't
look at file bytes — instead it spots structural shapes that strongly
correlate with CSV-level mistakes:

* A massive row-count imbalance between two files is almost always the
  symptom of a wrong ``sep=`` choice: one file parsed with the expected
  delimiter and the other collapsed to a single column (or exploded).
* A DataFrame with a single object-typed column whose values contain a
  delimiter character strongly suggests auto-detect picked the wrong
  separator.
"""

from __future__ import annotations

import logging

import pandas as pd

from ..core.interfaces import IValidationRule

#: Default ratio above which a row-count imbalance is flagged as an
#: error. Picked high enough that legitimate "one file has more data
#: than the other" scenarios pass, but low enough to catch the classic
#: comma-vs-semicolon mis-parse that collapses one side to ~1 row/line.
DEFAULT_MAX_ROW_COUNT_RATIO: float = 100.0


class CSVRowCountRatioValidator(IValidationRule):
    """Flags files whose row counts differ by an implausible ratio.

    Use case: the loader picked the wrong delimiter for one file, so
    that file collapsed to (say) 1 column / 1 row and the other parsed
    normally. A ratio threshold catches this without breaking legitimate
    partial-dataset comparisons.
    """

    def __init__(self, max_ratio: float = DEFAULT_MAX_ROW_COUNT_RATIO) -> None:
        self.max_ratio = max_ratio
        self.logger = logging.getLogger(self.__class__.__name__)

    def validate(self, df1: pd.DataFrame, df2: pd.DataFrame) -> list[str]:
        n1, n2 = len(df1), len(df2)
        if n1 == 0 or n2 == 0:
            # Empty-data is handled by EmptyDataValidationRule already —
            # stay silent here so the user gets one clear error.
            return []
        ratio = max(n1, n2) / min(n1, n2)
        if ratio > self.max_ratio:
            self.logger.warning(
                f"Row-count ratio {ratio:.0f}x ({n1} vs {n2}) looks like a delimiter mismatch",
            )
            return [
                f"Сильное расхождение количества строк: {n1} vs {n2} "
                f"(x{ratio:.0f} при пороге x{self.max_ratio:.0f}). "
                f"Возможно, выбран неверный разделитель CSV."
            ]
        return []

    def get_rule_name(self) -> str:
        return f"CSV: проверка соотношения строк (макс. x{self.max_ratio:.0f})"


class CSVSingleColumnCollapseValidator(IValidationRule):
    """Flags a single-column object DataFrame whose values still contain
    obvious CSV delimiters — a near-certain wrong-separator mis-parse.
    """

    _SUSPECT_DELIMITERS: tuple[str, ...] = (",", ";", "\t", "|")
    _SAMPLE_ROWS: int = 20

    def __init__(self) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)

    def validate(self, df1: pd.DataFrame, df2: pd.DataFrame) -> list[str]:
        errors: list[str] = []
        for label, df in (("первом", df1), ("втором", df2)):
            if self._looks_collapsed(df):
                self.logger.warning(f"CSV в {label} файле выглядит как одна слипшаяся колонка")
                errors.append(
                    f"Похоже, {label} CSV был разобран неверным разделителем — "
                    f"значения одной колонки всё ещё содержат символы "
                    f"{', '.join(repr(d) for d in self._SUSPECT_DELIMITERS)}."
                )
        return errors

    @classmethod
    def _looks_collapsed(cls, df: pd.DataFrame) -> bool:
        if df.shape[1] != 1:
            return False
        only_col = df.iloc[:, 0]
        if only_col.dtype != object:
            return False
        sample = only_col.head(cls._SAMPLE_ROWS).dropna().astype(str)
        if sample.empty:
            return False
        # At least half of the sample rows contain a suspect delimiter.
        hit = sum(any(d in s for d in cls._SUSPECT_DELIMITERS) for s in sample)
        return hit >= max(1, len(sample) // 2)

    def get_rule_name(self) -> str:
        return "CSV: проверка слипшейся одной колонки"


def create_csv_validators() -> list[IValidationRule]:
    """Bundle of CSV-specific validators for ``ValidationRuleFactory.for_csv()``."""
    return [
        CSVRowCountRatioValidator(),
        CSVSingleColumnCollapseValidator(),
    ]
