"""The app's answer path without Streamlit: input checks, cache key, per-session cap, friendly errors.

    problem = validate_question(text)          # None, or a message to show instead of calling the API
    result = ask(text, meter)                   # counts one API-backed question, then calls the agent
    message = friendly_error(exc)               # what the user sees for any exception from ask()
"""

from dataclasses import dataclass
from datetime import date
from functools import cache
from pathlib import Path

import anthropic
import yaml

from src.agent import agent, config
from src.agent.agent import AgentResult

MAX_QUESTION_CHARS = 300
SESSION_QUESTION_CAP = 15

EMPTY_QUESTION = "Please type a question about IBRD loans."
TOO_LONG = f"Please keep your question under {MAX_QUESTION_CHARS} characters."
SESSION_LIMIT = "Demo limit reached for this session."
DEMO_UNAVAILABLE = "Demo is temporarily unavailable."
DEMO_LIMIT = "Demo limit reached, please try again later."
GENERIC_ERROR = "Something went wrong while answering. Please try again in a moment."
NO_API_KEY = "Demo is temporarily unavailable: no API key is configured."

LIMIT_ERROR_TYPES = {"billing_error", "rate_limit_error", "overloaded_error"}
AUTH_ERROR_TYPES = {"authentication_error", "permission_error"}


def normalize_question(text: str) -> str:
    """Cache key: strip, lowercase, collapse whitespace."""
    return " ".join(text.split()).lower()


def validate_question(text: str | None) -> str | None:
    text = (text or "").strip()
    if not text:
        return EMPTY_QUESTION
    if len(text) > MAX_QUESTION_CHARS:
        return TOO_LONG
    return None


@dataclass
class QuestionMeter:
    """Questions in this session that reached the API (cache hits never get here)."""
    limit: int = SESSION_QUESTION_CAP
    used: int = 0

    @property
    def reached(self) -> bool:
        return self.used >= self.limit

    def record(self) -> None:
        self.used += 1


class UncachedResult(Exception):
    """Carries an agent result that must be shown but not cached (status "error")."""

    def __init__(self, result: AgentResult):
        super().__init__(result.message)
        self.result = result


def ask(question: str, meter: QuestionMeter) -> AgentResult:
    """Count the question against the session cap, then run the agent. API errors propagate."""
    meter.record()
    return agent.answer(question, raise_api_errors=True)


def friendly_error(exc: BaseException) -> str:
    if isinstance(exc, (anthropic.AuthenticationError, anthropic.PermissionDeniedError)):
        return DEMO_UNAVAILABLE
    if isinstance(exc, (anthropic.RateLimitError, anthropic.OverloadedError)):
        return DEMO_LIMIT
    if isinstance(exc, anthropic.APIStatusError):
        # A spend limit is a 402 billing_error, which has no SDK class of its own.
        if exc.type in LIMIT_ERROR_TYPES or exc.status_code in (402, 429, 529):
            return DEMO_LIMIT
        if exc.type in AUTH_ERROR_TYPES:
            return DEMO_UNAVAILABLE
        if isinstance(exc, anthropic.BadRequestError) and "credit balance" in str(exc).lower():
            return DEMO_LIMIT
    return GENERIC_ERROR


def resolve_api_key(secret: str | None, env: str | None) -> str | None:
    """st.secrets first, then the environment variable."""
    return secret or env or None


@dataclass(frozen=True)
class DatasetInfo:
    name: str
    id: str
    source_url: str
    end_of_period: date


@cache
def dataset_info(dictionary_path: Path = config.DICTIONARY_PATH) -> DatasetInfo:
    ds = yaml.safe_load(Path(dictionary_path).read_text())["dataset"]
    return DatasetInfo(ds["name"], ds["id"], ds["source_url"], date.fromisoformat(ds["end_of_period"]))
