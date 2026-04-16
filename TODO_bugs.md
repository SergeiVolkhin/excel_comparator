# Latent bugs discovered during characterization (fix separately after refactor)

These are **pre-existing** bugs in the codebase, not introduced by the refactor.
Per plan rules, each is fixed in its own `fix:` commit, not silently folded
into refactor work.

## 1. `ExcelFileLoader.get_sheet_names` — unclosed `pd.ExcelFile`  ✅ FIXED
- File: `src/loaders/excel_loader.py:74-82`
- Symptom: `ResourceWarning: unclosed file` surfaced via pytest's
  `PytestUnraisableExceptionWarning` during test runs.
- Fix applied in commit `perf: add read_only option to ExcelFileLoader
  + fix unclosed file`: xlsx path now goes through
  `load_workbook(read_only=True)` with try/finally close; .xls path
  uses `pd.ExcelFile` in a `with`-block.

## 2. `BasicComparator._create_differences_mask` — pandas FutureWarning on `fillna(object_sentinel)`  ✅ FIXED
- File: `src/comparators/basic_comparator.py:108-109`
       and `src/comparators/advanced_comparator.py:250-251`
- Symptom: `FutureWarning: Downcasting object dtype arrays on .fillna ...`
  on modern pandas; becomes `TypeError` on future pandas.
- Fix applied: `build_differences_mask` in `src/comparators/_shared.py`
  now computes `(df1.values != df2.values) & ~(df1.isna() & df2.isna())`
  — NaN-safe without any sentinel. `_na_marker` attribute removed
  from both comparators. Regression test added in
  `tests/test_basic_comparator.py::test_no_future_warning_on_object_columns`.
  pytest `filterwarnings = ["error"]` (no pandas suppressions).

## 3. `BasicComparator._preprocess_dataframe` — wasteful `astype(str)` mask on every cell  ✅ FIXED
- File: `src/comparators/basic_comparator.py:95-101` (original)
- Symptom: even with a dtype==object guard, the NaN-mask was built as
  `result_df[col].astype(str) != 'nan'` — this coerced *every* value in
  the column just to detect NaN, and also misbehaves if a cell contains
  the literal string ``"nan"``.
- Fix applied in commit `refactor: dedupe _preprocess_dataframe ...`
  (2899087): the extracted `preprocess_dataframe` in
  `src/comparators/_shared.py` now uses `result[col].notna()`, which is
  both cheaper and semantically correct. Regression test added in
  `tests/test_basic_comparator.py::test_ignore_case_preserves_numeric_columns`.

## 4. `AdvancedComparator.align_dataframes` with `key_columns` — result ignored  ⚠️ DOCUMENTED / PARTIAL
- File: `src/comparators/advanced_comparator.py:156-176`
- Symptom: when `key_columns` is provided, code performs an outer merge
  but discards the merged frame and returns the original aligned ones.
  Row statistics are populated, but cell-level comparison is not actually
  key-based.
- Status: limitation is now **explicit**, not silent:
  - `AdvancedComparator.compare` docstring calls out the limitation
    ("row-статистика считается по ключам, но фактическое cell-level
    сравнение по-прежнему выполняется построчно (по индексу)").
  - `align_dataframes` logs a WARNING via `self.logger.warning(...)`
    when key_columns is provided, naming the feature as planned.
  - Regression test:
    `tests/test_advanced_comparator.py::TestKeyColumns::test_valid_key_columns_logs_warning`.
- Follow-up: implementing true key-based cell-level alignment is a
  separate feature, not a bug fix.
