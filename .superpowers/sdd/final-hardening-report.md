# Final Hardening Report — experiment-handoff feature

## Fix 1 — Harden guardrail vs pasted predictions in `Actual`

**Problem:** `~74.5 (pred)` pasted into an `Actual` cell was accepted as a real measured value.

**Solution:**
- Added module-level helper `_looks_like_prediction(value)` in `tools/handoff_table.py` (matches `(pred)` substring or leading `~`).
- `validate`: a RUN row is filled ONLY if `actual` is not in `EMPTY_ACTUAL` AND not `_looks_like_prediction(actual)`. A prediction-looking actual appears in `missing`.
- `extract`: for a RUN row, if `actual` is empty OR `_looks_like_prediction(actual)`, route to `incomplete` (not `measured`).

**New tests (RED→GREEN):**
- `TestPastedPrediction::test_validate_treats_pasted_prediction_as_unfilled` — RUN row with `~74.5 (pred)` in Actual → `ok False`, row in `missing`. RED before fix, GREEN after.
- `TestPastedPrediction::test_extract_routes_pasted_prediction_to_incomplete` — same table → `extract` puts row in `incomplete`, not in `results`. RED before fix, GREEN after.

---

## Fix 2 — Template placeholder reuse value

**Problem:** REUSE rows with `[value]` or `[val]` placeholders were emitted as `reused` results.

**Solution:**
- Added `"[value]"` and `"[val]"` to `EMPTY_ACTUAL` set.
- `extract`: for a REUSE row whose `actual` is in `EMPTY_ACTUAL`, skip emitting it entirely.

**New test (RED→GREEN):**
- `TestPlaceholderReuse::test_extract_skips_placeholder_reuse_rows` — REUSE rows with `[value]`/`[val]` must not appear in results. RED before fix, GREEN after.

---

## Fix 3 — Template trailing newline

**Problem:** Template might not end with exactly one trailing newline.

**Verification:** `EXPERIMENT_HANDOFF_TEMPLATE.md` already ended with exactly one `\n`. No change needed to the file.

**New test (passed immediately — GREEN from start):**
- `TestTemplate::test_template_ends_with_single_newline` — asserts `raw.endswith(b"\n")` and NOT `raw.endswith(b"\n\n")`.

---

## Existing guardrail + TestTemplate confirmation

- `TestExtract::test_extract_drops_predictions_keeps_measured_and_reused`: SAMPLE_TABLE has `73.4` (plain number) → still `measured`; `⬜` row stays `incomplete`; `dropped_predictions == 2`; `kinds == ["measured", "reused"]`. PASSED unchanged.
- `TestTemplate::test_template_parses_and_has_run_and_reuse`: template still has `n_run >= 1`, `n_reuse >= 1`, `ok False`. PASSED unchanged.

---

## Full suite output

```
============================= test session starts =============================
platform win32 -- Python 3.14.3, pytest-9.1.1, pluggy-1.6.0
collected 19 items

tests/test_handoff_table.py::TestSlugify::test_basic_kebab PASSED
tests/test_handoff_table.py::TestSlugify::test_caps_length_no_trailing_dash PASSED
tests/test_handoff_table.py::TestSlugify::test_empty_fallback PASSED
tests/test_handoff_table.py::TestSlugify::test_punct_and_collapse PASSED
tests/test_handoff_table.py::TestValidate::test_parse_finds_three_rows PASSED
tests/test_handoff_table.py::TestValidate::test_validate_flags_one_missing PASSED
tests/test_handoff_table.py::TestValidate::test_validate_ok_when_all_filled PASSED
tests/test_handoff_table.py::TestExtract::test_extract_drops_predictions_keeps_measured_and_reused PASSED
tests/test_handoff_table.py::TestExtract::test_main_validate_exit_codes PASSED
tests/test_handoff_table.py::TestExtract::test_reused_value_and_source PASSED
tests/test_handoff_table.py::TestCLI::test_extract_subcommand PASSED
tests/test_handoff_table.py::TestCLI::test_slug_subcommand PASSED
tests/test_handoff_table.py::TestCLI::test_validate_missing_file_returns_2 PASSED
tests/test_handoff_table.py::TestPastedPrediction::test_extract_routes_pasted_prediction_to_incomplete PASSED
tests/test_handoff_table.py::TestPastedPrediction::test_validate_treats_pasted_prediction_as_unfilled PASSED
tests/test_handoff_table.py::TestUnrelatedTable::test_parse_ignores_unrelated_table PASSED
tests/test_handoff_table.py::TestPlaceholderReuse::test_extract_skips_placeholder_reuse_rows PASSED
tests/test_handoff_table.py::TestTemplate::test_template_ends_with_single_newline PASSED
tests/test_handoff_table.py::TestTemplate::test_template_parses_and_has_run_and_reuse PASSED

============================= 19 passed in 0.09s ==============================
```

**14 existing tests: all still pass. 5 new tests: 3 were RED before implementation, all GREEN after.**
