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
