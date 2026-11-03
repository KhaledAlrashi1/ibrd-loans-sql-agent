"""v2 API: POST /api/ask and GET /api/health. Imports the agent; never changes it.

Request order for /api/ask (docs/v2-plan.md, section 3):
  validate input (no Redis, no model) -> cache lookup (hit: return, not counted) -> API key configured?
  -> per-IP hourly limit + global daily cap -> agent.answer -> cache the result if cacheable -> respond.

Every response is JSON with a "status". Failures never show a stack trace: anthropic errors map to the
same friendly text as the Streamlit app (service.friendly_error); Redis failures fail closed.
"""

import json
import logging
import os
import time

import anthropic
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException

from scripts.build_db import ensure_database
from src.agent import agent, config
from src.agent.executor import run_query
from src.ui import service

from server import contract, guard

MAX_BODY_BYTES = 2048
NOT_JSON = "Please send a JSON body like {\"question\": \"...\"}."

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
log = logging.getLogger("ibrd_api")

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

try:  # once per instance, during the cold start rather than inside the first request
    ensure_database()
    DB_ERROR = None
except Exception as e:  # reported by /api/health; /api/ask answers "unavailable"
    log.exception("database setup failed")
    DB_ERROR = type(e).__name__


def run_agent(question: str):
    """The one call to the model. Tests replace this function."""
    return agent.answer(question, raise_api_errors=True)


def api_key_configured() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY")) or config.SECRETS_PATH.exists()


def client_ip(request: Request) -> str:
    """The IP the per-IP limit counts. Only headers Vercel sets itself (it overwrites any client value).

    X-Forwarded-For is never read: its first hop is whatever the client sent. Off Vercel (local dev only),
    the socket peer is used.
    """
    for name in ("x-vercel-forwarded-for", "x-real-ip"):
        value = request.headers.get(name, "").split(",")[0].strip()
        if value:
            return value
    return request.client.host if request.client else "unknown"


def reply(http_status: int, body: dict, started: float) -> JSONResponse:
    log.info("ask status=%s source=%s http=%d ms=%d", body["status"], body.get("source", "-"), http_status,
             round((time.perf_counter() - started) * 1000))
    return JSONResponse(body, status_code=http_status, headers={"Cache-Control": "no-store"})


def answer_question(question: str, ip: str, started: float) -> tuple[int, dict]:
    """Everything after input validation. Runs in a worker thread (Redis and the model are blocking)."""
    def elapsed() -> int:
        return round((time.perf_counter() - started) * 1000)

    store = guard.get_store()
    if store is None or DB_ERROR:
        return 503, contract.notice("unavailable", service.DEMO_UNAVAILABLE)
    key = contract.cache_key(question)
    try:
        hit = guard.cache_get(store, key)
        if hit is not None:
            return 200, contract.respond(hit, "cache", elapsed())
        if not api_key_configured():
            return 503, contract.notice("unavailable", service.NO_API_KEY)
        limited = guard.check_live(store, ip)
    except guard.StoreError as e:
        log.warning("redis failed: %s", e)
        return 503, contract.notice("unavailable", service.DEMO_UNAVAILABLE)
    if limited:
        return 429, contract.notice("limited", limited.message, limited.retry_after_s, scope=limited.scope)

    try:
        result = run_agent(question)
    except anthropic.APIError as e:
        log.warning("model call failed: %s", type(e).__name__)
        return 503, contract.notice("unavailable", service.friendly_error(e))
    payload = contract.build_payload(result)
    if payload["status"] in contract.CACHEABLE:
        try:
            guard.cache_put(store, key, payload)
        except guard.StoreError as e:  # the answer is still good; it just isn't cached
            log.warning("cache write failed: %s", e)
    return 200, contract.respond(payload, "live", elapsed())


@app.post("/api/ask")
async def ask(request: Request) -> JSONResponse:
    started = time.perf_counter()
    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        return reply(400, contract.notice("invalid", service.TOO_LONG), started)
    try:
        data = json.loads(body)
        question = data.get("question") if isinstance(data, dict) else None
    except ValueError:
        return reply(400, contract.notice("invalid", NOT_JSON), started)
    if question is not None and not isinstance(question, str):
        return reply(400, contract.notice("invalid", NOT_JSON), started)
    problem = service.validate_question(question)
    if problem:
        return reply(400, contract.notice("invalid", problem), started)

    status, payload = await run_in_threadpool(answer_question, question.strip(), client_ip(request), started)
    return reply(status, payload, started)


@app.get("/api/health")
def health() -> JSONResponse:
    """No model call and no Redis write. Runs one fixed read-only SELECT, so it also proves the executor works."""
    ok = DB_ERROR is None
    rows = None
    if ok:
        try:
            rows = run_query(f"SELECT COUNT(*) FROM {config.TABLE}").rows[0][0]
        except Exception:
            log.exception("health query failed")
            ok = False
    body = {"ok": ok, "db_ready": ok, "rows": rows, "data_as_of": contract.data_as_of(),
            "cache_version": contract.cache_version()}
    return JSONResponse(body, status_code=200 if ok else 503, headers={"Cache-Control": "no-store"})


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    message = "Not found." if exc.status_code == 404 else "Method not allowed." if exc.status_code == 405 else "Bad request."
    return JSONResponse(contract.notice("invalid", message), status_code=exc.status_code)


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    log.exception("unexpected error")
    return JSONResponse(contract.notice("unavailable", service.GENERIC_ERROR), status_code=500)
