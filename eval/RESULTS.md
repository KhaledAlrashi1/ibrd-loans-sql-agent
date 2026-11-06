# Evaluation results

How the agent scores on `eval/questions.yaml` (20 dev questions used for tuning, 10 heldout questions
scored only at checkpoints). Scoring rules are at the top of `questions.yaml`; the comparison code is
`src/agent/scoring.py`. Each question is **correct**, **abstained** (the agent asked or declined instead of
answering) or **wrong**. The caveat check is reported only and never changes an outcome.

## 2026-11-01: Phase 4 checkpoint

- Data: snapshot End of Period 2026-09-30.
- Model: `claude-sonnet-5-5`, effort `high`.
- Agent and prompt: commit `3177053`. The runs used the working tree that was then committed unchanged as `3177053`.
- Scoring correction: commit `d6f9711`, made after the heldout run (see below).

### Runs as first scored

| Run | File | Correct | Abstained | Wrong | Caveats | Latency median / max | Cost |
|---|---|---|---|---|---|---|---|
| dev 1 | `results/20261101-173532_dev.json` | 20 | 0 | 0 | 3/3 | 3.2 s / 14.7 s | $0.18 |
| dev 2 | `results/20261101-173649_dev.json` | 20 | 0 | 0 | 3/3 | 2.9 s / 3.8 s | $0.14 |
| dev 3 | `results/20261101-173749_dev.json` | 20 | 0 | 0 | 3/3 | 3.1 s / 4.1 s | $0.14 |
| heldout | `results/20261101-173903_heldout.json` | **9** | 0 | **1** | 1/1 | 3.1 s / 5.5 s | $0.07 |

No dev question changed outcome across the three runs. Cost is estimated from token counts at list prices.

### H07 scoring correction (made after seeing the heldout result)

H07 asks "Which region owes the most to the IBRD?". The agent summed `borrowers_obligation_usd` by region,
excluding guarantees, and returned all 7 regions in descending order. Its first row matched the gold row
(LATIN AMERICA AND CARIBBEAN, US$86,600,995,156.95). The scorer required exactly one row, so it marked
the answer wrong.

Khaled decided that for "which X has the most" questions, a full ranking whose first row matches the gold
row counts as correct. `match: first_row` was added to D08, D12 and H07, with the same tolerances as before.
Only the scorer and the eval file changed. The agent, the prompt and the saved runs did not.

In the same commit, the caveat terms for D09 and H05 changed from `["zero", "excluded"]` to `["multiple"]`.
The old terms also matched "excluded" in unrelated assumptions such as "guarantees excluded".

### Re-scored with the corrected scorer (no new model calls)

Reproduce with `scripts/rescore.py`, which re-scores saved result files against the current
`questions.yaml` without calling the model or changing the files:

```bash
source .venv/bin/activate
python scripts/rescore.py eval/results/20261101-173532_dev.json eval/results/20261101-173649_dev.json \
    eval/results/20261101-173749_dev.json eval/results/20261101-173903_heldout.json
```

| Run | Before (correct / abstained / wrong) | After | Caveats before → after |
|---|---|---|---|
| dev 1 | 20 / 0 / 0 | 20 / 0 / 0 | 3/3 → 3/3 |
| dev 2 | 20 / 0 / 0 | 20 / 0 / 0 | 3/3 → 3/3 |
| dev 3 | 20 / 0 / 0 | 20 / 0 / 0 | 3/3 → 3/3 |
| heldout | 9 / 0 / 1 | 10 / 0 / 0 | 1/1 → 1/1 |

Only H07 changed (wrong → correct).

**How to read the heldout number:** the heldout score was **9/10 as first scored**. The 10/10 comes from a
scoring rule changed after the heldout result was seen, so it is not a clean heldout measurement. The
heldout set is also small (10 questions). The next heldout checkpoint will be scored with the corrected
rules from the start.

## 2026-11-03: Post-hardening run

PR #5 changed `src/agent/executor.py` (memory cap 512 MB, 2 threads, no disk spill, locked configuration)
and added `MEMORY_LIMIT` / `THREADS` to `config.py`. The prompt, the validator and the model settings did
not change. One dev run on merged `main` (commit `a8f96a5`), so the latest result file matches the code
the v2 API imports.

- Data: snapshot End of Period 2026-09-30. Model: `claude-sonnet-5-5`, effort `high`.
- Before the run: `pytest -q` 146 passed; `scripts/verify_gold.py` all gold answers match pandas.

| Run | File | Correct | Abstained | Wrong | Caveats | Latency median / max | Cost |
|---|---|---|---|---|---|---|---|
| dev (post-hardening) | `results/20261103-191552_dev.json` | 20 | 0 | 0 | 3/3 | 3.3 s / 4.3 s | $0.18 |

Same outcome as the three Phase 4 dev runs. Heldout was not run.

## 2026-11-06: KI-1 fix and caveat-scoring change

### Scorer change (no gold values changed)

The caveat check used to test only that required terms appear (`must_mention`). D15 passed with a wrong
caveat ("the count may be lower than 44" next to an answer of 44; see `docs/known-issues.md`, KI-1). Two
deterministic checks were added to `src/agent/scoring.py`. Like `must_mention`, they are **reported only and
never change the outcome**:

1. **`must_not_mention`** in `questions.yaml`: any listed term in the message or assumptions fails the caveat.
   D15: `["lower than", "fewer than", "may be lower"]`.
2. **Comparison-claim check**, on every answer whose result is a single number: phrases such as
   "lower / fewer / less than X" fail when the result is ≥ X, and "higher / more / greater than X" fail when
   the result is ≤ X.

**Earlier runs under the new scorer** (`scripts/rescore.py` on all saved dev runs; heldout not read):

| Run | File | Outcomes (c / a / w) | Caveats before → after |
|---|---|---|---|
| Phase 3 first run | `results/20261101-171538_dev.json` | 19 / 1 / 0 (unchanged) | not scored → 3/3 |
| dev 1 | `results/20261101-173532_dev.json` | 20 / 0 / 0 (unchanged) | 3/3 → 3/3 |
| dev 2 | `results/20261101-173649_dev.json` | 20 / 0 / 0 (unchanged) | 3/3 → 3/3 |
| dev 3 | `results/20261101-173749_dev.json` | 20 / 0 / 0 (unchanged) | 3/3 → **2/3** |
| post-hardening | `results/20261103-191552_dev.json` | 20 / 0 / 0 (unchanged) | 3/3 → 3/3 |

**Yes, one earlier run would have failed D15:** dev 3 (Nov 1). Both checks catch it: `must_not_mention` finds
"lower than" and "may be lower", and the claim "lower than 44" is contradicted by the result of 44. No other
earlier answer triggers the comparison-claim check (11-13 single-number answers per run).

### Dev run after the KI-1 fix

KI-1 fix: the dictionary now says FY2027 has 44 loans and 0 guarantees and that a partial-year figure can
only be the same or higher for the full year; the prompt's Defaults say assumptions describe what the SQL
does and don't predict how the result compares to a number.

- Data: snapshot End of Period 2026-09-30. Model: `claude-sonnet-5-5`, effort `high`.
- Before the run: `scripts/verify_gold.py` all gold answers match pandas.

| Run | File | Correct | Abstained | Wrong | Caveats | Comparison claims contradicted | Latency median / max | Cost |
|---|---|---|---|---|---|---|---|---|
| dev (KI-1) | `results/20261106-140841_dev.json` | 20 | 0 | 0 | 3/3 | 0 of 13 | 3.2 s / 7.1 s | $0.18 |

D15 now answers 44 with "FY2027 is partial in this snapshot: it only covers 2026-07-01 to 2026-09-30, so the
full-year count could be higher." and "Guarantees excluded (is_guarantee = FALSE); FY2027 has no guarantees
anyway." Heldout was not run.
