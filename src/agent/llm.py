"""One call to Claude: system prompt (cached) + the conversation so far -> one model turn.

Structured output comes from a single strict tool, submit_response. claude-sonnet-5-5 rejects a forced
tool_choice with a 400, so tool_choice is "auto" and the system prompt requires the call; agent.py
treats a turn without the call as a failure. Temperature is not sent: the API version this SDK uses
rejects it on every model.
"""

import os
import tomllib
from functools import cache

import anthropic
from anthropic.types import Message, ToolUseBlock

from src.agent import config
from src.agent.prompt import RESPONSE_TOOL, TOOL_NAME, build_system_prompt


def load_api_key() -> str:
    """ANTHROPIC_API_KEY from the environment, else from .streamlit/secrets.toml. Never logged."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key and config.SECRETS_PATH.exists():
        with config.SECRETS_PATH.open("rb") as f:
            key = tomllib.load(f).get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("No Anthropic API key: set ANTHROPIC_API_KEY or add it to .streamlit/secrets.toml.")
    return key


@cache
def get_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=load_api_key())


def call_model(messages: list[dict]) -> Message:
    return get_client().messages.create(
        model=config.MODEL,
        max_tokens=config.MAX_TOKENS,
        system=[{"type": "text", "text": build_system_prompt(), "cache_control": {"type": "ephemeral"}}],
        tools=[RESPONSE_TOOL],
        tool_choice={"type": "auto", "disable_parallel_tool_use": True},
        output_config={"effort": config.EFFORT},
        messages=messages,
    )


def find_tool_call(response: Message) -> ToolUseBlock | None:
    return next((b for b in response.content if b.type == "tool_use" and b.name == TOOL_NAME), None)
