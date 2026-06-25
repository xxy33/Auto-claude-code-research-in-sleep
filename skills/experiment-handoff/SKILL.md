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
