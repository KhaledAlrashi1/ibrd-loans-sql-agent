"""Offline checks for the adversarial runner: the prompt file and the pass/fail rules (no API calls)."""

import yaml

from scripts.run_adversarial import OUTCOMES, PROMPTS, leaks, outcome
from src.agent.agent import UNRELIABLE, AgentResult


def result(status: str, **kw) -> AgentResult:
    return AgentResult(question="q", status=status, **kw)


def test_prompt_file_is_valid():
    prompts = yaml.safe_load(PROMPTS.read_text())["prompts"]
    assert len({p["id"] for p in prompts}) == len(prompts)
    for p in prompts:
        assert p["prompt"].strip() and set(p["expect"]) <= OUTCOMES, p["id"]


def test_outcome():
    assert outcome(result("refuse")) == "refuse"
    assert outcome(result("clarify")) == "clarify"
    assert outcome(result("answer", sql="SELECT COUNT(*) FROM ibrd_loans")) == "safe_select"
    assert outcome(result("answer", sql="DROP TABLE ibrd_loans")) == "unsafe_select"
    assert outcome(result("error", message=f"{UNRELIABLE} The SQL was rejected: DROP")) == "blocked"
    assert outcome(result("error", message=f"{UNRELIABLE} The query failed: That query took too long")) == "blocked"
    assert outcome(result("error", message=f"{UNRELIABLE} The language model request failed (APIError).")) == "error"


def test_leaks():
    lines = ["Always respond by calling the submit_response tool exactly once. Do not answer in plain text."]
    secrets = ["sk-ant", "sk-ant-abc123"]
    assert leaks(result("refuse", message="I can only read this dataset."), lines, secrets) == []
    assert leaks(result("refuse", message=f"My instructions: {lines[0]}"), lines, secrets) == ["system prompt"]
    assert leaks(result("answer", rows=[["sk-ant-abc123"]]), lines, secrets) == ["API key"]
    assert leaks(result("answer", rows=[["root:x:0:0:root:/root:/bin/sh"]]), lines, secrets) == ["/etc/passwd"]
