# CLAUDE.md — IBRD Loans Text-to-SQL Agent

Portfolio project for a World Bank application (MNA Fellow, Modeling, Data & Analytics).
A user asks a plain-English question about IBRD loans; the app generates SQL with an LLM,
validates it, runs it on a local DuckDB file, and shows the answer as a table (+ chart when it fits) with the SQL.

**Hard deadline: live demo + public repo by Nov 17, 2026.**

## Priorities (in this order)
1. **Correct answers.** Saying "I'm not sure" beats returning a wrong number.
2. **Finished and live by Nov 17.** Cut features before cutting quality.
3. **A README a hiring manager understands in 60 seconds.**

## Stack
- Python 3.12, virtual env at `.venv` (created with `uv`). Do NOT use the conda envs on this machine.
- DuckDB (opened `read_only=True` by the app)
- Anthropic API, model set in `src/agent/config.py` (default `claude-sonnet-5-5`)
- `sqlglot` for SQL validation
- Streamlit UI, deployed on Streamlit Community Cloud
- No LangChain / agent frameworks: plain functions, easy to read and explain.

## Commands
```bash
source .venv/bin/activate
python scripts/build_db.py            # raw CSV -> DuckDB file in the temp dir, config.DB_PATH (fails loudly if checks fail)
python scripts/run_eval.py            # scores the agent (dev split) -> eval/results/<timestamp>_dev.json
pytest -q                             # guardrail tests
streamlit run app.py
```

## Repo structure
```
app.py                         Streamlit UI only (no business logic)
data/raw/ibrd_snapshot_2026-09-30.csv   FROZEN source snapshot (committed)
<tempdir>/ibrd-loans-sql-agent-<hash>/ibrd.duckdb   built by scripts/build_db.py (config.DB_PATH; nothing is written to data/)
src/agent/
  config.py                    model name, row limit, timeout
  data_dictionary.yaml         single source of truth: feeds the prompt AND the README
  prompt.py  llm.py  guardrails.py  executor.py  agent.py
scripts/build_db.py  scripts/run_eval.py
eval/questions.yaml            question, gold SQL, split (dev / heldout), notes
eval/results/
tests/test_guardrails.py
docs/                          demo GIF, screenshots
```

## Data facts (verified Oct 31, 2026)
- Source: World Bank Finances One, "IBRD Statement of Loans and Guarantees – Latest Available Snapshot" (DS00047). License CC BY 4.0.
- Snapshot: **End of Period = 09/30/2026**, 9,538 rows × 35 columns. One row per Loan Number.
- Amounts are in **US$**; the exchange-rate basis differs by column (`usd_basis` in `data_dictionary.yaml`): undisbursed at End of Period rates, borrower's obligation revalued, several columns not documented.
- Table name in DuckDB: `ibrd_loans`. Columns renamed to snake_case; the original→new name mapping lives in `data_dictionary.yaml`.
- **Guarantees are mixed in:** Loan Numbers starting `IBRDB` or `IBRDG` are guarantees (official rule). Derived column `is_guarantee`. Loan questions exclude guarantees by default, and the answer says so.
- **Years:** World Bank fiscal year runs Jul 1 – Jun 30 (FY2024 = Jul 2023–Jun 2024). Default "year" = fiscal year (`board_approval_fy`), and the answer says so.
- **Exact category values matter.** Example: Region `MID EAST,NORTH AFRICA,AFG,PAK`; country `Turkiye`, `Korea, Republic of`, `Egypt, Arab Republic of`. The prompt must list the allowed values exactly.
- Anything not confirmed by official metadata or the data itself is marked `TODO: verify` in the dictionary. **Never guess a column's meaning.**

## Guardrails (non-negotiable)
- Exactly one statement, and it must be a `SELECT` (CTEs allowed). Reject everything else using the parsed sqlglot AST, not regex.
- Enforce a row limit (default 1,000) and a query timeout (default 10 s).
- Read-only DuckDB connection.
- On a failure: at most one retry with the error message, then return "I couldn't answer that reliably" plus the reason.
- An empty result returns "No matching rows", never a guess.
- Every answer shows its SQL and any assumptions (e.g., "guarantees excluded", "fiscal year").
- Agent SQL returns raw, unrounded USD values. Rounding and formatting happen only in the UI.

## Rules for Claude Code
1. **Never edit gold SQL or expected answers in `eval/` to make a test pass.** Fix the agent, prompt or dictionary instead. Only Khaled changes gold answers.
2. **Never overwrite or re-download `data/raw/`.** The snapshot is frozen for reproducible evaluation.
3. Never commit secrets. The API key lives in `.streamlit/secrets.toml` / `ANTHROPIC_API_KEY` (both gitignored).
4. Ask before adding a new dependency or a feature not in the plan.
5. When the meaning of the data is unclear, stop and report. Don't assume.
6. Work in small steps. After each step, run the relevant check and report results in short tables.
7. Keep explanations short. Lead with what changed and what Khaled needs to review.
8. During tuning, run only `run_eval.py --split dev`. Never run or read heldout results unless Khaled asks.
9. One branch per phase; open a PR; merge only when Khaled says so.
10. Never print or read the contents of .streamlit/secrets.toml. Load the key from there or from ANTHROPIC_API_KEY.
