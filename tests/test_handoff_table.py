"""Tests for handoff_table.py — slug, validate, extract."""
from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import handoff_table as ht  # noqa: E402


SAMPLE_TABLE = """
## §4 Experiments

| System | Benchmark | Backbone | Metric | Expected | Actual | Status | Source |
|--------|-----------|----------|--------|----------|--------|--------|--------|
| Prior baseline X | GSM8K | Llama-3-8B | acc | 71.2 | 71.2 | REUSE | [Smith'25] |
| Ours | GSM8K | Llama-3-8B | acc | ~74.5 (pred) | ⬜ | RUN | — |
| Ours-ablate | GSM8K | Llama-3-8B | acc | ~73.0 (pred) | 73.4 | RUN | R007 |
"""


class TestSlugify(unittest.TestCase):
    def test_basic_kebab(self):
        self.assertEqual(ht.slugify("Staleness Law with Diversity"), "staleness-law-with-diversity")

    def test_punct_and_collapse(self):
        self.assertEqual(ht.slugify("Off-Policy  Reuse!! (v2)"), "off-policy-reuse-v2")

    def test_caps_length_no_trailing_dash(self):
        s = ht.slugify("a" * 50, maxlen=40)
        self.assertEqual(len(s), 40)
        self.assertFalse(s.endswith("-"))

    def test_empty_fallback(self):
        self.assertEqual(ht.slugify("   "), "untitled")
        self.assertEqual(ht.slugify("中文方向"), "untitled")


class TestValidate(unittest.TestCase):
    def test_parse_finds_three_rows(self):
        rows = ht.parse_tables(SAMPLE_TABLE)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["system"], "Prior baseline X")
        self.assertEqual(rows[1]["status"], "RUN")

    def test_validate_flags_one_missing(self):
        res = ht.validate(SAMPLE_TABLE)
        self.assertFalse(res["ok"])
        self.assertEqual(res["n_run"], 2)
        self.assertEqual(res["n_run_filled"], 1)
        self.assertEqual(res["n_reuse"], 1)
        self.assertEqual(len(res["missing"]), 1)
        self.assertEqual(res["missing"][0]["system"], "Ours")

    def test_validate_ok_when_all_filled(self):
        filled = SAMPLE_TABLE.replace("| ~74.5 (pred) | ⬜ | RUN | — |",
                                      "| ~74.5 (pred) | 75.1 | RUN | R009 |")
        res = ht.validate(filled)
        self.assertTrue(res["ok"])
        self.assertEqual(res["missing"], [])


class TestExtract(unittest.TestCase):
    def test_extract_drops_predictions_keeps_measured_and_reused(self):
        out = ht.extract(SAMPLE_TABLE)
        kinds = sorted(r["kind"] for r in out["results"])
        self.assertEqual(kinds, ["measured", "reused"])     # the ⬜ RUN row is excluded
        self.assertEqual(out["dropped_predictions"], 2)      # two RUN rows seen
        self.assertEqual(len(out["incomplete"]), 1)
        # GUARDRAIL: no predicted "(pred)" value ever appears as a result value
        for r in out["results"]:
            self.assertNotIn("pred", r["value"].lower())
            self.assertNotIn("~", r["value"])

    def test_reused_value_and_source(self):
        out = ht.extract(SAMPLE_TABLE)
        reused = [r for r in out["results"] if r["kind"] == "reused"][0]
        self.assertEqual(reused["value"], "71.2")
        self.assertEqual(reused["source"], "[Smith'25]")

    def test_main_validate_exit_codes(self):
        fd, path = tempfile.mkstemp(suffix=".md")
        os.write(fd, SAMPLE_TABLE.encode("utf-8"))
        os.close(fd)
        try:
            self.assertEqual(ht.main(["validate", path]), 1)               # has an empty RUN cell
            self.assertEqual(ht.main(["validate", path, "--allow-partial"]), 0)
        finally:
            os.unlink(path)


class TestCLI(unittest.TestCase):
    def test_slug_subcommand(self):
        with contextlib.redirect_stdout(io.StringIO()):
            result = ht.main(["slug", "Some Direction Title"])
        self.assertEqual(result, 0)

    def test_extract_subcommand(self):
        fd, path = tempfile.mkstemp(suffix=".md")
        os.write(fd, SAMPLE_TABLE.encode("utf-8"))
        os.close(fd)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                result = ht.main(["extract", path])
            self.assertEqual(result, 0)
        finally:
            os.unlink(path)

    def test_validate_missing_file_returns_2(self):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = ht.main(["validate", "definitely_nonexistent_handoff_xyz.md"])
        self.assertEqual(result, 2)


class TestPastedPrediction(unittest.TestCase):
    """Fix 1: a pasted prediction in Actual must not count as a real measured value."""

    PRED_TABLE = """
| System | Benchmark | Backbone | Metric | Expected | Actual | Status | Source |
|--------|-----------|----------|--------|----------|--------|--------|--------|
| Ours | GSM8K | Llama-3-8B | acc | ~74.5 (pred) | ~74.5 (pred) | RUN | — |
"""

    def test_validate_treats_pasted_prediction_as_unfilled(self):
        res = ht.validate(self.PRED_TABLE)
        self.assertFalse(res["ok"])
        self.assertEqual(res["n_run"], 1)
        self.assertEqual(res["n_run_filled"], 0)
        self.assertEqual(len(res["missing"]), 1)
        self.assertEqual(res["missing"][0]["system"], "Ours")

    def test_extract_routes_pasted_prediction_to_incomplete(self):
        out = ht.extract(self.PRED_TABLE)
        # must NOT appear in results
        self.assertEqual(len(out["results"]), 0)
        # must land in incomplete
        self.assertEqual(len(out["incomplete"]), 1)
        # guardrail: no result value contains pred or ~
        for r in out["results"]:
            self.assertNotIn("pred", r["value"].lower())
            self.assertNotIn("~", r["value"])


class TestUnrelatedTable(unittest.TestCase):
    """parse_tables must ignore tables whose header does not match CANON_HEADER."""

    UNRELATED = """
| Name | Age |
|------|-----|
| Alice | 30 |
"""

    def test_parse_ignores_unrelated_table(self):
        rows = ht.parse_tables(self.UNRELATED)
        self.assertEqual(len(rows), 0)


class TestPlaceholderReuse(unittest.TestCase):
    """Fix 2: REUSE rows with [value] / [val] placeholder must not be emitted."""

    PLACEHOLDER_TABLE = """
| System | Benchmark | Backbone | Metric | Expected | Actual | Status | Source |
|--------|-----------|----------|--------|----------|--------|--------|--------|
| Prior | GSM8K | Llama | acc | 70.0 | [value] | REUSE | [Author'YY] |
| Prior2 | GSM8K | Llama | acc | 70.0 | [val] | REUSE | [Author'YY] |
| Ours | GSM8K | Llama | acc | ~74.5 (pred) | 74.5 | RUN | R001 |
"""

    def test_extract_skips_placeholder_reuse_rows(self):
        out = ht.extract(self.PLACEHOLDER_TABLE)
        # placeholder REUSE rows must not appear in results
        for r in out["results"]:
            self.assertNotIn("[value]", r["value"])
            self.assertNotIn("[val]", r["value"])
        # the real RUN row must still appear as measured
        kinds = [r["kind"] for r in out["results"]]
        self.assertIn("measured", kinds)
        self.assertNotIn("reused", kinds)


class TestTemplate(unittest.TestCase):
    def test_template_parses_and_has_run_and_reuse(self):
        tpl = (Path(__file__).resolve().parents[1] / "templates" /
               "EXPERIMENT_HANDOFF_TEMPLATE.md").read_text(encoding="utf-8")
        res = ht.validate(tpl)
        self.assertGreaterEqual(res["n_run"], 1)     # at least one ⬜ row to fill
        self.assertGreaterEqual(res["n_reuse"], 1)   # at least one cited reuse row
        self.assertFalse(res["ok"])                  # template ships with unfilled RUN cells
        for anchor in ["## §1", "## §3", "## §4", "## §7"]:
            self.assertIn(anchor, tpl)

    def test_template_ends_with_single_newline(self):
        tpl_path = (Path(__file__).resolve().parents[1] / "templates" /
                    "EXPERIMENT_HANDOFF_TEMPLATE.md")
        raw = tpl_path.read_bytes()
        self.assertTrue(raw.endswith(b"\n"), "template must end with a newline")
        self.assertFalse(raw.endswith(b"\n\n"), "template must not end with two newlines")
