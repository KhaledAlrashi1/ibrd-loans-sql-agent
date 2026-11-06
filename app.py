"""Streamlit UI only (no business logic): src/ui/ holds the formatting, chart and answer-path rules."""

import logging
import os

import streamlit as st

from scripts.build_db import ensure_database
from src.agent import config
from src.agent.agent import AgentResult
from src.ui import display, service

log = logging.getLogger("ibrd_app")

REPO_URL = "https://github.com/KhaledAlrashi1/ibrd-loans-sql-agent"
LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"
EXAMPLES = [
    "Which 10 countries have the most undisbursed IBRD loans?",
    "Which 5 Middle East and North Africa countries owe the most to the IBRD?",
    "What was the total amount of IBRD loans approved in each fiscal year from 2020 to 2025?",
    "Which loans are active?",
]

st.set_page_config(page_title="IBRD Loans Q&A", page_icon=":material/account_balance:", layout="centered")


@st.cache_resource(show_spinner="Preparing the database (first start only)...")
def database_ready():
    return ensure_database()


@st.cache_data(max_entries=500, show_spinner=False)
def cached_answer(normalized: str, _question: str, _meter: service.QuestionMeter) -> AgentResult:
    """Keyed on the normalized question only. Errors raise, and Streamlit never caches a raise."""
    result = service.ask(_question, _meter)
    if result.status == "error":
        raise service.UncachedResult(result)
    return result


def api_key_configured() -> bool:
    try:
        secret = st.secrets.get("ANTHROPIC_API_KEY")
    except Exception:  # no secrets file at all
        secret = None
    key = service.resolve_api_key(secret, os.environ.get("ANTHROPIC_API_KEY"))
    if key:
        os.environ["ANTHROPIC_API_KEY"] = key  # where src/agent/llm.py looks first
    return bool(key)


def queue(question: str) -> None:
    st.session_state.q_input = question
    st.session_state.pending = question


def submit() -> None:
    st.session_state.pending = st.session_state.q_input


def run_question(question: str) -> None:
    """Store what to show in st.session_state.view: ("result", AgentResult) or ("notice", level, text)."""
    ss = st.session_state
    problem = service.validate_question(question)
    if problem:
        ss.view = ("notice", "warning", problem)
        return
    if ss.meter.reached:
        ss.view = ("notice", "warning", service.SESSION_LIMIT)
        return
    try:
        with st.spinner("Writing and checking the SQL..."):
            result = cached_answer(service.normalize_question(question), question.strip(), ss.meter)
        ss.view = ("result", result)
    except service.UncachedResult as e:
        ss.view = ("result", e.result)
    except Exception as e:
        log.exception("answer failed: %s", type(e).__name__)
        ss.view = ("notice", "error", service.friendly_error(e))


def show_notice(level: str, text: str) -> None:
    {"info": st.info, "warning": st.warning, "error": st.error}[level](display.md_text(text))


def show_result(r: AgentResult) -> None:
    if r.status == "clarify":
        st.info(display.md_text(r.message), title="I need a bit more detail", icon=":material/help:")
    elif r.status == "refuse":
        st.warning(display.md_text(r.message), title="I can't answer that", icon=":material/block:")
    elif r.status == "error":
        st.error(display.md_text(r.message), icon=":material/error:")
    elif not r.rows:
        st.info(display.md_text(r.message), icon=":material/search_off:")
    else:
        st.markdown(f"**{display.md_text(r.message)}**")
        st.dataframe(display.styled_table(r.columns, r.rows), hide_index=True)
        spec = display.choose_chart(r.columns, r.rows)
        if spec:
            st.altair_chart(display.build_chart(spec, r.columns, r.rows), width="stretch")

    if r.assumptions:
        st.markdown("**Assumptions**\n" + "\n".join(f"- {display.md_text(a)}" for a in r.assumptions))
    if r.truncated:
        st.caption(f"Showing first {config.ROW_LIMIT:,} rows.")
    if r.sql:
        with st.expander("SQL" if r.status == "answer" else "SQL attempted", expanded=False):
            st.code(r.sql, language="sql")


def main() -> None:
    ss = st.session_state
    ss.setdefault("meter", service.QuestionMeter())
    ss.setdefault("view", None)
    ss.setdefault("pending", None)
    info = service.dataset_info()

    st.title("Ask the IBRD loan book")
    st.write("Ask a question in plain English about World Bank IBRD loans. An AI model writes the SQL, "
             "the app checks it and runs it on the official data, and you see the answer, the SQL and "
             "every assumption behind it.")
    st.caption(f"Data as of {info.end_of_period:%b} {info.end_of_period.day}, {info.end_of_period.year}")

    try:
        database_ready()
        ready, setup_problem = api_key_configured(), service.NO_API_KEY
    except Exception:
        log.exception("database setup failed")
        ready, setup_problem = False, service.DEMO_UNAVAILABLE

    controls = st.container()  # filled after the pending question runs, so "disabled" is current
    if ready and ss.pending is not None:
        question, ss.pending = ss.pending, None
        run_question(question)

    with controls:
        disabled = not ready or ss.meter.reached
        st.markdown("**Try an example**")
        left, right = st.columns(2)
        for i, example in enumerate(EXAMPLES):
            (left if i % 2 == 0 else right).button(example, key=f"example_{i}", on_click=queue, args=(example,),
                                                   disabled=disabled, width="stretch")
        with st.form("ask", border=False):
            st.text_input("Your question", key="q_input", disabled=disabled,
                          placeholder="e.g. How much does Chile owe the IBRD?")
            st.form_submit_button("Ask", key="ask", type="primary", on_click=submit, disabled=disabled)
        if not ready:
            st.warning(setup_problem)
        elif ss.meter.reached:
            st.warning(service.SESSION_LIMIT)

    if ss.view is not None:
        try:
            if ss.view[0] == "result":
                show_result(ss.view[1])
            else:
                show_notice(*ss.view[1:])
        except Exception:
            log.exception("rendering failed")
            st.error(service.GENERIC_ERROR)

    st.divider()
    st.caption(
        f"Source: [World Bank, IBRD Statement of Loans and Guarantees ({info.id})]({info.source_url}), "
        f"[CC BY 4.0]({LICENSE_URL}). Snapshot of {info.end_of_period:%Y-%m-%d}; columns renamed and two "
        f"derived flags added. · [Code on GitHub]({REPO_URL})"
    )


try:
    main()
except Exception:  # last resort: never show a traceback
    log.exception("app failed")
    st.error(service.GENERIC_ERROR)
