#!/usr/bin/env python3
"""handoff_table.py — deterministic helper for the experiment-handoff workflow.

Owns three pieces of logic the SKILL.md prose must NOT hand-roll:
  1. slug   — derive research-projects/<slug>/ from a direction title.
  2. validate — confirm every RUN row in a handoff doc has its Actual filled.
  3. extract  — produce measured/cited results, NEVER emitting predicted numbers.

Usage:
    python3 handoff_table.py slug "<direction>" [--maxlen 40]
    python3 handoff_table.py validate <handoff.md> [--allow-partial]
    python3 handoff_table.py extract  <handoff.md>
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def slugify(direction: str, maxlen: int = 40) -> str:
    s = direction.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    if len(s) > maxlen:
        s = s[:maxlen].rstrip("-")
    return s or "untitled"
