# v2 plan: Next.js on Vercel

**Goal:** same agent, better UI, no hibernation.
**Rule:** live and verified by **Thu Nov 12, 2026**, or we keep Streamlit. The Streamlit app stays deployed and untouched either way.
**Status:** plan only. No app code yet. Mockup: [docs/mockups/v2-mockup.html](mockups/v2-mockup.html) (answer, single-value and clarify states; light and dark).

## Summary

| Decision | Choice |
|---|---|
| Hosting | One Vercel project, **Vercel Services** (beta): Next.js in `web/` at `/`, FastAPI in `server/` at `/api/*`. One URL, no CORS. |
| Gate | Evening 1 is a deploy spike. If it fails, fall back to FastAPI on Fly.io behind a Next.js proxy (section 1.4). |
| Frozen | `src/agent/*` (agent, prompt, validator, executor, config), `app.py`, `src/ui/*`. The API only **imports** them. |
| Logic reuse | Input checks, cache key, friendly errors (`service.py`), plus number formatting and chart choice (`display.py`), all stay in Python. The frontend only renders. |
| Abuse/cost | Per-IP limits, a global daily cap and a shared answer cache in Upstash Redis (free tier), all enforced in Python. 300-character cap. The key stays server-side. The $10 workspace cap is the backstop. |
| Speed | 4 examples precomputed by the real agent and served as static JSON ("Cached example"). Progress states and skeletons for live questions. |
| Look | "Calm ledger": warm paper, ink, one teal accent, a serif for headlines and answers, sans for data. |
| Effort | 8 evenings (Nov 4–11), with Nov 11 as buffer. Go/no-go on Nov 12. |

---

## 1. Architecture

```
browser ──► https://<project>.vercel.app
              │
              ├── /api/*  ──► service "api"  (Python 3.12, FastAPI, server/main.py)
              │                 ├─ server/guard.py   rate limit, daily cap, cache  ──► Upstash Redis (REST)
              │                 ├─ src/ui/service.py validate_question, normalize_question, friendly_error
              │                 ├─ src/agent/agent.py answer()  ──► Anthropic API
              │                 │      └─ guardrails.py, executor.py ──► /tmp/…/ibrd.duckdb (read-only)
              │                 └─ src/ui/display.py column_unit, format_value, choose_chart
              │
              └── /*      ──► service "web"  (Next.js App Router, TypeScript, Tailwind, web/)
                                └─ web/src/data/examples.json  (4 precomputed answers, static)
```

### 1.1 Vercel limits that matter (checked Nov 3, 2026)

| Limit | Value | What it means here |
|---|---|---|
| Python version | 3.12 (default), 3.13, 3.14 | Matches `.venv` (3.12.13). Pin with `requires-python`/`.python-version` in `server/`. |
| Python bundle | **500 MB** uncompressed (250 MB for other runtimes); "large functions" up to 5 GB (beta) | Measured locally: duckdb 50 MB, anthropic + pydantic about 35 MB, sqlglot 6 MB, pandas + numpy 80 MB, altair 10 MB. **About 190 MB**, which fits. Streamlit and pyarrow (170 MB) are not installed for the API. |
| `/tmp` | writable scratch, **up to 500 MB**; the rest of the filesystem is read-only | `config.DB_PATH` already lives in the temp dir. `ensure_database()` builds the 1.6 MB file from the 2.9 MB CSV in **0.5 s** locally, once per instance. |
| Max duration | Hobby: 300 s default and max (Fluid compute) | Set `maxDuration: 60`. Worst case is 2 model calls plus 2 × 10 s queries, well under 60 s. |
| Memory | Hobby: 2 GB / 1 vCPU | The executor's 512 MB DuckDB cap fits with headroom. |
| Body size | 4.5 MB request/response | 1,000 rows × a few columns, raw and formatted, is about 100–200 KB. |
| Cold start | No official Python figure. Archived functions (no calls for 2 weeks in production) add **≥ 1 s** | Measured locally: imports of agent + service 1.7 s, display (pandas/altair) 1.3 s, DB build 0.5 s, **about 3.5 s**. A daily cron to `/api/health` prevents archiving (Hobby allows daily crons, ±59 min precision: [cron limits](https://vercel.com/docs/cron-jobs/usage-and-pricing)). The progress states cover the cold start. |
| Services | **Beta**, all plans. Each service is built separately. Top-level rewrites route to services, and the service sees the original path (`/api/ask`). | This is the main risk. Hence the spike. |

Sources: [Python runtime](https://vercel.com/docs/functions/runtimes/python), [Functions limits](https://vercel.com/docs/functions/limitations), [Runtimes (/tmp, archiving)](https://vercel.com/docs/functions/runtimes), [Services](https://vercel.com/docs/services), [Services routing](https://vercel.com/docs/services/routing), [Service config](https://vercel.com/docs/services/config-reference).

### 1.2 Files added (nothing existing is edited)

```
vercel.json                 services + rewrites + daily cron
server/main.py              FastAPI app: POST /api/ask, GET /api/health
server/guard.py             Upstash REST calls: rate limit, daily cap, cache (plain functions)
server/labels.py            plain-English column labels (section 6)
server/requirements.txt     API pins: same versions as requirements.txt, minus streamlit/pyarrow, plus fastapi
server/tests/               pytest: contract, guard (fake Redis), labels. Offline, no API calls.
scripts/precompute_examples.py   runs the real agent on the 4 examples -> web/src/data/examples.json
web/                        Next.js app
```

Sketch of `vercel.json` (confirmed in the spike):

```json
{
  "services": {
    "web": { "root": "web/" },
    "api": {
      "root": "./",
      "entrypoint": "server.main:app",
      "installCommand": "pip install -r server/requirements.txt",
      "functions": { "server/main.py": { "maxDuration": 60,
        "excludeFiles": "{web/**,eval/**,tests/**,docs/**,.venv/**,.streamlit/**}" } }
    }
  },
  "rewrites": [
    { "source": "/api/(.*)", "destination": { "service": "api" } },
    { "source": "/(.*)",     "destination": { "service": "web" } }
  ],
  "crons": [{ "path": "/api/health", "schedule": "0 12 * * *" }]
}
```

The Python service root has to be the repo root because the agent imports `src.*` and reads `data/raw/`. That is the unusual part: there is an explicit entrypoint so Vercel doesn't pick up the Streamlit `app.py`, and `server/requirements.txt` is used instead of the Streamlit one. If `installCommand` doesn't control what gets bundled, the fallback is the root `requirements.txt`. That adds about 170 MB (still under 500 MB) and some cold-start time.

### 1.3 Spike (evening 1, the go/no-go for this architecture)

Deploy a throwaway preview with the real `vercel.json`, a Next.js hello page and `server/main.py`. The server imports `src.agent.agent`, runs `ensure_database()` and executes one fixed SQL through `run_query` (no LLM call). Record:

| Check | Pass if |
|---|---|
| `/` serves Next.js and `/api/health` serves FastAPI on one domain | both 200 |
| Function bundle size (build log) | < 400 MB |
| Cold `/api/health` (first call after deploy) | < 6 s |
| Warm `/api/health` | < 300 ms |
| DB built in `/tmp`, fixed SQL returns 9,538 | yes |
| Executor limits active (`current_setting('memory_limit')`) | 488.2 MiB |

Any fail that can't be fixed that evening → switch to 1.4 on evening 2. No more debugging Services.

### 1.4 Fallback if Vercel Python is a poor fit

| Option | Hibernation | Cost | Tradeoffs |
|---|---|---|---|
| **A. FastAPI on Fly.io + Next.js on Vercel** (recommended fallback) | None with `min_machines_running = 1` | Roughly $3–6/month for a 512 MB–1 GB shared-CPU machine (512 MB is too tight next to DuckDB's 512 MB cap; prefer 1 GB). Verify on fly.io/pricing. No free tier for new orgs. | Same Python code via a Dockerfile in `server/`. Next.js Route Handler `/api/ask` proxies server-side, so there's still one public URL and no CORS. The Fly URL is public, so the proxy adds a shared-secret header and FastAPI rejects calls without it. One more account and deploy. |
| B. Render Starter | None on paid ($7/month per third-party pricing). The free tier sleeps after 15 min and takes about 1 min to wake. | $7/month | Simplest Python hosting, but the free tier has the same hibernation problem as Streamlit. |
| C. Keep Streamlit | — | $0 | The default if Nov 12 is a no-go. |

---

## 2. API contract

`POST /api/ask` with body `{"question": "<text>"}`. The body is capped at 2 KB and extra fields are ignored. Always JSON.

```jsonc
{
  "status": "answer",            // answer | empty | clarify | refuse | error | invalid | limited | unavailable
  "summary": "Top 10 countries by total undisbursed amount on IBRD loans (excluding guarantees and regional entries).",
  "columns": [
    {"name": "country",         "label": "Country",           "unit": "plain"},
    {"name": "undisbursed_usd", "label": "Undisbursed (USD)", "unit": "usd"}
  ],
  "rows":         [["Turkiye", 14851719396.98], ["India", 12981866606.32]],   // raw, unrounded
  "display_rows": [["Turkiye", "$14.85B"],      ["India", "$12.98B"]],        // display.format_value
  "chart": {"kind": "bar", "x": "country", "y": "undisbursed_usd"},           // display.choose_chart, or null
  "assumptions": ["Guarantees excluded (is_guarantee = FALSE).", "..."],
  "sql": "SELECT country, SUM(undisbursed_amount_usd) AS undisbursed_usd ...",
  "truncated": false,
  "row_limit": 1000,
  "latency_ms": 3160,            // this request, server side (a cache hit is ~20 ms)
  "answered_ms": 3160,           // the original agent run (same as latency_ms unless cached)
  "attempts": 1,
  "source": "live",              // live | cache | example
  "data_as_of": "2026-09-30",
  "retry_after_s": null          // set when status = limited
}
```

| Case | HTTP | status | API call? | Message source |
|---|---|---|---|---|
| Agent answered with rows | 200 | `answer` | yes (or cache) | agent `message` |
| Agent answered, 0 rows | 200 | `empty` | yes (or cache) | `agent.NO_ROWS` ("No matching rows") |
| Clarify / refuse | 200 | `clarify` / `refuse` | yes (or cache) | agent `message` |
| Agent gave up after retry | 200 | `error` (not cached) | yes | agent `message` ("I couldn't answer that reliably. …") |
| Empty or > 300 characters | 400 | `invalid` | **no** | `service.validate_question` |
| Per-IP limit or global daily cap | 429 | `limited` | **no** | fixed text + `retry_after_s` |
| Bad key, spend cap, overload, Redis down | 503 | `unavailable` | — | `service.friendly_error` |

`GET /api/health` returns `{"ok": true, "db_ready": true, "data_as_of": "2026-09-30", "cache_version": "a1b2c3d4e5f6"}`. It makes no API call and no Redis write.

**Reuse:** `validate_question`, `normalize_question`, `friendly_error`, `dataset_info` from `src/ui/service.py`; `column_unit`, `format_value`, `choose_chart` from `src/ui/display.py`; `agent.answer(question, raise_api_errors=True)`, the same call the Streamlit app makes. `QuestionMeter` (per Streamlit session) is replaced by the Redis limits.

---

## 3. Cost and abuse protection

Everything lives in Python (`server/guard.py`), so there is one place to read. Upstash is called through its REST API with the HTTP client the project already uses (`httpx2`). **No Redis library is added.**

**Request order:** validate input (no Redis) → per-IP request limit → cache lookup (hit → return `source: "cache"`) → per-IP live limit + global daily cap → `agent.answer` → store the result if cacheable → respond.

| Control | Setting (proposal, Khaled to confirm) | Notes |
|---|---|---|
| Input length | 300 characters (client `maxlength` + counter; server `validate_question`) | No API call either way |
| Per-IP burst | 6 requests / minute, all requests including cache hits | Fixed window: `INCR rl:m:{ip}:{minute}` + `EXPIRE 60` |
| Per-IP live questions | 20 / day | Counts only requests that reach the model |
| Global live questions | 100 / day (about $1/day at about $0.01 per question) | Checked after the cache, so cached answers keep working after the cap |
| Answer cache | Key `ans:{cache_version}:{sha256(normalized question)}`, TTL 30 days | `cache_version` = first 12 hex chars of sha256(system prompt + model + effort + snapshot), so a prompt change invalidates the cache automatically. Caches `answer`, `empty`, `clarify`, `refuse`; never `error` (same as Streamlit). |
| IP | `x-real-ip`, which Vercel overwrites so a client can't spoof it ([request headers](https://vercel.com/docs/headers/request-headers)); stored only as a salted sha256 prefix | No raw IPs in Redis. In fallback A, the Next.js proxy forwards it in a header next to the shared secret. |
| Redis unreachable | **Fail closed** for live questions (`unavailable`); the examples still work (static JSON) | Cost and correctness before availability |
| API key | Vercel env var, **Production only, marked Sensitive**, read only by the Python service. A **separate key** in the `ibrd-demo` workspace from the Streamlit key, so either can be revoked alone. Never `NEXT_PUBLIC_*`. | Go/no-go greps the built `web/.next` for `sk-ant` |
| Backstop | $10 spend cap on the `ibrd-demo` workspace | A 402 billing error maps to "Demo limit reached" via `friendly_error` |

Upstash free tier: 500K commands/month, 250 MB, 10 GB bandwidth, 1 database ([pricing](https://upstash.com/pricing/redis)). A live question uses about 6 commands, so the free tier is far more than needed. Provisioned through the Vercel Marketplace, which injects the REST URL and token as env vars (names confirmed at setup).

---

## 4. Perceived performance

**Precomputed examples.** `scripts/precompute_examples.py` calls the real `agent.answer()` on the 4 `EXAMPLES` from `app.py` (about $0.04), builds the same JSON as `/api/ask` with `source: "example"`, and writes `web/src/data/examples.json` with `computed_at`, `git_commit`, `model`, `effort` and `cache_version`. The UI labels these **"Cached example · computed by the live agent on <date>"**. Clicking an example renders instantly and makes no network call. A pytest checks that `examples.json`'s `cache_version` matches the current prompt hash, so a prompt change can't silently leave stale examples. **The JSON is never hand-edited;** to change an example, re-run the script.

**Progress states for live questions.** `agent.answer()` is a single call and must not change, so the API can't stream real stage events. The UI therefore shows:

| Stage | Shown when | Honest because |
|---|---|---|
| Understanding the question | immediately | request sent |
| Writing SQL | after about 0.7 s, until the response arrives | the model call is the long part |
| Checking the SQL | ticked when the response arrives | the server confirms it ran the validator |
| Running it on the data | ticked right after (150 ms) | the server confirms it ran the query |

If `attempts == 2`, the meta line says "Retried once after the first SQL was rejected." Real per-stage streaming needs hooks in `agent.py`, so it waits until after Nov 17.

**Skeletons, not spinners.** While loading, the answer card keeps its final shape: a summary line, 6 bar placeholders, 3 assumption lines. A slow 1.4 s opacity pulse, static under reduced motion. Space is reserved so nothing jumps when the answer lands.

**No model or effort changes.** Same `claude-sonnet-5-5`, effort `high`.

---

## 5. Design direction: "Calm ledger"

One direction: calm, data-first, editorial. It should read like a well-set annual report table, not a dashboard. The answer sentence and the number are the loudest things on the page. The UI recedes.

*Skills note:* the design skills named in the brief (Emil Kowalski's, impeccable, taste, web-design-guidelines) are not installed on this machine. This direction follows the installed **dataviz** skill: its mark specs, and its palette validator, which was run on the colours below.

### 5.1 Type

`next/font/google` self-hosts the fonts at build time: no runtime request to Google and no npm dependency. Scale ratio about 1.25.

| Role | Font | Size / line height | Weight | Notes |
|---|---|---|---|---|
| Page title | Source Serif 4 | 39/45 (31/36 on mobile) | 600 | −0.01em |
| Answer summary | Source Serif 4 | 21/28 | 400 | max 58ch |
| Clarify message | Source Serif 4 | 22/31 | 400 | |
| Hero number | Inter | 56/56 | 600 | −0.02em, proportional figures |
| Body | Inter | 16/25 | 400 | |
| Table, UI | Inter | 14/20 | 400, headers 600 | `tabular-nums` in number columns |
| Meta, captions | Inter | 13/18 | 400 | muted ink |
| Overline labels | Inter | 12, caps, +0.06em | 600 | "ASSUMPTIONS", "TRY AN EXAMPLE" |
| SQL | system monospace | 13/21 | 400 | wraps (`pre-wrap`, `overflow-wrap:anywhere`) |

### 5.2 Colour

Not World Bank colours: no navy or cyan, no logo. The accent is teal-green. All text tokens pass WCAG AA (≥ 4.5:1) on both page and card. Ratios computed, not eyeballed.

| Token | Light | Contrast on page | Dark | Contrast on page |
|---|---|---|---|---|
| page | `#f8f7f3` | — | `#121211` | — |
| surface (cards, charts) | `#fdfcf9` | — | `#1b1a18` | — |
| ink | `#1b1a17` | 16.2 | `#eeece6` | 15.9 |
| ink-2 | `#55534c` | 7.2 | `#c4c1b8` | 10.4 |
| muted (smallest text) | `#6f6c64` | 4.9 | `#9a978e` | 6.4 |
| hairline / rule | `#e4e2db` / `#cfccc3` | — | `#2d2c29` / `#3a3935` | — |
| accent (series, button) | `#007d61` | 4.8 | `#29a288` | 5.9 |
| accent-ink (links) | `#00614f` | 6.9 | `#5cc4ab` | 8.9 |
| clarify (ochre) | `#8a5a00` on `#f6eedc` | 5.5 | `#e0b04a` on `#2b2416` | 9.4 |
| critical (error only) | `#b42f2f` | 5.8 | `#ef7b7b` | 7.0 |

Palette validator (dataviz `validate_palette.js`): series 1 passes lightness band, chroma floor and contrast in both modes. A second series, if ever needed, is ochre (`#b3621e` light / `#ce7a3b` dark). Light-mode CVD separation is 7.9, in the warn band, so it is allowed **only with direct labels**. Today every chart is single-series (`choose_chart` allows exactly two columns), so no legend is needed.

Dark mode follows the OS by default, with a manual toggle (stored per browser). It is its own set of steps, not an inversion.

### 5.3 Numbers

The rules come from `display.format_value`, computed in Python so both UIs agree:

| Kind | Format | Example |
|---|---|---|
| US$ | largest unit the rounded value reaches; B 2 dp, M 1 dp, K 1 dp | `$14.85B`, `$456.7M`, `$12.3K`, `$512.40` |
| Share (0–1) | percent, 1 dp; tiny values `<0.1%` | `12.4%` |
| Counts | thousands separators | `9,538` |
| Fiscal years | no separator; `FY` prefix on axes | `2024`, `FY2024` |
| Dates | `Sep 30, 2026` | |
| NULL | muted em dash `—` | |
| Exact value | Full unrounded US$ on hover (desktop), and a **"Show exact values"** switch in the table for touch | `$14,851,719,396.98` |

### 5.4 Tables and charts

- **Table:** hairline row rules, no zebra stripes, no vertical lines. Numbers right-aligned in tabular figures. Header sticky past 15 rows, body max 480 px with internal scroll. On mobile the first column is sticky while the table scrolls sideways inside the card, so the page never scrolls sideways. A rank column only for "top N" results. If truncated: "Showing the first 1,000 rows. Ask a narrower question to see the rest."
- **Chart and table** are two tabs on the same result. The default is Chart when `choose_chart` returns one; the table is always available as the accessible view.
- **Bar** (ranking): horizontal, single teal, 18 px thick (≤ 24), 4 px rounded data end, square at the baseline, zero baseline always. A direct value label at each bar tip, so no axis or gridlines. Long names are ellipsized with the full name on hover. Hover lightens the bar and the tooltip shows the exact value.
- **Line** (fiscal-year series): 2 px line, 8 px markers with a 2 px surface ring, y axis from zero with compact ticks (`$10B`), hairline gridlines, x ticks `FY2020`. Only the last point is labelled. Crosshair + tooltip on hover.
- **Axis and caption labels** use the plain-English column label (section 6), e.g. "Undisbursed (USD), by country".
- Charts are hand-built SVG/HTML (two forms only), so there is **no chart library**.

### 5.5 States

| State | Treatment |
|---|---|
| Idle | Examples list (4 rows, "instant" tag); input focused on desktop only |
| Loading | 4-step progress list + skeleton card (section 4); Ask button disabled with "Asking…" |
| Answer, many rows | Summary sentence (serif) → Chart/Table tabs → Assumptions (always visible) → SQL (collapsed, copy button) → meta line |
| Answer, single value (1×1) | Hero number + label line, caveat callout if an assumption flags a partial year, then the same sections |
| Empty | "No matching rows" + assumptions + SQL, so the reader sees what was searched |
| Clarify | Ochre "I need a bit more detail" heading with icon, the question in serif, "Add that detail to your question above and ask again. Nothing was run." The original question stays in the input. |
| Refuse | **Neutral ink**, not red (refusing is correct behaviour): "I can't answer that from this data" + the agent's reason, which says what it *can* answer |
| Error | Critical icon + "I couldn't answer that reliably" + reason; "SQL attempted" collapsed |
| Limited | Neutral: "You've asked a lot of questions in a short time. Try again in 40 s." (countdown). Daily cap: "Demo limit reached for today. The four examples still work." |
| Invalid | Inline under the input, no card, no request |
| Unavailable / offline | "Demo is temporarily unavailable" / "Couldn't reach the server", plus Retry |

Status colours never carry meaning alone: each state has an icon and a text label.

### 5.6 Layout and motion

- **Layout:** one column, max 720 px, 16 px gutters (24 px from 640 px up). Tap targets ≥ 44 px. No sticky input. The footer carries the attribution.
- **Motion:** only opacity and transform, 120–200 ms, `cubic-bezier(.2,.8,.2,1)`. The card enters with a 180 ms fade and 4 px rise. Bars grow from the baseline once, 420 ms, 25 ms stagger (not on tab switch). Progress ticks take 150 ms. **No count-up on numbers:** the number is the fact, not an animation. `prefers-reduced-motion` turns all of it off.
- **Footer:** "Independent project, not affiliated with the World Bank." + "Data: World Bank, IBRD Statement of Loans and Guarantees (DS00047), CC BY 4.0. Snapshot of Sep 30, 2026; columns renamed and two derived flags added." + GitHub link.

---

## 6. UX fixes carried over from Streamlit

| Fix | How |
|---|---|
| Plain-English column labels | `server/labels.py`, returned as `columns[].label`. (1) A dictionary column uses its original name in sentence case, with "(US$)" → "(USD)": `borrowers_obligation_usd` → "Borrower's obligation (USD)", `board_approval_fy` → "Board approval fiscal year". (2) An alias is split on `_`: trailing `usd` → "(USD)", trailing `share` → "(%)", `fy` → "fiscal year", `cy` → "calendar year", `avg` → "average"; first letter capitalised: `total_owed_usd` → "Total owed (USD)", `loan_count` → "Loan count". Tested against every alias in the saved dev results. |
| Axis labels | The same label string feeds the chart caption, axis title and tooltip |
| Single value as one large number | 1 row × 1 column → hero number (mockup "Single value") |
| Wrapped SQL | `white-space: pre-wrap; overflow-wrap: anywhere`, plus a copy button |
| Visible latency | Meta line: "Live · 3.1 s" or "Cached answer · originally 3.1 s" or "Cached example · computed Nov 1" |

`display.py` stays unchanged. Labels are new code in `server/`, so the Streamlit app is not touched.

---

## 7. Tasks, risks, go/no-go

### 7.1 Tasks (1 evening ≈ 3 h)

| # | Date | Task | Est. | Done when |
|---|---|---|---|---|
| 1 | Wed Nov 4 | Spike (1.3): `vercel.json`, Next.js hello in `web/`, `server/main.py` health + fixed SQL; Upstash + Vercel env vars | 1 | All spike checks pass, or fallback chosen |
| 2 | Thu Nov 5 | `POST /api/ask`: response builder, status mapping, `labels.py`; pytest with a fake agent | 1 | Contract tests pass offline |
| 3 | Fri Nov 6 | `guard.py`: limits, daily cap, cache, fail-closed; pytest with a fake Redis | 1 | Guard tests pass offline |
| 4 | Sat Nov 7 | `precompute_examples.py` (one live run, about $0.04) + version test; page shell: tokens, type, header, input, examples, footer | 1 | Examples render from JSON with no network call |
| 5 | Sun Nov 8 | Answer rendering: summary, table (exact-values switch), bar + line, hero number, assumptions, SQL | 1.5 | Matches mockup at 390 px and 1200 px |
| 6 | Mon Nov 9 | Progress + skeleton; clarify / refuse / error / empty / limited / invalid / unavailable; dark mode | 1 | Every row in 5.5 reachable |
| 7 | Tue Nov 10 | Production deploy, separate API key, cron, run the go/no-go list, fix | 1 | List passes on production |
| 8 | Wed Nov 11 | **Buffer**; README "v2" section and screenshot | 0.5–1 | — |
| | **Thu Nov 12** | **Go/no-go** | | |

Total: about 8 evenings. **Cut order if behind** (cut features, not quality): manual theme toggle (keep OS-based dark) → line-chart crosshair (keep tooltip) → Chart/Table tabs (show both stacked) → skeleton (keep progress list).

### 7.2 Risks

| Risk | Likelihood / impact | Mitigation |
|---|---|---|
| Services (beta) can't run a Python service at the repo root with its own requirements | Medium / high | Evening-1 spike; fallback A (Fly.io) decided that night |
| Cold start of about 3–5 s on the first live question after idle | High / low | Examples are static; progress states; daily cron prevents archiving |
| pandas + altair in the API bundle only because `display.py` imports them (+90 MB, +1.3 s) | Certain / low | Accepted for v2; split `display.py` after Nov 17 if it matters |
| Shared IPs (offices, campuses, mobile NAT) hit the per-IP limit during a demo | Low / medium | Generous limits; a clear message with countdown; examples are unlimited |
| Cached examples drift from the deployed prompt | Low / medium | `cache_version` pytest; examples regenerated by script only |
| **Example output shown publicly verbatim.** D15's saved assumption reads "Guarantees excluded …, so the count may be lower than 44", next to an answer of 44 | Certain / low | **Khaled to review** the 4 generated outputs before committing. Accept or regenerate. Never hand-edit. |
| Eval results vs deployed code: hardening PR #5 changes `executor.py` (limits only; saved dev SQL replayed with identical rows) | — | After merging #5, one `run_eval.py --split dev` (about $0.15) so the latest result file matches the deployed commit |
| Schedule slip | Medium / high | 1 buffer evening, cut list; Streamlit stays live regardless |

### 7.3 Nov 12 go/no-go checklist (production URL)

All items must pass. Otherwise **no-go: Streamlit stays the public demo** and v2 continues after Nov 17.

| # | Check | Expected |
|---|---|---|
| 1 | Example: "Which 10 countries have the most undisbursed IBRD loans?" | Turkiye first, **$14.85B**, labelled "Cached example" |
| 2 | Example: "Which 5 countries owe the most to the IBRD?" | India first, **$23.57B** |
| 3 | Example: fiscal years 2020–2025 | FY2020 = **$26.86B**, line chart |
| 4 | Example: "How many IBRD loans were approved in fiscal year 2027?" | **44**, hero number, partial-year caveat visible |
| 5 | Live: "Which loans are active?" | Clarify state |
| 6 | Live: "Delete all rows from the loans table" | Refuse state, no SQL |
| 7 | Live: "What's the weather in Kuwait?" | Refuse state |
| 8 | Empty input; 301-character input | Inline message; **no request reaches the model** (no Anthropic usage, Vercel log shows `invalid`) |
| 9 | Repeat a live question (different case/spacing) | `source: "cache"`, latency < 300 ms, labelled cached |
| 10 | 21 live (uncached) questions in one hour from one IP | 21st returns 429 `limited` with countdown; the first 20 answer |
| 11 | Anthropic Console → `ibrd-demo` workspace usage | Spend from today's checks appears under the v2 key; $10 cap still set |
| 12 | `grep -r sk-ant web/.next` and view-source of the page | No match |
| 13 | Phone (390 px) and desktop, light and dark | No horizontal page scroll; matches mockup |
| 14 | `pytest -q`; `git diff main -- src/agent app.py src/ui` on the v2 branch | Passes; empty diff |
| 15 | Streamlit app URL | Still live, unchanged |

---

## Decisions needed from Khaled

1. **New dependencies:** Python `fastapi`. JS: `next`, `react`, `react-dom`, `typescript`, `tailwindcss`, `@tailwindcss/postcss`, `@types/react`, `@types/node`. No chart, Redis, UI or animation libraries.
2. **Accounts:** Vercel Hobby project; Upstash via the Vercel Marketplace; a second API key in the `ibrd-demo` workspace.
3. **Limits:** 6/min and 20/day per IP; 100 live questions/day globally (section 3).
4. **Fallback budget:** OK to spend about $3–6/month on Fly.io if the spike fails?
5. **Mockup direction:** approve "Calm ledger" or request changes before evening 4.

---

## Decisions (Khaled, Nov 3, 2026)

These replace the proposals above where they differ.

| # | Topic | Decision |
|---|---|---|
| 1 | Rate limits | **20 live questions per hour per IP (raised from 10 on Nov 6); 150 live questions per day globally.** Cache hits and cached examples don't count toward either. No separate per-minute burst limit (replaces the 6/min and 20/day proposal in section 3). |
| 2 | Fallback | Fly.io (section 1.4, option A) is used **only if the gate fails**, and needs Khaled's approval first (account + card). |
| 3 | Cached examples | Generated **once** by the real agent from merged `main`, committed as-is, labelled "Cached example". If D15's caveat is misleading again (e.g. "the count may be lower than 44" next to 44), replace example 4 with D09. **Never reroll or hand-edit.** |
| 4 | Mockup feedback | None given. "Calm ledger" proceeds as specified in section 5. |
| 5 | New dependencies | Approved as listed under "Decisions needed" (FastAPI; Next.js, React, TypeScript, Tailwind and their types). Test-only: Playwright for the frontend smoke test. |
