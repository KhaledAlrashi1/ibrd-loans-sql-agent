"""Unit tests for src/ui (no API calls): formatting, chart choice, normalization, error mapping, session cap."""

import datetime

import anthropic
import httpx2
import pytest

from src.agent.agent import AgentResult
from src.ui import display, service
from src.ui.display import ChartSpec, choose_chart, column_unit, format_value

# --- number formatting -------------------------------------------------------------------------------

@pytest.mark.parametrize("value, expected", [
    (1_234_567_890, "$1.23B"),
    (25_834_171_033.09, "$25.83B"),
    (1_234_567_890_123, "$1,234.57B"),
    (456_700_000, "$456.7M"),
    (12_340, "$12.3K"),
    (512.4, "$512.40"),
    (999_960, "$1.0M"),          # rounds up into the next unit, never "$1000.0K"
    (999_999_999, "$1.00B"),
    (-23_218_035.77, "-$23.2M"),
    (-0.01, "-$0.01"),
    (-0.004, "$0.00"),
    (0, "$0.00"),
])
def test_format_usd(value, expected):
    assert format_value(value, display.USD) == expected


@pytest.mark.parametrize("value, expected", [
    (0.1234, "12.3%"), (1.0, "100.0%"), (0, "0.0%"), (0.0004, "<0.1%"), (0.0005, "0.1%"),
])
def test_format_share(value, expected):
    assert format_value(value, display.SHARE) == expected


@pytest.mark.parametrize("value, unit, expected", [
    (5.880697376568286, display.PLAIN, "5.880697376568286"),  # other numbers as stored
    (2020, display.PLAIN, "2020"),                            # no thousands separator on years
    (9425, display.PLAIN, "9425"),
    (None, display.USD, ""),
    (float("nan"), display.USD, ""),
    ("India", display.USD, "India"),                          # non-numbers are never unit-formatted
    (True, display.USD, "True"),
    (datetime.date(2026, 9, 30), display.PLAIN, "2026-09-30"),
])
def test_format_other(value, unit, expected):
    assert format_value(value, unit) == expected


@pytest.mark.parametrize("name, expected", [
    ("borrowers_obligation_usd", display.USD),     # dictionary: original name has (US$)
    ("undisbursed_amount_usd", display.USD),
    ("interest_rate", display.PLAIN),              # dictionary: units undocumented
    ("board_approval_fy", display.PLAIN),
    ("total_owed_usd", display.USD),               # computed alias convention
    ("Owed_USD", display.USD),
    ("cancelled_share", display.SHARE),
    ("loan_count", display.PLAIN),
    ("usd_total", display.PLAIN),                  # suffix only
])
def test_column_unit(name, expected):
    assert column_unit(name) == expected


def test_explicit_units_win():
    assert column_unit("cancelled_share", {"cancelled_share": display.PLAIN}) == display.PLAIN


def test_styled_table_keeps_raw_values():
    cols, rows = ["country", "owed_usd", "cancelled_share", "first_fy"], [["India", 23_573_624_318.85, 0.05, 1949],
                                                                       ["Chile", 1_000.0, None, None]]
    styler = display.styled_table(cols, rows)
    assert styler.data["owed_usd"].tolist() == [23_573_624_318.85, 1_000.0]
    assert str(styler.data["first_fy"].dtype) == "Int64"     # NULL does not turn years into floats
    html = styler.to_html()
    assert "$23.57B" in html and "5.0%" in html and "1949" in html and "1949.0" not in html


def test_duplicate_column_names_are_numbered():
    assert display.unique_names(["n", "n", "x", "n"]) == ["n", "n (2)", "x", "n (3)"]


# --- chart choice --------------------------------------------------------------------------------------

def test_bar_for_category_and_number():
    rows = [["India", 2.0], ["Indonesia", 1.5], ["Ukraine", 1.0]]
    assert choose_chart(["country", "owed_usd"], rows) == ChartSpec("bar", "country", "owed_usd")


def test_bar_either_column_order():
    assert choose_chart(["n", "region"], [[3, "A"], [2, "B"]]) == ChartSpec("bar", "region", "n")


@pytest.mark.parametrize("n_rows, chart", [(1, None), (2, "bar"), (25, "bar"), (26, None)])
def test_bar_row_limits(n_rows, chart):
    spec = choose_chart(["country", "x_usd"], [[f"c{i}", float(i)] for i in range(n_rows)])
    assert (spec.kind if spec else None) == chart


def test_line_for_fiscal_year_series():
    rows = [[2020, 2.6e10], [2021, 2.9e10], [2022, 3.2e10]]
    assert choose_chart(["fiscal_year", "total_approved_usd"], rows) == ChartSpec("line", "fiscal_year", "total_approved_usd")
    assert choose_chart(["board_approval_fy", "loans"], rows).kind == "line"
    assert choose_chart(["fy", "loans"], [[y, 1] for y in range(1947, 2028)]).kind == "line"  # no 25-row cap


@pytest.mark.parametrize("columns, rows", [
    (["loan_count"], [[9425]]),                                          # one column
    (["country", "owed_usd", "n"], [["A", 1.0, 1], ["B", 2.0, 2]]),      # three columns
    (["country", "owed_usd"], [["A", 1.0], ["A", 2.0]]),                 # repeated labels
    (["country", "owed_usd"], [["A", 1.0], ["B", None]]),                # missing value
    (["country", "is_guarantee"], [["A", True], ["B", False]]),          # bool is not a measure
    (["country", "first_fy"], [["A", 1950], ["B", 1960]]),               # years are not a measure
    (["board_approval_date", "x_usd"], [[datetime.date(2020, 1, 1), 1.0], [datetime.date(2021, 1, 1), 2.0]]),
    (["fiscal_year", "x_usd"], [[2020, 1.0]]),                           # one point
    (["fiscal_year", "x_usd"], [[2020, 1.0], [2020, 2.0]]),              # repeated years
    (["country", "country"], [["A", "B"], ["C", "D"]]),
    (["country", "owed_usd"], []),
])
def test_no_chart(columns, rows):
    assert choose_chart(columns, rows) is None


def test_build_chart_runs_for_both_kinds():
    bar = display.build_chart(ChartSpec("bar", "country", "owed_usd"), ["country", "owed_usd"], [["A", 1e9], ["B", 2e9]])
    assert bar.to_dict()["mark"]["type"] == "bar"
    line = display.build_chart(ChartSpec("line", "fiscal_year", "n"), ["fiscal_year", "n"], [[2020, 1], [2021, 2]])
    assert line.to_dict()["mark"]["type"] == "line"


def test_md_text_escapes_dollar():
    assert display.md_text("US$ at historical rates; US$ again") == "US\\$ at historical rates; US\\$ again"


# --- question normalization and validation -----------------------------------------------------------

@pytest.mark.parametrize("raw", ["How much does Turkey owe?", "  how much  does\tTURKEY owe?\n", "HOW MUCH DOES TURKEY OWE?"])
def test_normalize_question(raw):
    assert service.normalize_question(raw) == "how much does turkey owe?"


@pytest.mark.parametrize("text, expected", [
    ("", service.EMPTY_QUESTION),
    ("   \n", service.EMPTY_QUESTION),
    (None, service.EMPTY_QUESTION),
    ("x" * 301, service.TOO_LONG),
    ("x" * 300, None),
    ("  " + "x" * 300 + "  ", None),   # surrounding whitespace does not count
    ("How much does Turkey owe?", None),
])
def test_validate_question(text, expected):
    assert service.validate_question(text) == expected


# --- error mapping -------------------------------------------------------------------------------------

def status_error(cls, status: int, error_type: str | None = None, message: str = "boom"):
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    body = {"type": "error", "error": {"type": error_type, "message": message}} if error_type else None
    return cls(message, response=httpx2.Response(status, request=request), body=body)


@pytest.mark.parametrize("exc, expected", [
    (status_error(anthropic.AuthenticationError, 401, "authentication_error"), service.DEMO_UNAVAILABLE),
    (status_error(anthropic.PermissionDeniedError, 403, "permission_error"), service.DEMO_UNAVAILABLE),
    (status_error(anthropic.RateLimitError, 429, "rate_limit_error"), service.DEMO_LIMIT),
    (status_error(anthropic.OverloadedError, 529, "overloaded_error"), service.DEMO_LIMIT),
    (status_error(anthropic.APIStatusError, 402, "billing_error"), service.DEMO_LIMIT),
    (status_error(anthropic.APIStatusError, 402), service.DEMO_LIMIT),
    (status_error(anthropic.BadRequestError, 400, "invalid_request_error",
                  "Your credit balance is too low to access the Anthropic API."), service.DEMO_LIMIT),
    (status_error(anthropic.BadRequestError, 400, "invalid_request_error"), service.GENERIC_ERROR),
    (status_error(anthropic.InternalServerError, 500, "api_error"), service.GENERIC_ERROR),
    (anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com")), service.GENERIC_ERROR),
    (RuntimeError("No Anthropic API key"), service.GENERIC_ERROR),
    (ValueError("anything"), service.GENERIC_ERROR),
])
def test_friendly_error(exc, expected):
    assert service.friendly_error(exc) == expected


def test_resolve_api_key_prefers_secrets():
    assert service.resolve_api_key("from-secrets", "from-env") == "from-secrets"
    assert service.resolve_api_key(None, "from-env") == "from-env"
    assert service.resolve_api_key("", "") is None


# --- session cap ----------------------------------------------------------------------------------------

def test_session_cap(monkeypatch):
    calls = []
    monkeypatch.setattr(service.agent, "answer",
                        lambda q, raise_api_errors: calls.append(raise_api_errors) or AgentResult(q, "answer"))
    meter = service.QuestionMeter()
    for _ in range(service.SESSION_QUESTION_CAP - 1):
        service.ask("q", meter)
    assert not meter.reached
    service.ask("q", meter)
    assert meter.reached and meter.used == 15
    assert calls == [True] * 15   # the app always asks for API errors to be raised


def test_session_cap_counts_failed_calls(monkeypatch):
    def fail(q, raise_api_errors):
        raise status_error(anthropic.RateLimitError, 429, "rate_limit_error")
    monkeypatch.setattr(service.agent, "answer", fail)
    meter = service.QuestionMeter(limit=2)
    for _ in range(2):
        with pytest.raises(anthropic.RateLimitError):
            service.ask("q", meter)
    assert meter.reached


def test_dataset_info():
    info = service.dataset_info()
    assert info.id == "DS00047" and info.end_of_period == datetime.date(2026, 9, 30)
