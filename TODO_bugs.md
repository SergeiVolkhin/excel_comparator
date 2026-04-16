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

## 3. `BasicComparator._preprocess_dataframe` — chained `astype(str)` on numeric dtypes
- File: `src/comparators/basic_comparator.py:95-101`
- Symptom: `.astype(str).str.lower()` runs on numeric columns when
  `ignore_case`/`ignore_whitespace` is set, wasting CPU and converting
  numbers to strings unintentionally if the mask matches.
- Fix: apply only to `dtype == "object"` columns (guard already partially
  present but still enters the loop for non-strings).

## 4. `AdvancedComparator.align_dataframes` with `key_columns` — result ignored
- File: `src/comparators/advanced_comparator.py:156-176`
- Symptom: when `key_columns` is provided, code performs an outer merge
  but discards the merged frame and returns the original aligned ones.
  Row statistics are populated, but cell-level comparison is not actually
  key-based.
- Fix: either implement key-based alignment properly or remove the
  misleading `key_columns` option.
