"""The /api/ask response body, built from an AgentResult. Shared by the API and scripts/precompute_examples.py.

    payload = build_payload(result)             # everything that comes from the agent run (cacheable)
    body = respond(payload, source="live", latency_ms=3160)

Raw values stay unrounded in "rows". "display_rows" holds the text the UI shows: display.format_value for
US$ and shares (so v2 and Streamlit agree), plus thousands separators for counts, "Sep 30, 2026" for dates,
and "" for NULL (the UI draws a muted dash). The chart choice is display.choose_chart on the raw rows.
"""

import hashlib
import math
from datetime import date, datetime
from decimal import Decimal

from src.agent import config
from src.agent.agent import AgentResult
from src.agent.prompt import build_system_prompt
from src.ui import display, service

from server.labels import column_label

# Bump when the payload shape or display rules change, so cached payloads from older code are not served.
PAYLOAD_VERSION = "1"
CACHEABLE = {"answer", "empty", "clarify", "refuse"}


def data_as_of() -> str:
    return service.dataset_info().end_of_period.isoformat()


def cache_version() -> str:
    """Changes whenever the prompt, model, effort, snapshot or payload rules change."""
    basis = "\n".join([build_system_prompt(), config.MODEL, config.EFFORT, data_as_of(), PAYLOAD_VERSION])
    return hashlib.sha256(basis.encode()).hexdigest()[:12]


def cache_key(question: str) -> str:
    normalized = service.normalize_question(question)
    return f"ans:{cache_version()}:{hashlib.sha256(normalized.encode()).hexdigest()}"


def plain_value(v):
    """A value as DuckDB returned it, made JSON-safe: Decimal -> float, NaN/inf -> None, dates -> ISO text."""
    if isinstance(v, Decimal):
        v = float(v)
    if isinstance(v, float) and not math.isfinite(v):
        return None
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    return str(v)


def format_plain_number(v, name: str) -> str:
    if isinstance(v, int):
        return str(v) if display.YEAR_NAME.search(name.lower()) else f"{v:,}"
    if v == 0 or abs(v) >= 1:
        return f"{v:,.2f}".rstrip("0").rstrip(".")
    return f"{v:.4g}"


def display_text(v, unit: str, name: str) -> str:
    if isinstance(v, Decimal):
        v = float(v)
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return ""
    if isinstance(v, datetime):
        v = v.date()
    if isinstance(v, date):
        return f"{v:%b} {v.day}, {v.year}"
    if isinstance(v, bool):
        return "Yes" if v else "No"
    if display.is_number(v) and unit == display.PLAIN:
        return format_plain_number(v, name)
    return display.format_value(v, unit)


def response_status(result: AgentResult) -> str:
    if result.status == "answer" and not result.rows:
        return "empty"
    return result.status


def build_payload(result: AgentResult) -> dict:
    names = display.unique_names(result.columns)
    units = [display.column_unit(c) for c in result.columns]
    rows = [[float(v) if isinstance(v, Decimal) else v for v in row] for row in result.rows]
    spec = display.choose_chart(names, rows)
    return {
        "status": response_status(result),
        "question": result.question,
        "summary": result.message,
        "columns": [{"name": n, "label": column_label(n), "unit": u} for n, u in zip(names, units)],
        "rows": [[plain_value(v) for v in row] for row in rows],
        "display_rows": [[display_text(v, u, n) for v, u, n in zip(row, units, names)] for row in rows],
        "chart": {"kind": spec.kind, "x": spec.x, "y": spec.y} if spec else None,
        "assumptions": list(result.assumptions),
        "sql": result.sql,
        "truncated": result.truncated,
        "row_limit": config.ROW_LIMIT,
        "answered_ms": round(result.latency_s * 1000),
        "attempts": result.attempts,
        "data_as_of": data_as_of(),
    }


def respond(payload: dict, source: str, latency_ms: int) -> dict:
    return {**payload, "source": source, "latency_ms": latency_ms, "retry_after_s": None}


def notice(status: str, message: str, retry_after_s: int | None = None, **extra) -> dict:
    """Bodies for invalid / limited / unavailable: no agent output, same top-level keys the UI reads."""
    return {"status": status, "message": message, "retry_after_s": retry_after_s, **extra}
