# Experiment Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a human-in-the-loop experiment workflow to ARIS — ARIS plans experiments + emits a self-contained fill-in-the-blank handoff package, a colleague runs them and fills in measured numbers, ARIS ingests the returned file and writes the paper.

**Architecture:** Two new Markdown skills (`experiment-handoff` emit side, `handoff-intake` intake side) compose existing ARIS skills (`/research-lit`, `/experiment-plan`, `/paper-writing`). One tested Python helper (`tools/handoff_table.py`) owns the deterministic logic: slug derivation, handoff-table completeness validation, and predicted-vs-actual results extraction. A new template defines the deliverable's exact shape. Per-direction artifacts live under `research-projects/<slug>/`.

**Tech Stack:** Python 3.8+ stdlib only (argparse, re, json, pathlib), `unittest` tests, Markdown SKILL.md files following ARIS conventions.

## Global Constraints

- **Python 3.8+, stdlib only** — no third-party imports in `tools/handoff_table.py`. Start the module with `from __future__ import annotations`.
- **Tests are `unittest.TestCase`** in `tests/test_handoff_table.py`; import the helper via `sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))` then `import handoff_table`. Run with `python -m pytest tests/test_handoff_table.py -v` (pytest runs unittest classes; fallback `python -m unittest tests.test_handoff_table -v`).
- **Canonical handoff results-table header (exact, lowercased match drives parsing):** `System | Benchmark | Backbone | Metric | Expected | Actual | Status | Source`. This refines design-spec §6's single "Run? / Source" column into two columns (`Status` ∈ {RUN, REUSE} + `Source`) for deterministic parsing.
- **Empty-Actual markers** (lowercased, stripped): `"", "⬜", "todo", "tbd", "-", "—", "n/a", "..."`.
- **GUARDRAIL — predictions must never become results:** the `Expected` column holds predicted numbers tagged `(pred)`; `extract()` MUST NOT emit a RUN row's `Expected` value as a result. Only `Actual` (measured) and `REUSE` (cited) values are emitted.
- **Workspace:** all per-direction artifacts under `research-projects/<slug>/`; `research-wiki/` stays shared at repo root.
- **Helper resolution in SKILL.md** uses the canonical strict-safe chain `.aris/tools/handoff_table.py → tools/handoff_table.py → $ARIS_REPO/tools/handoff_table.py` (per `skills/shared-references/integration-contract.md` §2); never hardcode `python3 tools/handoff_table.py`.
- **Inside SKILL bash blocks use `python3`**; for local dev/test commands on Windows use `python`.
- **Frequent commits** — one per task.

---

### Task 1: `handoff_table.py` — slug derivation

**Files:**
- Create: `tools/handoff_table.py`
- Test: `tests/test_handoff_table.py`

**Interfaces:**
- Produces: `slugify(direction: str, maxlen: int = 40) -> str` — lowercase kebab-case, non-alnum runs → `-`, collapse repeats, trim, cap length; returns `"untitled"` if empty.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_handoff_table.py::TestSlugify -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'handoff_table'`

- [ ] **Step 3: Write minimal implementation**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_handoff_table.py::TestSlugify -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add tools/handoff_table.py tests/test_handoff_table.py
git commit -m "feat(handoff): add handoff_table.py slugify with tests"
```

---

### Task 2: Table parsing + `validate`

**Files:**
- Modify: `tools/handoff_table.py`
- Test: `tests/test_handoff_table.py`

**Interfaces:**
- Consumes: `slugify` (Task 1).
- Produces:
  - `CANON_HEADER: list[str]` = `["system","benchmark","backbone","metric","expected","actual","status","source"]`
  - `EMPTY_ACTUAL: set[str]`
  - `parse_tables(md_text: str) -> list[dict]` — each row a dict with the 8 header keys (lowercased keys) plus `"line": int` (1-based line number of the data row).
  - `validate(md_text: str) -> dict` = `{"ok": bool, "n_run": int, "n_run_filled": int, "n_reuse": int, "missing": list[dict]}`; each `missing` entry `{"system","benchmark","metric","line"}`.

- [ ] **Step 1: Write the failing test**

```python
SAMPLE_TABLE = """
## §4 Experiments

| System | Benchmark | Backbone | Metric | Expected | Actual | Status | Source |
|--------|-----------|----------|--------|----------|--------|--------|--------|
| Prior baseline X | GSM8K | Llama-3-8B | acc | 71.2 | 71.2 | REUSE | [Smith'25] |
| Ours | GSM8K | Llama-3-8B | acc | ~74.5 (pred) | ⬜ | RUN | — |
| Ours-ablate | GSM8K | Llama-3-8B | acc | ~73.0 (pred) | 73.4 | RUN | R007 |
"""


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_handoff_table.py::TestValidate -v`
Expected: FAIL — `AttributeError: module 'handoff_table' has no attribute 'parse_tables'`

- [ ] **Step 3: Write minimal implementation**

Append to `tools/handoff_table.py` (after `slugify`):

```python
CANON_HEADER = ["system", "benchmark", "backbone", "metric",
                "expected", "actual", "status", "source"]
EMPTY_ACTUAL = {"", "⬜", "todo", "tbd", "-", "—", "n/a", "..."}


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
        is_empty = r["actual"].strip().lower() in EMPTY_ACTUAL
        if status == "reuse":
            n_reuse += 1
        elif status == "run":
            n_run += 1
            if is_empty:
                missing.append({"system": r["system"], "benchmark": r["benchmark"],
                                "metric": r["metric"], "line": r["line"]})
            else:
                n_run_filled += 1
    return {"ok": n_run_filled == n_run, "n_run": n_run,
            "n_run_filled": n_run_filled, "n_reuse": n_reuse, "missing": missing}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_handoff_table.py::TestValidate -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add tools/handoff_table.py tests/test_handoff_table.py
git commit -m "feat(handoff): markdown table parsing + RUN-row completeness validation"
```

---

### Task 3: `extract` — measured/cited results, predictions dropped

**Files:**
- Modify: `tools/handoff_table.py` (add `extract` + argparse `main`)
- Test: `tests/test_handoff_table.py`

**Interfaces:**
- Consumes: `parse_tables`, `EMPTY_ACTUAL` (Task 2).
- Produces:
  - `extract(md_text: str) -> dict` = `{"results": list[dict], "incomplete": list[dict], "dropped_predictions": int}`. Each result `{"system","benchmark","backbone","metric","value","kind","source"}` where `kind ∈ {"measured","reused"}`. RUN rows contribute their `Actual` as `measured`; REUSE rows contribute their `Actual` (the cited number) as `reused`; the predicted `Expected` of a RUN row is NEVER placed in `value`. `dropped_predictions` counts RUN rows seen (whose `Expected` prediction was discarded). Empty RUN rows go to `incomplete` (with `line`), not `results`.
  - `main(argv: list[str] | None = None) -> int` — argparse with `slug` / `validate` / `extract`; `validate` exits non-zero when not ok unless `--allow-partial`.

- [ ] **Step 1: Write the failing test**

```python
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
        import tempfile, os
        fd, path = tempfile.mkstemp(suffix=".md")
        os.write(fd, SAMPLE_TABLE.encode("utf-8"))
        os.close(fd)
        try:
            self.assertEqual(ht.main(["validate", path]), 1)               # has an empty RUN cell
            self.assertEqual(ht.main(["validate", path, "--allow-partial"]), 0)
        finally:
            os.unlink(path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_handoff_table.py::TestExtract -v`
Expected: FAIL — `AttributeError: module 'handoff_table' has no attribute 'extract'`

- [ ] **Step 3: Write minimal implementation**

Append to `tools/handoff_table.py`:

```python
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
            results.append({**base, "value": actual, "kind": "reused"})
        elif status == "run":
            dropped += 1  # the predicted Expected is intentionally discarded
            if is_empty:
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
    text = Path(args.path).read_text(encoding="utf-8")
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
```

- [ ] **Step 4: Run the full helper test suite**

Run: `python -m pytest tests/test_handoff_table.py -v`
Expected: PASS (all classes: TestSlugify, TestValidate, TestExtract)

- [ ] **Step 5: Commit**

```bash
git add tools/handoff_table.py tests/test_handoff_table.py
git commit -m "feat(handoff): results extraction (drops predictions) + CLI"
```

---

### Task 4: `EXPERIMENT_HANDOFF_TEMPLATE.md`

**Files:**
- Create: `templates/EXPERIMENT_HANDOFF_TEMPLATE.md`
- Test: `tests/test_handoff_table.py` (add `TestTemplate`)

**Interfaces:**
- Consumes: `validate` (Task 2) — the test parses the template's example tables to keep template and helper in lockstep.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_handoff_table.py::TestTemplate -v`
Expected: FAIL — `FileNotFoundError` (template not created yet)

- [ ] **Step 3: Create the template**

Write `templates/EXPERIMENT_HANDOFF_TEMPLATE.md` with exactly this content:

````markdown
# Experiment Handoff — [Project / Direction Title]

> **For the colleague running the experiments.** Fill in only the ⬜ cells in the
> `Actual` column for rows whose `Status` is `RUN`. Leave `REUSE` rows untouched
> (their numbers are cited from prior papers). Note any config deviation in the
> row's `Source`/Notes. When done, save and return this same file.
>
> `Expected` numbers tagged `(pred)` are **our predictions, not measurements** —
> they are only there to set expectations and are dropped automatically when we
> ingest your results.

**Slug / workspace:** `research-projects/<slug>/`
**Method thesis:** [one sentence]
**Target venue:** [venue]
**Compute assumed:** [e.g. 8×A800 80GB, BF16]

## §1 Project Background

[Self-contained background a colleague who did NOT plan this can execute from:
the problem, why it matters, the method in plain language, and what these
experiments are meant to show. No internal jargon-only references.]

## §2 Claims

- **C1:** [the main claim the experiments defend]
- **C2 (optional):** [supporting claim]

## §3 Reusable Baseline Ledger (cited — do NOT re-run)

These numbers are reused from prior work because they share our exact
**benchmark + backbone + split + metric**. They are pre-filled and locked.

| Method | Benchmark | Backbone | Split | Metric | Value | Citation |
|--------|-----------|----------|-------|--------|-------|----------|
| [Prior method] | [bench] | [backbone] | [split] | [metric] | [value] | [Author'YY] [arXiv id] |

## §4 Experiments to Run

One table per experiment block. `Status` = `RUN` (you run it, fill `Actual`) or
`REUSE` (cited above, already filled). `Expected` is our prediction `(pred)`.

### Block 1: [Main result]

| System | Benchmark | Backbone | Metric | Expected | Actual | Status | Source |
|--------|-----------|----------|--------|----------|--------|--------|--------|
| [Prior baseline] | [bench] | [backbone] | [metric] | [value] | [value] | REUSE | [Author'YY] |
| Ours | [bench] | [backbone] | [metric] | [~val (pred)] | ⬜ | RUN | — |

### Block 2: [Ablation]

| System | Benchmark | Backbone | Metric | Expected | Actual | Status | Source |
|--------|-----------|----------|--------|----------|--------|--------|--------|
| Ours − [component] | [bench] | [backbone] | [metric] | [~val (pred)] | ⬜ | RUN | — |

## §5 Run Specs (per RUN row)

For each `RUN` row above, the colleague needs:

- **[Block 1 / Ours]** — dataset/split: […]; backbone: […]; key hyperparameters:
  […]; seeds: […]; success criterion: […]; rough compute/runtime: […].
- **[Block 2 / Ours − component]** — […].

## §6 How to Fill This In

1. Run each `RUN` row's experiment per §5.
2. Put the measured number in that row's `Actual` cell (replace the ⬜).
3. Do **not** edit `REUSE` rows.
4. Note deviations (different seed, OOM workaround, …) in `Source`.
5. Save and return this file.

## §7 Prediction Disclaimer

`Expected (pred)` values are model-estimated expectations, **not** experimental
results. They are dropped at ingestion and never appear in the paper as
measured numbers.
````

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_handoff_table.py::TestTemplate -v`
Expected: PASS (template has ≥2 RUN ⬜ rows + ≥1 REUSE row, all anchors present)

- [ ] **Step 5: Commit**

```bash
git add templates/EXPERIMENT_HANDOFF_TEMPLATE.md tests/test_handoff_table.py
git commit -m "feat(handoff): add EXPERIMENT_HANDOFF template (helper-validated)"
```

---

### Task 5: `experiment-handoff` skill (emit side)

**Files:**
- Create: `skills/experiment-handoff/SKILL.md`

**Interfaces:**
- Consumes: `tools/handoff_table.py slug` (Task 3), `templates/EXPERIMENT_HANDOFF_TEMPLATE.md` (Task 4), and composes existing `/idea-discovery`, `/novelty-check`, `/research-lit`, `/experiment-plan`.

- [ ] **Step 1: Create the skill file**

Write `skills/experiment-handoff/SKILL.md` with exactly this content:

````markdown
---
name: experiment-handoff
description: 'Workflow 1.5-H: plan experiments and emit a self-contained human handoff package (background + fill-in-the-blank results table with predicted numbers and cited reusable baselines) for a colleague to run. Use when user says "实验交接", "交给同事跑实验", "experiment handoff", "出实验交接单", "plan experiments for someone else to run", or wants to plan + write while a human runs the experiments.'
argument-hint: [method-or-direction]
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, Skill, mcp__codex__codex, mcp__codex__codex-reply
---

# Workflow 1.5-H: Experiment Handoff (emit side)

Plan and package experiments for a human colleague: **$ARGUMENTS**

## Overview

This skill replaces machine execution (`/experiment-bridge`) with a human
handoff. It surveys the literature (reusing prior baseline numbers that share
our benchmark + backbone), plans the experiments, and emits one self-contained
`EXPERIMENT_HANDOFF.md` a colleague can execute from. After they fill it in and
return it, `/handoff-intake` ingests it and writes the paper.

```
/experiment-handoff "method or direction" [— discover: true]
  → research-projects/<slug>/EXPERIMENT_HANDOFF.md   ──hand to colleague──▶  /handoff-intake
```

## Constants

- **DISCOVER = false** — When `true`, prepend `/idea-discovery` + `/novelty-check` before planning. Override: `/experiment-handoff "direction" — discover: true`.
- **REUSE_VERIFY = true** — Cross-model (Codex MCP) verification of each high-stakes `REUSE` claim before it is locked. Set `false` to skip.
- **SLUG = (auto)** — Workspace name; auto-derived from the direction. Override: `— slug: my-name`.

## Workspace resolution

Resolve the per-direction workspace and the helper via the canonical chain:

```bash
cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" || exit 1
if [ -z "${ARIS_REPO:-}" ] && [ -f .aris/installed-skills.txt ]; then
  ARIS_REPO=$(awk -F'\t' '$1=="repo_root"{print $2; exit}' .aris/installed-skills.txt 2>/dev/null) || true
fi
HANDOFF_TOOL=".aris/tools/handoff_table.py"
[ -f "$HANDOFF_TOOL" ] || HANDOFF_TOOL="tools/handoff_table.py"
[ -f "$HANDOFF_TOOL" ] || { [ -n "${ARIS_REPO:-}" ] && HANDOFF_TOOL="$ARIS_REPO/tools/handoff_table.py"; }
[ -f "$HANDOFF_TOOL" ] || { echo "WARN: handoff_table.py unresolved; deriving slug manually." >&2; HANDOFF_TOOL=""; }

SLUG="${SLUG:-}"
if [ -z "$SLUG" ] && [ -n "$HANDOFF_TOOL" ]; then
  SLUG=$(python3 "$HANDOFF_TOOL" slug "DIRECTION_TEXT")
fi
WORKSPACE="research-projects/$SLUG"
mkdir -p "$WORKSPACE/refine-logs"
echo "Workspace: $WORKSPACE"
```

(Replace `DIRECTION_TEXT` with the user's direction. If `— slug:` was given, set `SLUG` from it and skip derivation. If the workspace already exists, reuse it — this is resume-friendly.)

## Workflow

### Phase 1 — Establish the method
- If `DISCOVER = true`: run `/idea-discovery "$ARGUMENTS"` then `/novelty-check`, writing into `research-projects/<slug>/idea-stage/`. Pick the top candidate as the method.
- Else: use the user-provided method, or read `research-projects/<slug>/refine-logs/FINAL_PROPOSAL.md` if it exists.

### Phase 2 — Reuse-aware survey
Pin the target **benchmark(s) + backbone(s) + split + metric** from the method. Then:
1. Run `/research-lit "<topic, focused on those benchmarks/backbones>"` to gather prior work.
2. For each prior result, extract `(method, benchmark, split, backbone, metric, value, citation)`.
3. **Reuse-eligibility gate:** a number is reusable ONLY if benchmark AND backbone AND split AND metric all match ours. Otherwise it becomes a `RUN` row. List every mismatch with its reason.
4. **If `REUSE_VERIFY = true`:** for each candidate `REUSE` number, ask Codex MCP to confirm the source paper really used that benchmark+backbone and that the value is transcribed correctly. Lock only verified numbers; mark unconfirmed ones `REUSE (unverified)`. Degrade gracefully (skip) if Codex MCP is unavailable.

Write the ledger to `research-projects/<slug>/refine-logs/REUSABLE_BASELINES.md`.

### Phase 3 — Experiment planning
Run `/experiment-plan` for the method, rooted at the workspace (its `refine-logs/` outputs go under `research-projects/<slug>/refine-logs/`). This yields the claims, experiment blocks, configs, and run order.

### Phase 4 — Emit the handoff package
Render `research-projects/<slug>/EXPERIMENT_HANDOFF.md` from
`templates/EXPERIMENT_HANDOFF_TEMPLATE.md` (resolve the template via the same
`.aris/tools → tools → $ARIS_REPO` chain, swapping `tools/` for `templates/`):
- **§1 Background** — self-contained, plain-language.
- **§2 Claims** — from `/experiment-plan`.
- **§3 Reusable Baseline Ledger** — from Phase 2, cited + locked.
- **§4 Experiment tables** — one per block; `REUSE` rows pre-filled from §3; `RUN` rows get a **predicted `Expected` tagged `(pred)`** and an empty `⬜ Actual`. Predictions should be anchored to the closest literature numbers, not invented freely.
- **§5 Run specs**, **§6 instructions**, **§7 disclaimer** — per template.

Keep the canonical header exactly: `System | Benchmark | Backbone | Metric | Expected | Actual | Status | Source`.

### Phase 5 — Self-check
Run the helper to confirm the emitted file is well-formed:

```bash
python3 "$HANDOFF_TOOL" validate "$WORKSPACE/EXPERIMENT_HANDOFF.md" --allow-partial
```

Expect `ok=false` with `n_run > 0` and the intended `n_reuse` (it ships unfilled by design). If `n_run` is 0 or no tables parse, the table header drifted — fix it.

### Phase 6 — Summarize
Tell the user:
```
🧾 Handoff package ready: research-projects/<slug>/EXPERIMENT_HANDOFF.md
- RUN rows (colleague fills): [n_run]
- REUSE rows (cited, locked): [n_reuse]
Send this file to the colleague. When they return it:
→ /handoff-intake "research-projects/<slug>/EXPERIMENT_HANDOFF.md"
```

## Output Protocols

> Follow these shared protocols for all output files:
> - **[Output Versioning Protocol](../shared-references/output-versioning.md)**
> - **[Output Manifest Protocol](../shared-references/output-manifest.md)**
> - **[Output Language Protocol](../shared-references/output-language.md)**

## Key Rules

- **GUARDRAIL — predictions are not results.** Predicted numbers live ONLY in the `Expected` column, always tagged `(pred)`. Never write a predicted number into a results file, tracker, or the paper. The only path to writing is `/handoff-intake`, which drops them.
- **Reuse only on exact match.** A baseline number is `REUSE` only if benchmark AND backbone AND split AND metric match ours; otherwise it is `RUN`. When in doubt, mark `RUN`.
- **Self-contained deliverable.** §1 must let a colleague who never saw the planning execute the experiments. No ARIS-internal references.
- **One workspace per direction.** All artifacts under `research-projects/<slug>/`; never write to repo-root `refine-logs/`.
- **Do not run experiments.** This skill plans and packages only.

## Composing with Other Skills

```
/idea-discovery "direction"     ← optional (— discover: true)
/experiment-handoff "method"    ← you are here (emit handoff package)
   … colleague runs experiments, fills the file, returns it …
/handoff-intake "…HANDOFF.md"   ← ingest results → write the paper
```
````

- [ ] **Step 2: Verify frontmatter + helper-resolution lint**

Run:
```bash
python -c "import re,sys; t=open('skills/experiment-handoff/SKILL.md',encoding='utf-8').read(); m=re.match(r'^---\n.*?\n---\n', t, re.DOTALL); print('frontmatter OK' if m and 'name: experiment-handoff' in m.group(0) else 'FRONTMATTER BAD'); sys.exit(0 if m else 1)"
bash tools/lint_skills_helpers.sh | grep -i experiment-handoff || echo "no hardcoded-helper findings (good)"
```
Expected: `frontmatter OK`, and no lint finding for this skill (it uses the resolver chain).

- [ ] **Step 3: Commit**

```bash
git add skills/experiment-handoff/SKILL.md
git commit -m "feat(handoff): add experiment-handoff skill (emit side)"
```

---

### Task 6: `handoff-intake` skill (intake side)

**Files:**
- Create: `skills/handoff-intake/SKILL.md`

**Interfaces:**
- Consumes: `tools/handoff_table.py validate|extract` (Tasks 2–3); composes `/paper-writing`, `/auto-paper-improvement-loop`.

- [ ] **Step 1: Create the skill file**

Write `skills/handoff-intake/SKILL.md` with exactly this content:

````markdown
---
name: handoff-intake
description: 'Ingest a colleague-filled EXPERIMENT_HANDOFF.md: validate every RUN row has a measured result, drop predicted numbers, then chain into paper writing + polishing. Use when user says "收回实验结果", "同事填完了", "handoff intake", "ingest results", "结果回来了写论文", or returns a filled experiment handoff file.'
argument-hint: [handoff-md-path-or-slug]
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, Skill, mcp__codex__codex, mcp__codex__codex-reply
---

# Handoff Intake (intake side)

Ingest the colleague's returned handoff file and write the paper: **$ARGUMENTS**

## Overview

The counterpart to `/experiment-handoff`. It reads the filled
`EXPERIMENT_HANDOFF.md`, confirms every `RUN` row has a measured `Actual`,
extracts a clean measured-results table (predictions discarded by
construction), then hands off to the existing writing pipeline.

## Constants

- **ALLOW_PARTIAL = false** — When `false`, refuse to proceed if any `RUN` row's `Actual` is unfilled. Override: `— allow-partial: true`.
- **RESULTS_REVIEW = true** — Cross-model (Codex MCP) sanity review of the results interpretation before writing. Set `false` to skip.

## Workspace + helper resolution

```bash
cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" || exit 1
if [ -z "${ARIS_REPO:-}" ] && [ -f .aris/installed-skills.txt ]; then
  ARIS_REPO=$(awk -F'\t' '$1=="repo_root"{print $2; exit}' .aris/installed-skills.txt 2>/dev/null) || true
fi
HANDOFF_TOOL=".aris/tools/handoff_table.py"
[ -f "$HANDOFF_TOOL" ] || HANDOFF_TOOL="tools/handoff_table.py"
[ -f "$HANDOFF_TOOL" ] || { [ -n "${ARIS_REPO:-}" ] && HANDOFF_TOOL="$ARIS_REPO/tools/handoff_table.py"; }
[ -f "$HANDOFF_TOOL" ] || { echo "ERROR: handoff_table.py unresolved; cannot validate results." >&2; exit 1; }

# $ARGUMENTS is either a path to EXPERIMENT_HANDOFF.md or a bare <slug>.
HANDOFF="$ARGUMENTS"
[ -f "$HANDOFF" ] || HANDOFF="research-projects/$ARGUMENTS/EXPERIMENT_HANDOFF.md"
[ -f "$HANDOFF" ] || { echo "ERROR: handoff file not found: $HANDOFF" >&2; exit 1; }
WORKSPACE="$(dirname "$HANDOFF")"
```

## Workflow

### Phase 1 — Validate completeness

```bash
python3 "$HANDOFF_TOOL" validate "$HANDOFF"   # add --allow-partial if ALLOW_PARTIAL=true
```

- Exit 0 → all `RUN` rows filled; proceed.
- Exit 1 → list the `missing` rows from the JSON and **stop**, unless `ALLOW_PARTIAL = true` (then proceed with whatever is filled and clearly note the gaps to the writer).

### Phase 2 — Extract measured results

```bash
python3 "$HANDOFF_TOOL" extract "$HANDOFF" > "$WORKSPACE/refine-logs/MEASURED_RESULTS.json"
```

This JSON contains only `measured` (RUN `Actual`) and `reused` (cited) values —
predicted numbers are dropped. `incomplete` lists any empty RUN rows (present
only under `--allow-partial`).

### Phase 3 — Surprise check
Compare each measured `Actual` against its `Expected (pred)` in the file. Flag
any large gap (e.g. method underperforms its prediction or a baseline beats us)
as a point the paper must address **honestly** — never paper over a negative.

### Phase 4 — (optional) cross-model results review
If `RESULTS_REVIEW = true`, send the measured-results table + claims to Codex
MCP for a sanity read: are the claims still supported? any obvious confound?
Degrade gracefully if Codex MCP is unavailable.

### Phase 5 — Write & polish
Chain into the existing pipeline, rooted at the workspace, passing ONLY the
measured/cited numbers from `MEASURED_RESULTS.json`:

```
/paper-writing "research-projects/<slug>/"      # narrative → LaTeX → PDF
/auto-paper-improvement-loop                     # multi-round review polish
```

Output the paper under `research-projects/<slug>/paper/`.

### Phase 6 — Summarize
```
✅ Intake complete for research-projects/<slug>/
- RUN results ingested: [n], Reused (cited): [m], Predictions dropped: [k]
- Surprises flagged: [list]
- Paper: research-projects/<slug>/paper/
```

## Output Protocols

> - **[Output Versioning Protocol](../shared-references/output-versioning.md)**
> - **[Output Manifest Protocol](../shared-references/output-manifest.md)**
> - **[Output Language Protocol](../shared-references/output-language.md)**

## Key Rules

- **GUARDRAIL — predictions never become results.** Build the results table ONLY from `extract`'s output (measured + cited). Never pull a number from the `Expected (pred)` column into the paper.
- **Block on incompleteness by default.** Do not write a paper on half-run experiments unless the user explicitly passes `— allow-partial: true`.
- **Be honest about surprises.** A measured result that contradicts the prediction is a finding to report, not to hide.
- **Stay in the workspace.** Read and write under `research-projects/<slug>/`.

## Composing with Other Skills

```
/experiment-handoff "method"   ← emit the package
   … colleague fills & returns EXPERIMENT_HANDOFF.md …
/handoff-intake "…HANDOFF.md"  ← you are here (validate → extract → write)
/paper-writing · /auto-paper-improvement-loop   ← invoked internally
```
````

- [ ] **Step 2: Verify frontmatter + lint**

Run:
```bash
python -c "import re,sys; t=open('skills/handoff-intake/SKILL.md',encoding='utf-8').read(); m=re.match(r'^---\n.*?\n---\n', t, re.DOTALL); print('frontmatter OK' if m and 'name: handoff-intake' in m.group(0) else 'FRONTMATTER BAD'); sys.exit(0 if m else 1)"
bash tools/lint_skills_helpers.sh | grep -i handoff-intake || echo "no hardcoded-helper findings (good)"
```
Expected: `frontmatter OK`, no lint finding for this skill.

- [ ] **Step 3: Commit**

```bash
git add skills/handoff-intake/SKILL.md
git commit -m "feat(handoff): add handoff-intake skill (intake side)"
```

---

### Task 7: Minimal usage docs + composing notes

These edits make the workflow discoverable WITHOUT changing the live skill-count
patterns (those are bumped only in the optional Task 9). Add command lines and
composing notes inside existing sections; do NOT add a new numbered `## N.` H2
to either README (the inventory check pins both at 16).

**Files:**
- Modify: `SETUP_GUIDE.md` (the "ready to use" command list near the end), `SETUP_GUIDE_CN.md` (same spot)
- Modify: `skills/experiment-bridge/SKILL.md` (Composing section), `skills/experiment-plan/SKILL.md` (Composing section)

- [ ] **Step 1: Add to `SETUP_GUIDE.md` workflow list**

In the closing ```` ``` ```` workflow block of `SETUP_GUIDE.md` (the one listing `/idea-discovery`, `/experiment-bridge`, …), add after the `/experiment-bridge` line:

```
> /experiment-handoff "method or direction"          # Workflow 1.5-H — plan + emit a human handoff package (colleague runs experiments)
> /handoff-intake "research-projects/<slug>/EXPERIMENT_HANDOFF.md"  # ingest filled results → write paper
```

- [ ] **Step 2: Mirror the same two lines into `SETUP_GUIDE_CN.md`**

Find the equivalent command list in `SETUP_GUIDE_CN.md` and add:

```
> /experiment-handoff "方法或方向"                    # 工作流 1.5-H — 规划并生成给同事的实验交接单
> /handoff-intake "research-projects/<slug>/EXPERIMENT_HANDOFF.md"  # 收回填好的结果 → 写论文
```

- [ ] **Step 3: Add composing notes to the two existing skills**

In `skills/experiment-bridge/SKILL.md`, in its "Composing with Other Skills" block, add a line:
```
/experiment-handoff "method"         ← human-run alternative to this bridge (colleague runs experiments)
```

In `skills/experiment-plan/SKILL.md`, in its "Composing with Other Skills" block, add a line:
```
/experiment-handoff   -> package the plan as a human handoff (colleague runs it)
```

- [ ] **Step 4: Verify the docs reference the real commands**

Run:
```bash
grep -c "experiment-handoff" SETUP_GUIDE.md SETUP_GUIDE_CN.md skills/experiment-bridge/SKILL.md skills/experiment-plan/SKILL.md
```
Expected: each file reports ≥1.

- [ ] **Step 5: Commit**

```bash
git add SETUP_GUIDE.md SETUP_GUIDE_CN.md skills/experiment-bridge/SKILL.md skills/experiment-plan/SKILL.md
git commit -m "docs(handoff): make experiment-handoff discoverable in setup guides + composing notes"
```

---

### Task 8: Integration verification (dry run on a real proposal)

No new code — prove the pieces work end-to-end on one real proposal, without
running any experiment.

**Files:** none (verification only)

- [ ] **Step 1: Full helper test suite green**

Run: `python -m pytest tests/test_handoff_table.py -v`
Expected: PASS (TestSlugify, TestValidate, TestExtract, TestTemplate).

- [ ] **Step 2: Derive a slug for proposal 01**

Run: `python tools/handoff_table.py slug "Predictive Staleness Law for Asynchronous Off-Policy GRPO"`
Expected: prints `predictive-staleness-law-for-asynchronous` (≤40 chars, no trailing dash).

- [ ] **Step 3: Stage proposal 01 into a workspace**

```bash
mkdir -p research-projects/staleness-law/refine-logs
cp "C:/Users/v-xiaoyuc/Desktop/x/github/Idea_discovery/01-staleness-law-with-diversity/PROPOSAL.md" research-projects/staleness-law/refine-logs/FINAL_PROPOSAL.md
```

- [ ] **Step 4: Hand-emit a tiny handoff file from the template and validate it**

Copy the template to the workspace, fill §4 Block 1 with one REUSE row (e.g. AReaL `2505.24298`, matching benchmark+backbone) and one `RUN` ⬜ row, then:

```bash
cp templates/EXPERIMENT_HANDOFF_TEMPLATE.md research-projects/staleness-law/EXPERIMENT_HANDOFF.md
# (edit §4 to have 1 REUSE + 1 RUN ⬜ row as above)
python tools/handoff_table.py validate research-projects/staleness-law/EXPERIMENT_HANDOFF.md
```
Expected: JSON with `"ok": false`, `"n_run": 1`, `"n_reuse": 1`, one `missing` entry (exit code 1).

- [ ] **Step 5: Simulate the colleague filling it, then extract**

Replace that row's `⬜` with a number, then:
```bash
python tools/handoff_table.py validate research-projects/staleness-law/EXPERIMENT_HANDOFF.md   # expect ok:true, exit 0
python tools/handoff_table.py extract  research-projects/staleness-law/EXPERIMENT_HANDOFF.md
```
Expected: `validate` ok; `extract` shows one `measured` + one `reused` result, `dropped_predictions: 1`, and NO `(pred)` / `~` string in any result `value`.

- [ ] **Step 6: Clean up the scratch workspace and commit nothing**

```bash
rm -rf research-projects/staleness-law
```
(The real run happens later via the live skills; this task only proves the plumbing.)

- [ ] **Step 7: Record verification result**

No commit. Report PASS/FAIL of steps 1–5 to the reviewer.

---

### Task 9 (OPTIONAL — only to make `check_skills_inventory.py` green for upstreaming)

The two new skills are fully usable after Task 6 (Claude Code auto-discovers them
from `skills/`). This task ONLY satisfies the repo's inventory-parity CI gate,
which requires: a Codex mirror per skill, a catalog entry per skill, and the
skill **count** bumped (+2) across every count-bearing doc. Skip for personal
use; do it before opening an upstream PR.

**Files:**
- Create: `skills/skills-codex/experiment-handoff/SKILL.md`, `skills/skills-codex/handoff-intake/SKILL.md`
- Modify: `docs/SKILLS_CATALOG.md`, `README.md`, `README_CN.md`, `AGENT_GUIDE.md`, `docs/ARIS_INTRO.md`, `docs/ARIS_INTRO.html`, `skills/skills-codex/README.md`, `skills/skills-codex/README_CN.md`

- [ ] **Step 1: See exactly what the gate wants**

Run: `python tools/check_skills_inventory.py`
Read every failure line. It will list: `missing Codex mirrors: experiment-handoff, handoff-intake`, `missing catalog entries: …`, and `<file> reports N skills; expected N+2` for each count file. Note the target count `expected_count`.

- [ ] **Step 2: Create the two Codex mirrors**

Copy each mainline skill to its mirror path and adapt for a Codex executor:
```bash
mkdir -p skills/skills-codex/experiment-handoff skills/skills-codex/handoff-intake
cp skills/experiment-handoff/SKILL.md skills/skills-codex/experiment-handoff/SKILL.md
cp skills/handoff-intake/SKILL.md   skills/skills-codex/handoff-intake/SKILL.md
```
Then in BOTH mirror files, remove every forbidden reviewer string (`mcp__codex__codex`, `codex-reply`, `reviewer-continuation`, `threadId`) and the `mcp__codex__codex, mcp__codex__codex-reply` tokens from `allowed-tools` — the Codex-side reviewer is Claude, not Codex MCP. Follow an existing mirror that does cross-model review (study `skills/skills-codex/research-review/SKILL.md`) and replace the "Codex MCP" review steps with that mirror's reviewer convention (or simply drop the optional review phases, keeping `REUSE_VERIFY`/`RESULTS_REVIEW` as no-ops). Ensure the file does NOT start with a UTF-8 BOM.

- [ ] **Step 3: Add catalog entries**

In `docs/SKILLS_CATALOG.md`, add two entries in the format the file uses (the regex is `[`/<name>`](../skills/<name>/SKILL.md)`):
```
[`/experiment-handoff`](../skills/experiment-handoff/SKILL.md) — plan + emit a human experiment handoff package.
[`/handoff-intake`](../skills/handoff-intake/SKILL.md) — ingest a filled handoff file → write the paper.
```
Also update the `**N skills**` count token in this file to `expected_count`.

- [ ] **Step 4: Bump every count token (+2 → `expected_count`)**

Update the number in each pattern below to `expected_count` from Step 1:
- `README.md`: `📊 **N composable skills**` and `ARIS ships **N+ skills**`
- `README_CN.md`: `📊 **N 个可组合 skill**` and `ARIS 现有 **N+ 个 skill**`
- `AGENT_GUIDE.md`: `Full catalog … **N skills**`
- `docs/ARIS_INTRO.md`: `collection of **N composable Claude Code skills**`, `## The N Skills`, `一组 N 个可组合的 Claude Code skills`
- `docs/ARIS_INTRO.html`: `collection of <strong>N composable Claude Code skills</strong>`, `id="the-N-skills"`, `一组 N 个可组合的 Claude Code skills`
- `skills/skills-codex/README.md`: `all `N` mainline skills`
- `skills/skills-codex/README_CN.md`: the `` `N` ``…skill count token

- [ ] **Step 5: Verify the gate is green**

Run: `python tools/check_skills_inventory.py && echo "INVENTORY OK"`
Expected: prints `INVENTORY OK` (exit 0, no failures).

- [ ] **Step 6: Commit**

```bash
git add skills/skills-codex/experiment-handoff skills/skills-codex/handoff-intake docs/SKILLS_CATALOG.md README.md README_CN.md AGENT_GUIDE.md docs/ARIS_INTRO.md docs/ARIS_INTRO.html skills/skills-codex/README.md skills/skills-codex/README_CN.md
git commit -m "chore(handoff): register skills in inventory (codex mirrors, catalog, counts)"
```

---

## Self-Review

**Spec coverage:**
- §3 components (2 skills + template) → Tasks 4, 5, 6. ✓
- §4 workspace `research-projects/<slug>/` → Task 5 workspace resolution + Task 8 staging. ✓
- §5 emit phases (workspace, discover flag, reuse survey, plan, emit) → Task 5 phases 1–6. ✓
- §6 deliverable sections §1–§7 + canonical table → Task 4 template. ✓
- §7 reuse-aware survey + eligibility gate + Codex verify → Task 5 Phase 2. ✓
- §8 intake (validate, extract, surprise, write) → Task 6 phases 1–5 + helper Tasks 2–3. ✓
- §9 guardrail (predictions never become results) → Global Constraints + `extract` Task 3 + tests + Key Rules in both skills. ✓
- §10 path rooting → Task 5 Phase 3 note + Task 6 workspace block; doc updates → Task 7; inventory → Task 9. ✓
- §12 success criteria → Task 8 dry run exercises emit-validate-extract. ✓

**Placeholder scan:** No "TBD/TODO" left as instructions; the `[bracketed]` spans inside the TEMPLATE file are intentional author-fill fields of the deliverable, not plan placeholders. ✓

**Type consistency:** `slugify`, `parse_tables`, `validate`, `extract`, `main`, `CANON_HEADER`, `EMPTY_ACTUAL` are named identically across Tasks 1–4, the SKILL.md helper calls (`slug`/`validate`/`extract` subcommands), and the tests. ✓
