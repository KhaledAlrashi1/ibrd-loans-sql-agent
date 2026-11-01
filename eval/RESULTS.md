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
