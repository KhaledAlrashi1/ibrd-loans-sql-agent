"""POST /api/ask and GET /api/health with the agent and Redis replaced: offline, no API calls."""

import time

import anthropic
import httpx2
import pytest
from fastapi.testclient import TestClient

from src.agent.agent import NO_ROWS, AgentResult
from src.ui import service

from server import contract, guard, main


REAL_GET_STORE = guard.get_store


class FailingStore(guard.MemoryStore):
    def get(self, key):
        raise guard.StoreError("connection refused")

    def incr(self, key, ttl_s):
        raise guard.StoreError("connection refused")


class Calls:
    """A fake agent: returns `result` (or raises `error`) and records each question it was asked."""

    def __init__(self):
        self.questions: list[str] = []
        self.result = AgentResult(
            question="q", status="answer", sql="SELECT country, SUM(undisbursed_amount_usd) AS undisbursed_usd ...",
            columns=["country", "undisbursed_usd"], rows=[["Turkiye", 14851719396.98], ["India", 12981866606.32]],
            assumptions=["Guarantees excluded (is_guarantee = FALSE)."], message="Top countries.", attempts=1,
            latency_s=3.16)
        self.error: Exception | None = None

    def __call__(self, question: str) -> AgentResult:
        self.questions.append(question)
        if self.error:
            raise self.error
        return self.result


@pytest.fixture
def store():
    return guard.MemoryStore()


@pytest.fixture
def calls(monkeypatch, store):
    fake = Calls()
    monkeypatch.setattr(main, "run_agent", fake)
    monkeypatch.setattr(guard, "get_store", lambda: store)
    monkeypatch.setattr(main, "api_key_configured", lambda: True)
    return fake


@pytest.fixture
def client(calls):
    return TestClient(main.app, raise_server_exceptions=False)


def ask(client, question, ip="203.0.113.7"):
    return client.post("/api/ask", json={"question": question}, headers={"x-real-ip": ip})


def api_error(cls, status):
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls("boom", response=httpx2.Response(status, request=request), body=None)


# --- statuses -----------------------------------------------------------------------------------------------

def test_answer_has_the_contract_fields(client, calls):
    r = ask(client, "Which countries have the most undisbursed loans?")
    body = r.json()
    assert r.status_code == 200 and body["status"] == "answer" and body["source"] == "live"
    assert body["rows"] == [["Turkiye", 14851719396.98], ["India", 12981866606.32]]  # raw, unrounded
    assert body["display_rows"] == [["Turkiye", "$14.85B"], ["India", "$12.98B"]]
    assert body["columns"] == [{"name": "country", "label": "Country / economy", "unit": "plain"},
                               {"name": "undisbursed_usd", "label": "Undisbursed (USD)", "unit": "usd"}]
    assert body["chart"] == {"kind": "bar", "x": "country", "y": "undisbursed_usd"}
    assert body["assumptions"] and body["sql"].startswith("SELECT")
    assert body["answered_ms"] == 3160 and body["attempts"] == 1 and body["data_as_of"] == "2026-09-30"
    assert body["retry_after_s"] is None and isinstance(body["latency_ms"], int)


def test_empty_result(client, calls):
    calls.result = AgentResult(question="q", status="answer", sql="SELECT 1 WHERE FALSE", columns=["x"], rows=[],
                               message=NO_ROWS, attempts=1)
    body = ask(client, "Loans to Atlantis?").json()
    assert body["status"] == "empty" and body["summary"] == "No matching rows" and body["sql"]


@pytest.mark.parametrize("status", ["clarify", "refuse"])
def test_clarify_and_refuse_have_no_sql(client, calls, status):
    calls.result = AgentResult(question="q", status=status, message="Do you mean X or Y?", attempts=1)
    r = ask(client, "Which loans are active?")
    assert r.status_code == 200 and r.json()["status"] == status and r.json()["sql"] == ""


def test_agent_error_is_shown_and_not_cached(client, calls):
    calls.result = AgentResult(question="q", status="error", sql="SELECT nope", attempts=2,
                               message="I couldn't answer that reliably. The query failed: ...")
    first = ask(client, "Something hard")
    second = ask(client, "Something hard")
    assert first.status_code == 200 and first.json()["status"] == "error" and first.json()["attempts"] == 2
    assert second.json()["source"] == "live" and len(calls.questions) == 2


def test_values_are_json_safe_and_formatted(client, calls):
    from datetime import date
    from decimal import Decimal
    calls.result = AgentResult(
        question="q", status="answer", sql="SELECT ...", attempts=1,
        columns=["board_approval_fy", "loan_count", "board_approval_date", "cancelled_share", "avg_rate", "note"],
        rows=[[2024, 9538, date(2026, 9, 30), 0.124, Decimal("4.25"), None],
              [2025, 12, date(2025, 1, 2), float("nan"), 0.03456, "x"]])
    body = ask(client, "mixed").json()
    assert body["rows"][0] == [2024, 9538, "2026-09-30", 0.124, 4.25, None]
    assert body["rows"][1][3] is None  # NaN is not valid JSON
    assert body["display_rows"][0] == ["2024", "9,538", "Sep 30, 2026", "12.4%", "4.25", ""]
    assert body["display_rows"][1][4] == "0.03456"


# --- input validation: no model call, no Redis ----------------------------------------------------------------

@pytest.mark.parametrize("payload, message", [
    ({"question": ""}, service.EMPTY_QUESTION),
    ({"question": "   "}, service.EMPTY_QUESTION),
    ({}, service.EMPTY_QUESTION),
    ({"question": "x" * 301}, service.TOO_LONG),
    ({"question": 42}, main.NOT_JSON),
    (["question"], service.EMPTY_QUESTION),
])
def test_invalid_input_never_reaches_the_model(client, calls, store, payload, message):
    r = client.post("/api/ask", json=payload)
    assert r.status_code == 400 and r.json() == {"status": "invalid", "message": message, "retry_after_s": None}
    assert calls.questions == [] and store.data == {}


def test_300_characters_is_allowed(client, calls):
    assert ask(client, "x" * 300).status_code == 200


def test_not_json_and_oversized_body(client, calls):
    assert client.post("/api/ask", content=b"question=hi").json()["message"] == main.NOT_JSON
    big = client.post("/api/ask", content=b'{"question": "' + b"x" * 3000 + b'"}')
    assert big.status_code == 400 and big.json()["status"] == "invalid"
    assert calls.questions == []


def test_extra_fields_are_ignored_and_question_is_stripped(client, calls):
    r = client.post("/api/ask", json={"question": "  Hello  ", "model": "opus", "limit": 999})
    assert r.status_code == 200 and calls.questions == ["Hello"]


# --- cache ------------------------------------------------------------------------------------------------------

def test_repeat_question_is_served_from_cache(client, calls):
    ask(client, "Which 5 countries owe the most?")
    hit = ask(client, "  which 5 COUNTRIES   owe the most?  ")
    body = hit.json()
    assert hit.status_code == 200 and body["source"] == "cache" and body["answered_ms"] == 3160
    assert body["latency_ms"] < 300 and len(calls.questions) == 1


def test_cache_key_changes_with_the_cache_version(monkeypatch):
    before = contract.cache_key("Q")
    monkeypatch.setattr(contract, "PAYLOAD_VERSION", "test")
    assert contract.cache_key("Q") != before
    assert contract.cache_key("  q ") == contract.cache_key("Q")


# --- limits -----------------------------------------------------------------------------------------------------

def test_limits_are_20_per_hour_per_ip_and_150_per_day():
    assert (guard.HOURLY_PER_IP, guard.DAILY_TOTAL) == (20, 150)


def test_twenty_first_live_question_in_an_hour_is_limited(client, calls):
    for i in range(guard.HOURLY_PER_IP):
        assert ask(client, f"question {i}").status_code == 200
    r = ask(client, "one more")
    body = r.json()
    assert r.status_code == 429 and body["status"] == "limited" and body["scope"] == "ip"
    assert 0 < body["retry_after_s"] <= 3600 and body["message"] == guard.PER_IP_MESSAGE
    assert len(calls.questions) == guard.HOURLY_PER_IP


def test_cache_hits_do_not_count(client, calls):
    for _ in range(guard.HOURLY_PER_IP + 5):
        assert ask(client, "same question").status_code == 200
    assert len(calls.questions) == 1
    assert ask(client, "a new question").status_code == 200


def test_limits_are_per_ip(client, calls):
    for i in range(guard.HOURLY_PER_IP):
        ask(client, f"q{i}", ip="198.51.100.1")
    assert ask(client, "next", ip="198.51.100.1").status_code == 429
    assert ask(client, "next", ip="198.51.100.2").status_code == 200


def test_spoofed_x_forwarded_for_cannot_reset_the_count(client, calls):
    """A new X-Forwarded-For on every request doesn't help: the count follows the IP Vercel sets."""
    def spoof(question, fake):
        headers = {"x-vercel-forwarded-for": "198.51.100.20", "x-real-ip": "198.51.100.20", "x-forwarded-for": fake}
        return client.post("/api/ask", json={"question": question}, headers=headers)

    for i in range(guard.HOURLY_PER_IP):
        assert spoof(f"q{i}", f"10.0.0.{i}, 198.51.100.20").status_code == 200
    assert spoof("next", "10.9.9.9").status_code == 429
    assert len(calls.questions) == guard.HOURLY_PER_IP


def test_x_forwarded_for_is_ignored_without_vercel_headers(client, calls):
    for i in range(guard.HOURLY_PER_IP):
        client.post("/api/ask", json={"question": f"q{i}"}, headers={"x-forwarded-for": f"10.0.0.{i}"})
    r = client.post("/api/ask", json={"question": "next"}, headers={"x-forwarded-for": "10.9.9.9"})
    assert r.status_code == 429  # all twenty-one counted against the socket peer


def test_global_daily_cap(client, calls, monkeypatch):
    monkeypatch.setattr(guard, "DAILY_TOTAL", 3)
    for i in range(3):
        assert ask(client, f"q{i}", ip=f"192.0.2.{i}").status_code == 200
    body = ask(client, "q-over", ip="192.0.2.99").json()
    assert body["status"] == "limited" and body["scope"] == "daily" and body["message"] == guard.DAILY_MESSAGE
    assert ask(client, "q0", ip="192.0.2.99").json()["source"] == "cache"  # cached answers still work
    assert len(calls.questions) == 3


def test_over_limit_ip_does_not_use_up_the_global_cap(client, calls, store):
    for i in range(guard.HOURLY_PER_IP + 20):
        ask(client, f"spam {i}", ip="198.51.100.9")
    day_counts = [int(v) for k, (v, _) in store.data.items() if k.startswith("cap:d:")]
    assert day_counts == [guard.HOURLY_PER_IP]


def test_ip_is_stored_hashed(client, calls, store):
    ask(client, "hello", ip="203.0.113.250")
    assert not any("203.0.113.250" in k for k in store.data)


def test_window_reset_after_the_hour(store):
    t = 1_800_000_000.0
    for _ in range(guard.HOURLY_PER_IP):
        assert guard.check_live(store, "1.2.3.4", now=t) is None
    limited = guard.check_live(store, "1.2.3.4", now=t)
    assert limited and limited.retry_after_s == int((t // 3600 + 1) * 3600 - t)
    assert guard.check_live(store, "1.2.3.4", now=t + 3600) is None


# --- failures: friendly JSON, never a stack trace -------------------------------------------------------------------

@pytest.mark.parametrize("error, message", [
    (api_error(anthropic.RateLimitError, 429), service.DEMO_LIMIT),
    (api_error(anthropic.AuthenticationError, 401), service.DEMO_UNAVAILABLE),
    (api_error(anthropic.InternalServerError, 500), service.GENERIC_ERROR),
    (api_error(anthropic.APIStatusError, 402), service.DEMO_LIMIT),
])
def test_api_errors_map_to_friendly_messages(client, calls, error, message):
    calls.error = error
    r = ask(client, "anything")
    assert r.status_code == 503 and r.json() == {"status": "unavailable", "message": message, "retry_after_s": None}


def test_unexpected_exception_has_no_traceback(client, calls):
    calls.error = RuntimeError("secret internals at /var/task/src/agent/llm.py")
    r = ask(client, "anything")
    assert r.status_code == 500 and r.json()["message"] == service.GENERIC_ERROR
    assert "Traceback" not in r.text and "/var/task" not in r.text


def test_redis_down_fails_closed(client, calls, monkeypatch):
    monkeypatch.setattr(guard, "get_store", lambda: FailingStore())
    r = ask(client, "anything")
    assert r.status_code == 503 and r.json()["message"] == service.DEMO_UNAVAILABLE and calls.questions == []


def test_no_redis_on_vercel_fails_closed(client, calls, monkeypatch):
    monkeypatch.setattr(guard, "get_store", lambda: REAL_GET_STORE({"VERCEL": "1"}))
    r = ask(client, "anything")
    assert r.status_code == 503 and calls.questions == []


def test_missing_api_key(client, calls, monkeypatch):
    monkeypatch.setattr(main, "api_key_configured", lambda: False)
    r = ask(client, "anything")
    assert r.status_code == 503 and r.json()["message"] == service.NO_API_KEY and calls.questions == []


def test_unknown_route_and_method_are_json(client):
    assert client.get("/api/nope").json()["status"] == "invalid"
    r = client.get("/api/ask")
    assert r.status_code == 405 and r.json()["status"] == "invalid"


# --- store selection and health -------------------------------------------------------------------------------------

def test_store_selection():
    assert isinstance(guard.get_store({}), guard.MemoryStore)
    assert guard.get_store({"VERCEL": "1"}) is None
    up = guard.get_store({"VERCEL": "1", "KV_REST_API_URL": "https://x.upstash.io", "KV_REST_API_TOKEN": "t"})
    assert isinstance(up, guard.UpstashStore)
    up2 = guard.get_store({"UPSTASH_REDIS_REST_URL": "https://y.upstash.io", "UPSTASH_REDIS_REST_TOKEN": "t"})
    assert isinstance(up2, guard.UpstashStore) and up2.url == "https://y.upstash.io"


class RecordingUpstash(guard.UpstashStore):
    """UpstashStore with the HTTP call replaced by a dict, recording every key it is sent."""

    def __init__(self, namespace, data):
        super().__init__("https://x.upstash.io", "t", namespace)
        self.data, self.keys = data, []

    def pipeline(self, commands):
        replies = []
        for cmd, key, *args in commands:
            self.keys.append(key)
            if cmd == "INCR":
                self.data[key] = int(self.data.get(key, 0)) + 1
            elif cmd == "SET":
                self.data[key] = args[0]
            replies.append(self.data.get(key) if cmd != "EXPIRE" else 1)
        return replies


def test_redis_keys_are_namespaced_by_vercel_env():
    env = {"VERCEL": "1", "KV_REST_API_URL": "https://x.upstash.io", "KV_REST_API_TOKEN": "t"}
    assert guard.get_store({**env, "VERCEL_ENV": "preview"}).namespace == "preview"
    assert guard.get_store({**env, "VERCEL_ENV": "production"}).namespace == "production"
    assert guard.get_store({k: v for k, v in env.items() if k != "VERCEL"}).namespace == "local"

    shared = {}  # one Redis database behind both environments
    preview, production = RecordingUpstash("preview", shared), RecordingUpstash("production", shared)
    t = 1_800_000_000.0
    for _ in range(guard.HOURLY_PER_IP):
        assert guard.check_live(preview, "1.2.3.4", now=t) is None
    assert guard.check_live(preview, "1.2.3.4", now=t).scope == "ip"
    guard.cache_put(preview, "ans:v:q", {"status": "answer"})

    # Preview used up its hourly limit and cached an answer; production sees fresh counters and no cache.
    assert guard.check_live(production, "1.2.3.4", now=t) is None
    assert guard.cache_get(production, "ans:v:q") is None
    assert guard.cache_get(preview, "ans:v:q") == {"status": "answer"}
    assert all(k.startswith("preview:") for k in preview.keys)
    assert all(k.startswith("production:") for k in production.keys)
    assert shared[f"production:cap:d:{time.strftime('%Y%m%d', time.gmtime(t))}"] == 1


def test_limit_messages():
    assert guard.PER_IP_MESSAGE == "Live questions from your network are limited to 20 per hour."
    assert guard.DAILY_MESSAGE == "This demo has reached today's limit of 150 live questions."


def test_health(client):
    body = client.get("/api/health").json()
    assert body["ok"] and body["db_ready"] and body["rows"] == 9538 and body["data_as_of"] == "2026-09-30"
    assert body["cache_version"] == contract.cache_version()
