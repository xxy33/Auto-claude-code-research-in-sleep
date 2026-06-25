# Design: Human-in-the-Loop Experiment Handoff

**Date**: 2026-06-25
**Status**: Approved (design phase)
**Author**: cxx (with Claude Code)

## 1. Motivation

ARIS today assumes the *same agent* both plans and runs experiments
(`/experiment-bridge` implements code, deploys to GPU, and collects results).
We want a different division of labor:

- **ARIS does**: literature survey, experiment planning, and (after results
  come back) paper writing + polishing.
- **A human colleague does**: actually running the experiments.

The contract between the two sides is a single, self-contained Markdown file:
**the experiment handoff package**. ARIS emits it with a fill-in-the-blank
results table (plus *predicted* numbers and pre-filled, cited baseline numbers
reused from prior work); the colleague runs the experiments, fills in the
measured numbers in place, and returns the file; ARIS ingests it and writes the
paper.

This spec also introduces a **per-direction workspace convention**
(`research-projects/<slug>/`) so that artifacts for different research
directions stay isolated and the repo does not become cluttered over time.

## 2. Key design decisions (settled during brainstorming)

| Decision | Choice |
|---|---|
| Packaging | Approach A: two new skills + one template; existing skills mostly untouched |
| "Expected result" cell | Concrete **predicted numbers** (tagged `(pred)`), colleague fills the real number next to it |
| Literature reuse | **Pre-fill + cite**: reused baseline numbers are pre-filled and locked as `REUSE — do NOT re-run`; colleague only runs the genuinely new cells |
| Round-trip | **Same file, in-place fill**: colleague edits the same `EXPERIMENT_HANDOFF.md` and returns it |
| Entry point | **Both, via a flag**: default assumes the method is decided; `— discover: true` prepends idea discovery |
| Writing leg | **Reuse `/paper-writing` + `/auto-paper-improvement-loop` as-is** |
| Workspace folder | **`research-projects/<slug>/`** (reuse the existing folder; keep ARIS sub-structure inside) |

## 3. Components

Three new artifacts. No existing skill is rewritten; only small "composing
with other skills" notes are added to a few SKILL.md files.

| Artifact | Type | Role |
|---|---|---|
| `skills/experiment-handoff/SKILL.md` | new skill (Workflow 1.5-H) | direction/method → reuse-aware survey → plan → **emit** `EXPERIMENT_HANDOFF.md` |
| `skills/handoff-intake/SKILL.md` | new skill | filled `EXPERIMENT_HANDOFF.md` → validate → **chain into** `/paper-writing` |
| `templates/EXPERIMENT_HANDOFF_TEMPLATE.md` | new template | canonical shape of the deliverable |

The reuse-aware survey is a **phase inside `experiment-handoff`**, not a
standalone skill (YAGNI — can be promoted later if reused elsewhere).

## 4. Per-direction workspace

```
research-projects/<slug>/          slug = kebab-case of the direction; created if absent
  idea-stage/                      only when — discover: true
  refine-logs/                     FINAL_PROPOSAL.md, EXPERIMENT_PLAN.md, REUSABLE_BASELINES.md
  EXPERIMENT_HANDOFF.md            the deliverable handed to the colleague
  paper/   figures/                written by the writing leg at intake time
research-wiki/                     SHARED at repo root — accumulates across all directions
```

- Both new skills set their I/O base path to `research-projects/<slug>/`.
- `research-wiki/` deliberately stays at the repo root: it is a cross-direction
  knowledge base and must accumulate across projects.
- The two pre-existing folders (`research-projects/pgsc/`,
  `research-projects/memory-skill-coevolution/`) are the de-facto precedent;
  this convention gives them a spec to converge toward (no forced migration in
  this work).

### Slug resolution
- Derive `<slug>` from the direction/method title: lowercase, spaces/punct →
  `-`, collapse repeats, trim, cap length (~40 chars).
- If `research-projects/<slug>/` already exists, reuse it (resume-friendly).
- Allow an explicit override: `— slug: my-name`.

## 5. `experiment-handoff` skill (emit side)

Trigger examples:
```
/experiment-handoff "method or idea"                 # method already decided
/experiment-handoff "broad direction" — discover: true   # prepend idea discovery
/experiment-handoff "..." — slug: agent-mem-v2       # explicit workspace name
```

### Phases
1. **Resolve workspace** — compute slug, create `research-projects/<slug>/`,
   set it as the base path for all outputs.
2. **(Optional) Idea discovery** — when `— discover: true`, run
   `/idea-discovery` + `/novelty-check`, writing into
   `research-projects/<slug>/idea-stage/`. Otherwise read the user-provided
   method or an existing `refine-logs/FINAL_PROPOSAL.md`.
3. **Reuse-aware survey** (the novel phase) — see §7. Produces
   `refine-logs/REUSABLE_BASELINES.md` (the Reusable Baseline Ledger).
4. **Experiment planning** — run `/experiment-plan` internally, rooted at the
   workspace, to produce claims, blocks, configs.
5. **Emit handoff package** — render `EXPERIMENT_HANDOFF.md` from the template
   (§6), folding in the ledger from phase 3 and the plan from phase 4.
6. **Summarize** — tell the user the file path and what to send the colleague.

### Constants
- `WORKSPACE = research-projects/<slug>/`
- `DISCOVER = false`
- `REUSE_VERIFY = true` — cross-model (Codex MCP) verification of reuse claims
- `OUTPUT = research-projects/<slug>/EXPERIMENT_HANDOFF.md`

## 6. Deliverable: `EXPERIMENT_HANDOFF.md`

Self-contained and human-readable; a colleague who did **not** do the planning
must be able to execute from it without reading ARIS internals.

- **§1 Project Background** — problem, why it matters, the method in plain
  language, what the experiments are meant to show.
- **§2 Claims** — the 1–2 claims each experiment defends (from `/experiment-plan`).
- **§3 Reusable Baseline Ledger** — numbers reused from prior papers,
  pre-filled + cited, each tagged `REUSE — do NOT re-run`, with the matched
  *benchmark + backbone + split + metric*.
- **§4 Experiment tables** — one fill-in-the-blank table per experiment block:

  | System | Benchmark | Backbone | Metric | Expected *(pred)* | **Actual** | Run? / Source |
  |---|---|---|---|---|---|---|
  | Prior baseline X | GSM8K | Llama-3-8B | acc | 71.2 | 71.2 | `REUSE [Smith'25]` |
  | **Ours** | GSM8K | Llama-3-8B | acc | ~74.5 *(pred)* | ⬜ | `RUN` |

  `REUSE` rows arrive filled & locked; `RUN` rows carry a predicted `Expected`
  and an empty `⬜ Actual`.
- **§5 Run specs** — per `RUN` row: dataset/split, backbone, hyperparameters,
  seeds, success criterion, rough compute/runtime. Enough to execute without
  asking back.
- **§6 Instructions for the colleague** — "fill only the ⬜ cells in `Actual`
  for `RUN` rows; leave `REUSE` rows untouched; note any config deviation in
  Notes; return this file."
- **§7 Prediction disclaimer** — `Expected` values are predictions, not
  measurements; they exist only to set expectations and are dropped at intake.

## 7. Reuse-aware survey (research-grounded phase)

Insight: in fields like agent memory, work builds on prior results and **reuses
reported numbers when the benchmark and backbone match**, rather than re-running
every baseline.

Steps:
1. From the plan, pin the **target benchmark(s) + backbone(s) + metric + split**.
2. Call `/research-lit` focused on prior work using *those* benchmarks/backbones.
3. For each prior result, extract `(method, benchmark, split, backbone, metric,
   value, citation)`.
4. **Reuse-eligibility gate** — a prior number is reusable **only if benchmark
   AND backbone AND split AND metric all match** ours. If the backbone differs →
   not reusable → it becomes a `RUN` row. Every mismatch is listed with its
   reason.
5. **Cross-model verification** (`REUSE_VERIFY = true`, via Codex MCP) — GPT
   checks the high-stakes reuse claims: "did this paper really use this backbone
   on this benchmark, and is the number transcribed correctly?" before a number
   is locked as `REUSE`. Fits ARIS's adversarial-review ethos and guards against
   citing a wrong number. Degrade gracefully if Codex MCP is unavailable
   (mark such rows `REUSE (unverified)`).

Output: `refine-logs/REUSABLE_BASELINES.md` — the ledger that feeds §3 and the
`REUSE` rows of §4.

## 8. `handoff-intake` skill (intake side)

Trigger:
```
/handoff-intake "research-projects/<slug>/EXPERIMENT_HANDOFF.md"
/handoff-intake <slug>                       # resolves the path from the slug
/handoff-intake "..." — allow-partial: true  # proceed with some RUN cells empty
```

### Phases
1. **Load & locate workspace** — accept a file path or a slug.
2. **Validate completeness** — every `RUN` row's `Actual` must be filled;
   **block and list** any empties unless `— allow-partial: true`.
3. **Build measured-results table** — from `Actual` values + cited `REUSE`
   values **only**. Predicted (`Expected`) numbers are discarded here.
4. **Surprise check** — flag any `Actual` far from its `Expected`; these are
   points the writer must address honestly (never paper over).
5. **(Optional) cross-model sanity review** of the results interpretation.
6. **Hand off to writing** — chain `/paper-writing` then
   `/auto-paper-improvement-loop`, writing into the same workspace
   (`research-projects/<slug>/paper/`). Only measured/cited numbers are passed.

### Constants
- `ALLOW_PARTIAL = false`
- `RESULTS_REVIEW = true`

## 9. Guardrail: predictions must never become "results"

The one real risk in predicted numbers is a fabricated figure leaking into the
paper as a real result. Defenses:

- Predictions live **only** in the `Expected (pred)` column and are always
  tagged `(pred)`.
- Predictions are **never** written to `EXPERIMENT_TRACKER.md` results or any
  results file.
- `/handoff-intake` is the **only** bridge from handoff to writing, and it drops
  predictions by construction (§8 step 3).

## 10. Integration & wiring

- **Path rooting (trickiest bit)**: internal `/research-lit` and
  `/experiment-plan` calls currently hardcode root-level `refine-logs/` /
  `idea-stage/`. The handoff skill must root them at the workspace — by running
  them with the workspace as the base path and/or relocating their outputs into
  `research-projects/<slug>/`. This is the main implementation detail to resolve
  in the plan; it is not a design blocker.
- **Docs to update** (small additions): `README.md` / `README_CN.md` workflow
  list, `SETUP_GUIDE.md` / `SETUP_GUIDE_CN.md` quick-commands, possibly
  `docs/SKILLS_CATALOG.md`, and a "composing" note in `experiment-plan`,
  `experiment-bridge`, and `research-pipeline` SKILL.md so the new path is
  discoverable.
- **Output protocols**: both new skills follow the existing shared protocols
  (output-versioning, output-manifest, output-language).

## 11. Out of scope

- Automated experiment execution (that remains `/experiment-bridge`).
- Forced migration of the two existing `research-projects/` folders.
- Changes to `/paper-writing` internals (reused as-is).
- A standalone reuse-survey skill (kept as a phase for now).

## 12. Success criteria

- `/experiment-handoff "<direction>"` produces a single self-contained
  `research-projects/<slug>/EXPERIMENT_HANDOFF.md` with background, claims, a
  cited Reusable Baseline Ledger, fill-in-the-blank tables (predicted numbers +
  empty `Actual` cells), run specs, and colleague instructions.
- Baseline numbers that match our benchmark+backbone are pre-filled and cited;
  only genuinely new cells are marked `RUN`.
- A colleague can fill the file in place and return it.
- `/handoff-intake` validates completeness, drops predictions, and chains into
  paper writing + polishing, all within the same workspace.
- No predicted number can reach the paper as a measured result.
