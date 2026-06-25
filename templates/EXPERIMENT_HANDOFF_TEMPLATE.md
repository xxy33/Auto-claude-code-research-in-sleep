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
