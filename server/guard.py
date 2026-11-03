"""Cost and abuse protection for /api/ask: per-IP hourly limit, global daily cap, shared answer cache.

    store = get_store()                         # Upstash REST in production, memory for local dev only
    hit = cache_get(store, key)                 # a cached agent result (dict) or None; never counted
    limit = check_live(store, ip)               # None, or a Limited to return instead of calling the model
    cache_put(store, key, result_dict)

Limits (Khaled, Nov 3): 10 live questions per hour per IP, 150 per day in total. A question counts as
live only when it gets past the cache, so cache hits and the static examples never count.

Counters are fixed windows: INCR + EXPIRE NX on a key named after the hour (per IP) or the UTC day (global).
The per-IP counter is checked first, so a client that is over its own limit never uses up the global cap.

IPs are stored only as a salted sha256 prefix. The salt is derived from the Redis token, so it is secret
without another environment variable. Any Redis failure raises StoreError; main.py fails closed on it.
"""

import hashlib
import json
import os
import secrets
import threading
import time
from dataclasses import dataclass

import httpx2

HOURLY_PER_IP = 10
DAILY_TOTAL = 150
CACHE_TTL_S = 30 * 24 * 3600
REDIS_TIMEOUT_S = 3.0

# Upstash via the Vercel Marketplace injects KV_REST_API_*; a direct Upstash setup uses UPSTASH_REDIS_REST_*.
URL_VARS = ("KV_REST_API_URL", "UPSTASH_REDIS_REST_URL")
TOKEN_VARS = ("KV_REST_API_TOKEN", "UPSTASH_REDIS_REST_TOKEN")

PER_IP_MESSAGE = "You've asked a lot of questions in a short time."
DAILY_MESSAGE = "Demo limit reached for today. The four examples still work."


class StoreError(Exception):
    """Redis could not be reached or returned an error."""


@dataclass(frozen=True)
class Limited:
    scope: str           # "ip" | "daily"
    message: str
    retry_after_s: int


class UpstashStore:
    """The three Redis operations this app needs, over the Upstash REST API (one pipeline call each)."""

    def __init__(self, url: str, token: str):
        self.url = url.rstrip("/")
        self.salt = hashlib.sha256(b"ibrd-ip-salt:" + token.encode()).hexdigest()
        self.client = httpx2.Client(headers={"Authorization": f"Bearer {token}"}, timeout=REDIS_TIMEOUT_S)

    def pipeline(self, commands: list[list]) -> list:
        try:
            response = self.client.post(f"{self.url}/pipeline", json=commands)
            response.raise_for_status()
            replies = response.json()
        except (httpx2.HTTPError, ValueError) as e:
            raise StoreError(type(e).__name__) from None
        errors = [r["error"] for r in replies if "error" in r]
        if errors:
            raise StoreError(errors[0])
        return [r["result"] for r in replies]

    def incr(self, key: str, ttl_s: int) -> int:
        return int(self.pipeline([["INCR", key], ["EXPIRE", key, ttl_s, "NX"]])[0])

    def get(self, key: str) -> str | None:
        return self.pipeline([["GET", key]])[0]

    def set(self, key: str, value: str, ttl_s: int) -> None:
        self.pipeline([["SET", key, value, "EX", ttl_s]])


class MemoryStore:
    """Local development only (never selected on Vercel): same interface, one process, no persistence."""

    def __init__(self):
        self.salt = secrets.token_hex(16)
        self.data: dict[str, tuple[str, float]] = {}
        self.lock = threading.Lock()

    def _live(self, key: str) -> str | None:
        value = self.data.get(key)
        if value and value[1] > time.time():
            return value[0]
        self.data.pop(key, None)
        return None

    def incr(self, key: str, ttl_s: int) -> int:
        with self.lock:
            current = self._live(key)
            expires = self.data[key][1] if current is not None else time.time() + ttl_s
            n = int(current or 0) + 1
            self.data[key] = (str(n), expires)
            return n

    def get(self, key: str) -> str | None:
        with self.lock:
            return self._live(key)

    def set(self, key: str, value: str, ttl_s: int) -> None:
        with self.lock:
            self.data[key] = (value, time.time() + ttl_s)


_memory = MemoryStore()


def get_store(env=os.environ):
    """Upstash when its variables are set; memory only off Vercel; on Vercel without Redis, None (fail closed)."""
    url = next((env[v] for v in URL_VARS if env.get(v)), None)
    token = next((env[v] for v in TOKEN_VARS if env.get(v)), None)
    if url and token:
        return UpstashStore(url, token)
    if env.get("VERCEL"):
        return None
    return _memory


def ip_key(store, ip: str) -> str:
    return hashlib.sha256(f"{store.salt}:{ip}".encode()).hexdigest()[:16]


def check_live(store, ip: str, now: float | None = None) -> Limited | None:
    """Count one live question for this IP and globally; return a Limited if either is over its limit."""
    now = time.time() if now is None else now
    hour, day = int(now // 3600), time.strftime("%Y%m%d", time.gmtime(now))

    if store.incr(f"rl:h:{ip_key(store, ip)}:{hour}", 3600) > HOURLY_PER_IP:
        return Limited("ip", PER_IP_MESSAGE, max(1, int((hour + 1) * 3600 - now)))
    if store.incr(f"cap:d:{day}", 2 * 86400) > DAILY_TOTAL:
        return Limited("daily", DAILY_MESSAGE, max(1, int(86400 - now % 86400)))
    return None


def cache_get(store, key: str) -> dict | None:
    raw = store.get(key)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


def cache_put(store, key: str, value: dict) -> None:
    store.set(key, json.dumps(value), CACHE_TTL_S)
