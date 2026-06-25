"""Tests for handoff_table.py — slug, validate, extract."""
from __future__ import annotations

import sys
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
