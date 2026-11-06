"""Plain-English column labels: the dictionary rule, the alias rule, and every alias the agent has produced."""

import json
from pathlib import Path

import pytest

from src.agent import config

from server.labels import column_label

RESULTS = sorted((config.ROOT / "eval" / "results").glob("*_dev.json"))


@pytest.mark.parametrize("name, label", [
    ("borrowers_obligation_usd", "Borrower's obligation (USD)"),
    ("board_approval_fy", "Board approval fiscal year"),
    ("board_approval_cy", "Board approval calendar year"),
    ("repaid_to_ibrd_usd", "Repaid to IBRD (USD)"),
    ("project_id", "Project ID"),
    ("closed_date_most_recent", "Closed date (most recent)"),
    ("country", "Country / economy"),
    ("total_owed_usd", "Total owed (USD)"),
    ("loan_count", "Loan count"),
    ("cancelled_share", "Cancelled (%)"),
    ("avg_interest_rate", "Average interest rate"),
    ("fy", "Fiscal year"),
    ("LOAN_COUNT", "Loan count"),
    ("loan_count (2)", "Loan count (2)"),
])
def test_rules(name, label):
    assert column_label(name) == label


def saved_aliases() -> set[str]:
    names = set()
    for path in RESULTS:
        for r in json.loads(Path(path).read_text())["results"]:
            names.update((r.get("result") or {}).get("columns") or [])
    return names


def test_every_saved_dev_alias_gets_a_readable_label():
    names = saved_aliases()
    assert len(names) >= 20
    for name in names:
        label = column_label(name)
        assert "_" not in label and label[0].isupper(), (name, label)
        if name.endswith("_usd"):
            assert label.endswith("(USD)"), (name, label)
