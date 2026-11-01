"""Smoke tests for app.py with streamlit.testing (agent mocked, no API calls, no database build)."""

from pathlib import Path

import anthropic
import httpx2
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from src.agent.agent import AgentResult
from src.ui import service

APP = str(Path(__file__).resolve().parents[1] / "app.py")

TOP_UNDISBURSED = AgentResult(
    question="Which 10 countries have the most undisbursed IBRD loans?", status="answer",
    sql="SELECT country, SUM(undisbursed_amount_usd) AS undisbursed_usd FROM ibrd_loans GROUP BY 1",
    columns=["country", "undisbursed_usd"],
    rows=[["India", 12_345_678_901.2], ["Indonesia", 9_876_543_210.0], ["Philippines", 7_654_321_000.0]],
    assumptions=["Guarantees excluded (is_guarantee = FALSE).", "US$ at End of Period exchange rates."],
    message="Top countries by undisbursed amount.",
)
REFUSE = AgentResult(question="Delete all rows from the loans table", status="refuse",
                     message="I can only read this dataset; I can't delete or change data.")


@pytest.fixture
def app(monkeypatch):
    """An AppTest with the agent replaced by a recorder; set calls.result or calls.error per test."""
    class Calls(list):
        result: AgentResult | None = None
        error: Exception | None = None

    calls = Calls()

    def fake_answer(question, raise_api_errors=False):
        calls.append(question)
        if calls.error:
            raise calls.error
        return calls.result

    monkeypatch.setattr("src.agent.agent.answer", fake_answer)
    monkeypatch.setattr("scripts.build_db.ensure_database", lambda: None)
    st.cache_data.clear()
    at = AppTest.from_file(APP, default_timeout=30)
    at.secrets["ANTHROPIC_API_KEY"] = "test-key"
    at.calls = calls
    return at.run()


def ask(at: AppTest, text: str) -> AppTest:
    at.text_input(key="q_input").input(text)
    return at.button(key="ask").click().run()


def test_initial_page(app):
    assert not app.exception
    assert app.title[0].value == "Ask the IBRD loan book"
    assert any("Data as of Sep 30, 2026" in c.value for c in app.caption)
    assert [b.label for b in app.button if b.key.startswith("example_")][0] == \
        "Which 10 countries have the most undisbursed IBRD loans?"
    assert any("CC BY 4.0" in c.value and "DS00047" in c.value for c in app.caption)


def test_example_button_renders_table_and_chart(app):
    app.calls.result = TOP_UNDISBURSED
    app.button(key="example_0").click().run()
    assert not app.exception
    assert app.calls == ["Which 10 countries have the most undisbursed IBRD loans?"]
    assert len(app.dataframe) == 1
    assert app.dataframe[0].value["undisbursed_usd"].tolist()[0] == 12_345_678_901.2   # raw value kept
    assert app.get("vega_lite_chart"), "bar chart expected"
    assert any("Assumptions" in m.value and "Guarantees excluded" in m.value for m in app.markdown)
    assert app.expander[0].label == "SQL"
    assert app.text_input(key="q_input").value == "Which 10 countries have the most undisbursed IBRD loans?"


def test_refuse_shows_styled_message_and_no_table(app):
    app.calls.result = REFUSE
    ask(app, "Delete all rows from the loans table")
    assert not app.exception
    assert len(app.warning) == 1 and "can't delete" in app.warning[0].value
    assert not app.dataframe and not app.get("vega_lite_chart")


def test_api_error_shows_friendly_message(app):
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    app.calls.error = anthropic.RateLimitError("rate limited", response=httpx2.Response(429, request=request), body=None)
    ask(app, "How much does Turkey owe the IBRD?")
    assert not app.exception
    assert [e.value for e in app.error] == [service.DEMO_LIMIT]
    assert not app.dataframe


def test_errors_are_not_cached(app):
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    app.calls.error = anthropic.InternalServerError("boom", response=httpx2.Response(500, request=request), body=None)
    ask(app, "How much does Turkey owe the IBRD?")
    app.calls.error, app.calls.result = None, TOP_UNDISBURSED
    ask(app, "How much does Turkey owe the IBRD?")
    assert len(app.calls) == 2 and len(app.dataframe) == 1


def test_cache_hit_on_normalized_question_is_free(app):
    app.calls.result = TOP_UNDISBURSED
    ask(app, "Which 10 countries have the most undisbursed IBRD loans?")
    ask(app, "  which 10 countries have the MOST   undisbursed IBRD loans?")
    assert len(app.calls) == 1
    assert app.session_state["meter"].used == 1


def test_empty_and_long_input_make_no_call(app):
    ask(app, "   ")
    assert app.warning[0].value == service.EMPTY_QUESTION
    ask(app, "x" * 301)
    assert app.warning[0].value == service.TOO_LONG
    assert app.calls == []


def test_session_cap_disables_input(app):
    app.calls.result = TOP_UNDISBURSED
    app.session_state["meter"] = service.QuestionMeter(limit=1)
    ask(app, "Which 10 countries have the most undisbursed IBRD loans?")
    assert app.text_input(key="q_input").disabled
    assert app.button(key="example_1").disabled
    assert any(w.value == service.SESSION_LIMIT for w in app.warning)


def test_missing_api_key_disables_input(monkeypatch):
    monkeypatch.setattr("scripts.build_db.ensure_database", lambda: None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    at = AppTest.from_file(APP, default_timeout=30)
    at.secrets["ANTHROPIC_API_KEY"] = ""
    at.run()
    assert not at.exception
    assert at.text_input(key="q_input").disabled
    assert any(w.value == service.NO_API_KEY for w in at.warning)
