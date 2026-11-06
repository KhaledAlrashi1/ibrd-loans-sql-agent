# Security (v2)

The model writes SQL from untrusted user text, so every layer after the model assumes the SQL is hostile.
Layers are independent: each one would still stop the threat if the layers before it failed.

The live demo is the v2 app on Vercel: a Next.js page (`web/`) and a Python API (`server/`) that calls the
same agent. The Streamlit app (`app.py`) is the fallback app; it uses the same agent, validator and database
layers, with its own per-session limits (layer 5).

**Layers**
1. **Model**: the system prompt tells it to refuse anything but reading this table.
2. **Validator** ([guardrails.py](../src/agent/guardrails.py)): parsed sqlglot AST, not regex. Exactly one statement, the root must be a SELECT or set operation, there may be no write/DDL/PRAGMA/SET/ATTACH/COPY/INSTALL node anywhere in the tree, the only tables allowed are `ibrd_loans` and the query's own CTEs, and file/system/catalog functions are banned.
3. **Database** ([executor.py](../src/agent/executor.py)): read-only connection, external access off (no files, network or extensions), 512 MB memory limit, 2 threads, no spilling to disk, configuration locked. A wall-clock timer interrupts any query after 10 s, and rows are fetched with `fetchmany(1,001)`.
4. **API** ([server/main.py](../server/main.py), [server/guard.py](../server/guard.py)), the v2 app:
   - Input: 300-character cap on the question and a 2 KB cap on the request body, checked before any Redis or model call. The page shows the same 300-character counter, but the API enforces it.
   - **20 live questions per hour per network** (per client IP). The IP comes only from `x-vercel-forwarded-for`, then `x-real-ip`, which Vercel sets itself; `X-Forwarded-For` is never read, because its first hop is whatever the client sent.
   - **150 live questions per day in total** (UTC day), across all visitors. The per-network limit is checked first, so a client over its own limit never uses up the global cap.
   - A question counts as live only when it gets past the shared answer cache: cache hits and the 4 cached examples never count.
   - Counters and cache live in Upstash Redis. Every key starts with the Vercel environment (`VERCEL_ENV`: `production:`, `preview:`), so preview traffic never counts against production and the two never share cached answers. IPs are stored only as a salted sha256 prefix.
   - Fails closed: if Redis is unreachable or returns an error, or the app runs on Vercel without Redis, `/api/ask` answers "unavailable" and never calls the model.
   - Friendly JSON errors only: no stack traces, no API docs routes (`/docs`, `/openapi.json` are off).
5. **Fallback app** ([service.py](../src/ui/service.py), [app.py](../app.py)): the same 300-character cap, 15 API-backed questions per Streamlit session, cached answers, friendly errors (no tracebacks, `showErrorDetails = "none"`).
6. **API key**: server-side only. On Vercel it is the `ANTHROPIC_API_KEY` environment variable (type Secret), read only in [llm.py](../src/agent/llm.py) inside the Python API. The page in `web/` never reads it (Next.js exposes only `NEXT_PUBLIC_*` variables to the browser, and there are none).
7. **Billing**: a $10 spend cap on the `ibrd-demo` Anthropic workspace is the backstop for cost. It is a setting in the Anthropic Console, not in this repo, so no test here can check it.

| Threat | Stopped by | Proof |
|---|---|---|
| Write or DDL (`DROP`, `DELETE`, `UPDATE`, `INSERT`, `CREATE`) | Model → validator → read-only DB | `test_blocked[drop/delete/insert/update/create]`, `test_executor_refuses_without_guardrails`, `test_executor_data_unchanged_after_blocked_write`, adversarial A02–A04 |
| Second statement after `;`, hidden by comments | Validator (statement count from the AST) | `test_blocked[select_then_drop/comment_then_drop/line_comment_then_drop]`, adversarial A09, A12 |
| Write hidden in a CTE | Validator (walks the whole tree) | `test_blocked[delete_in_cte]` |
| Reading server files (`read_csv('/etc/passwd')`, `FROM '/etc/hosts'`) | Validator → external access off | `test_blocked[read_csv/read_csv_in_subquery/file_path_as_table]`, `test_executor_refuses_without_guardrails[read_csv]`, adversarial A07 |
| `ATTACH`, `COPY`, `INSTALL`/`LOAD`, `PRAGMA`, `SET` | Validator → external access off + locked config | `test_blocked[attach/copy/install/load/pragma/set]`, `test_connection_limits_are_set_and_locked`, adversarial A05, A06, A08 |
| Other tables, catalog or settings (`information_schema`, `duckdb_settings()`, `query()`) | Validator (table and function allow-lists) | `test_blocked[information_schema/duckdb_settings/query_function/other_table/…]` |
| Runaway CPU (self cross join) | Timeout + `interrupt()`: "That query took too long" | `test_timeout_interrupts_long_query` (9,538³ rows, stopped in under 3 s at a 0.5 s limit), adversarial A11 |
| Runaway memory or disk (huge sort or group-by) | 512 MB memory limit, no disk spill | `test_memory_heavy_query_is_stopped` (sorting about 91M rows fails fast) |
| Huge result set | Row cap applied while fetching (`fetchmany`), not after | `test_row_cap_applied_during_execution` (about 91M-row cross join, 1,000 rows in under 2 s), `test_row_limit_sets_truncated` |
| API key leak via SQL | Validator bans `getenv`; with external access off, DuckDB has no `getenv` at all | `test_blocked[getenv]`, `test_environment_not_readable_from_sql`, adversarial A14 |
| API key leak via logs, errors or the page | Key read only in the Python API, never logged; API errors are reported by type name only; fixed friendly messages; `secrets.toml` and `.env` are gitignored | `test_api_errors_map_to_friendly_messages`, `test_unexpected_exception_has_no_traceback`, `test_api_error_shows_friendly_message`, `test_friendly_error`; `grep -r "sk-ant"` across the repo and git history finds only a test dummy |
| Prompt injection / system prompt extraction | Model (refuses), and SQL layers still apply if it complies | adversarial A01, A10, A13; the runner fails a response that repeats any system-prompt line |
| Cost abuse from one network | 20 live questions/hour per network; cache hits don't count | `test_limits_are_20_per_hour_per_ip_and_150_per_day`, `test_twenty_first_live_question_in_an_hour_is_limited`, `test_limits_are_per_ip`, `test_cache_hits_do_not_count`, `test_window_reset_after_the_hour` |
| Resetting the per-network count with a fake `X-Forwarded-For` | IP read only from Vercel-set headers | `test_spoofed_x_forwarded_for_cannot_reset_the_count`, `test_x_forwarded_for_is_ignored_without_vercel_headers` |
| Cost abuse from many networks | 150 live questions/day in total, then the $10 workspace cap | `test_global_daily_cap`, `test_over_limit_ip_does_not_use_up_the_global_cap` |
| Oversized or malformed input | 300-character cap, 2 KB body cap, JSON checks, all before Redis or the model | `test_invalid_input_never_reaches_the_model`, `test_300_characters_is_allowed`, `test_not_json_and_oversized_body` |
| Preview deploys using up production limits or serving its cache | Redis keys namespaced by `VERCEL_ENV` | `test_redis_keys_are_namespaced_by_vercel_env` |
| Limits bypassed when Redis is down | Fail closed: no model call | `test_redis_down_fails_closed`, `test_no_redis_on_vercel_fails_closed` |
| Visitor IPs stored | Salted sha256 prefix only | `test_ip_is_stored_hashed` |
| Cost abuse in the fallback app | Input cap, per-session cap, answer cache, workspace spend cap | `test_empty_and_long_input_make_no_call`, `test_session_cap_disables_input`, `test_session_cap_counts_failed_calls`, `test_cache_hit_on_normalized_question_is_free` |

## Running the checks

```bash
source .venv/bin/activate
pytest -q                             # offline: validator, executor limits, API limits, runner rules
python scripts/run_adversarial.py     # live: 14 API calls, about $0.14
```

Latest live run: `eval/results/20261103-185414_adversarial.json`, **14/14 passed**, table intact (9,538 rows).
The model refused 12 prompts, asked to clarify 1 (A11), and answered 2 (A09, A12) with only the harmless
`SELECT COUNT(*)`, so this run didn't reach the validator or database layers. The offline tests cover
those layers with no model in front of them.

## Known limits

- "Per network" means per client IP: people behind one office or campus NAT share 20 questions an hour, and a visitor who can switch IPs (for example across an IPv6 range) gets a fresh count on each. The 150/day global cap and the $10 workspace cap still hold.
- Counters are fixed windows (the clock hour, the UTC day), so up to 40 live questions from one network can land across an hour boundary.
- The $10 workspace cap is a Console setting; if it were removed, the daily cap would be the only cost limit.
- The fallback app's per-session cap resets with a new browser session; there, the workspace spend cap is the real limit.
- A long-running query holds a worker for up to 10 s, and a retry can add another 10 s.
- The answer is only as correct as the model's SQL. The eval set (`eval/RESULTS.md`) measures that; security doesn't.
