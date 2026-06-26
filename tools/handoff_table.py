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


CANON_HEADER = ["system", "benchmark", "backbone", "metric",
                "expected", "actual", "status", "source"]
EMPTY_ACTUAL = {"", "⬜", "todo", "tbd", "-", "—", "n/a", "...", "[value]", "[val]"}


def _looks_like_prediction(value: str) -> bool:
    """A measured Actual must not be a leftover prediction (e.g. '~74.5 (pred)')."""
    v = value.strip().lower()
    return "(pred)" in v or v.startswith("~")


def _split_row(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _is_separator(cells: list[str]) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", c.replace(" ", "")) for c in cells)


def parse_tables(md_text: str) -> list[dict]:
    """Return data rows of every markdown table whose header matches CANON_HEADER."""
    rows: list[dict] = []
    lines = md_text.splitlines()
    i, n = 0, len(lines)
    while i < n:
        if "|" in lines[i] and [c.lower() for c in _split_row(lines[i])] == CANON_HEADER:
            if i + 1 < n and "|" in lines[i + 1] and _is_separator(_split_row(lines[i + 1])):
                j = i + 2
                while j < n and "|" in lines[j]:
                    dc = _split_row(lines[j])
                    if not _is_separator(dc) and len(dc) >= len(CANON_HEADER):
                        row = dict(zip(CANON_HEADER, dc[:len(CANON_HEADER)]))
                        row["line"] = j + 1
                        rows.append(row)
                    j += 1
                i = j
                continue
        i += 1
    return rows


def validate(md_text: str) -> dict:
    n_run = n_run_filled = n_reuse = 0
    missing: list[dict] = []
    for r in parse_tables(md_text):
        status = r["status"].strip().lower()
        actual = r["actual"].strip()
        is_empty = actual.lower() in EMPTY_ACTUAL
        is_pred = _looks_like_prediction(actual)
        if status == "reuse":
            n_reuse += 1
        elif status == "run":
            n_run += 1
            if is_empty or is_pred:
                missing.append({"system": r["system"], "benchmark": r["benchmark"],
                                "metric": r["metric"], "line": r["line"]})
            else:
                n_run_filled += 1
    return {"ok": n_run_filled == n_run, "n_run": n_run,
            "n_run_filled": n_run_filled, "n_reuse": n_reuse, "missing": missing}


def extract(md_text: str) -> dict:
    results: list[dict] = []
    incomplete: list[dict] = []
    dropped = 0
    for r in parse_tables(md_text):
        status = r["status"].strip().lower()
        actual = r["actual"].strip()
        is_empty = actual.lower() in EMPTY_ACTUAL
        base = {"system": r["system"], "benchmark": r["benchmark"],
                "backbone": r["backbone"], "metric": r["metric"], "source": r["source"]}
        if status == "reuse":
            # Fix 2: skip unfilled placeholder reuse rows entirely
            if not is_empty:
                results.append({**base, "value": actual, "kind": "reused"})
        elif status == "run":
            dropped += 1  # the predicted Expected is intentionally discarded
            if is_empty or _looks_like_prediction(actual):
                # Fix 1: prediction-looking actual routes to incomplete, not measured
                incomplete.append({**base, "line": r["line"]})
            else:
                results.append({**base, "value": actual, "kind": "measured"})
    return {"results": results, "incomplete": incomplete, "dropped_predictions": dropped}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="experiment-handoff table helper")
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("slug")
    sp.add_argument("direction")
    sp.add_argument("--maxlen", type=int, default=40)
    vp = sub.add_parser("validate")
    vp.add_argument("path")
    vp.add_argument("--allow-partial", action="store_true")
    ep = sub.add_parser("extract")
    ep.add_argument("path")
    args = p.parse_args(argv)

    if args.cmd == "slug":
        print(slugify(args.direction, args.maxlen))
        return 0
    try:
        text = Path(args.path).read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"error: file not found: {args.path}", file=sys.stderr)
        return 2
    if args.cmd == "validate":
        res = validate(text)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if (res["ok"] or args.allow_partial) else 1
    if args.cmd == "extract":
        print(json.dumps(extract(text), ensure_ascii=False, indent=2))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
