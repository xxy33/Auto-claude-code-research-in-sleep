"""Tests for handoff_table.py — slug, validate, extract."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import handoff_table as ht  # noqa: E402


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
