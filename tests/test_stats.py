"""web/src/data/stats.json (scripts/build_stats.py, DuckDB) recomputed independently with pandas from the raw CSV."""

import json

import pytest

from scripts.verify_gold import COUNTRY, FY, OBLIGATION, ORIGINAL, load_raw
from src.agent import config

STATS = config.ROOT / "web" / "src" / "data" / "stats.json"
USD = pytest.approx  # sums of the same values in another order: allow float noise only
CENT = 0.01


@pytest.fixture(scope="module")
def stats() -> dict:
    return json.loads(STATS.read_text())


@pytest.fixture(scope="module")
def loans():
    df = load_raw()
    return df[~df["guarantee"]]


def test_snapshot_and_loan_count(stats, loans):
    assert stats["end_of_period"] == "2026-09-30"
    assert stats["loans"] == len(loans) == 9425  # 9,538 rows minus 113 guarantees (data_dictionary.yaml)


def test_outstanding_is_borrowers_obligation_on_loans(stats, loans):
    assert stats["outstanding_usd"] == USD(loans[OBLIGATION].sum(), abs=CENT)


def test_approved_is_original_principal_on_loans_since_first_fy(stats, loans):
    assert stats["approved_usd"] == USD(loans[ORIGINAL].sum(), abs=CENT)
    assert stats["first_fy"] == loans[FY].min() == 1947


def test_countries_exclude_regional_entries(stats, loans):
    assert stats["countries"] == loans.loc[~loans["regional"], COUNTRY].nunique()


def test_outstanding_by_region(stats, loans):
    expected = loans.groupby("Region")[OBLIGATION].sum().sort_values(ascending=False)
    got = stats["outstanding_by_region"]
    assert [r["region"] for r in got] == list(expected.index)
    for r in got:
        assert r["usd"] == USD(expected[r["region"]], abs=CENT)
    assert sum(r["usd"] for r in got) == USD(stats["outstanding_usd"], abs=CENT)
