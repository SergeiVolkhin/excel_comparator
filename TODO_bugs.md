# Latent bugs discovered during characterization (fix separately after refactor)

These are **pre-existing** bugs in the codebase, not introduced by the refactor.
Per plan rules, each is fixed in its own `fix:` commit, not silently folded
into refactor work.

## 1. `ExcelFileLoader.get_sheet_names` — unclosed `pd.ExcelFile`
- File: `src/loaders/excel_loader.py:74-82`
- Symptom: `ResourceWarning: unclosed file` surfaced via pytest's
  `PytestUnraisableExceptionWarning` during test runs.
- Fix: wrap `pd.ExcelFile(...)` in `with`-statement (it's a context manager).

## 2. `BasicComparator._create_differences_mask` — pandas FutureWarning on `fillna(object_sentinel)`
- File: `src/comparators/basic_comparator.py:108-109`
       and `src/comparators/advanced_comparator.py:250-251`
- Symptom: `FutureWarning: Downcasting object dtype arrays on .fillna ...`
  on modern pandas; becomes `TypeError` on future pandas.
- Fix: replace object-sentinel pattern with
  `df1.eq(df2) | (df1.isna() & df2.isna())` vectorised equality,
  or `infer_objects(copy=False)` as interim mitigation.

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
