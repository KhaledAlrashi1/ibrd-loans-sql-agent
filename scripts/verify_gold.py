"""Recompute every gold answer in eval/questions.yaml with pandas, straight from the raw CSV.

Independent of the DuckDB build: raw column names, its own parsing, no import of build_db.py.
Compares against gold_result using the tolerances in the file (comparison logic: src/agent/scoring.py)
and reports disagreements.
It never edits questions.yaml.

    python scripts/verify_gold.py [--split dev|heldout|all]
"""

import argparse
import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.agent.scoring import plain, rows_match  # noqa: E402

RAW_CSV = ROOT / "data" / "raw" / "ibrd_snapshot_2026-09-30.csv"
QUESTIONS = ROOT / "eval" / "questions.yaml"

DATE_COLUMNS = [
    "End of Period", "First Repayment Date", "Last Repayment Date", "Agreement Signing Date",
    "Board Approval Date", "Effective Date (Most Recent)", "Closed Date (Most Recent)", "Last Disbursement Date",
]
NUMBER_COLUMNS = [
    "Interest Rate", "Original Principal Amount (US$)", "Cancelled Amount (US$)", "Undisbursed Amount (US$)",
    "Disbursed Amount (US$)", "Repaid to IBRD (US$)", "Due to IBRD (US$)", "Exchange Adjustment (US$)",
    "Borrower's Obligation (US$)", "Sold 3rd Party (US$)", "Repaid 3rd Party (US$)", "Due 3rd Party (US$)",
    "Loans Held (US$)", "Board approval - Fiscal year", "Board approval - Calendar year",
]

ORIGINAL = "Original Principal Amount (US$)"
UNDISBURSED = "Undisbursed Amount (US$)"
CANCELLED = "Cancelled Amount (US$)"
OBLIGATION = "Borrower's Obligation (US$)"
FY = "Board approval - Fiscal year"
COUNTRY = "Country / Economy"


def load_raw() -> pd.DataFrame:
    df = pd.read_csv(RAW_CSV, dtype=str, keep_default_na=False)
    df = df.apply(lambda s: s.str.strip()).replace("", None)
    for col in DATE_COLUMNS:
        df[col] = pd.to_datetime(df[col], format="%m/%d/%Y").dt.date
    for col in NUMBER_COLUMNS:
        df[col] = pd.to_numeric(df[col])
    df["guarantee"] = df["Loan Number"].str.startswith(("IBRDB", "IBRDG"))
    df["regional"] = df["Country / Economy Code"].str.contains(r"\d")
    return df


def top(series: pd.Series, n: int) -> list[list]:
    s = series.sort_values(ascending=False)
    return [[k, float(v)] for k, v in s.head(n).items()]


def answers(df: pd.DataFrame) -> dict:
    """Question id -> (rows, note). Each implements the question's spec, not the gold SQL."""
    loans = df[~df["guarantee"]]
    ranked = loans[~loans["regional"]]

    def country(name):
        return loans[loans[COUNTRY] == name]

    largest = loans[loans[ORIGINAL] == loans[ORIGINAL].max()]
    mexico = country("Mexico")
    return {
        "D01": [[len(loans)]],
        "D02": [[country("Brazil")[ORIGINAL].sum()]],
        "D03": top(ranked.groupby(COUNTRY)[UNDISBURSED].sum(), 10),
        "D04": top(ranked.groupby(COUNTRY)[OBLIGATION].sum(), 5),
        "D05": [[country("Turkiye")[OBLIGATION].sum()]],
        "D06": [[len(country("Korea, Republic of"))]],
        "D07": [[int(fy), float(v)] for fy, v in
                loans[loans[FY].between(2020, 2025)].groupby(FY)[ORIGINAL].sum().sort_index().items()],
        "D08": top(loans.groupby("Region")[UNDISBURSED].sum(), 1),
        "D09": [[loans.loc[loans["Interest Rate"] > 0, "Interest Rate"].mean()]],
        "D10": [[int(df["guarantee"].sum())]],
        "D11": [[country("Morocco")["Project ID"].nunique()]],
        "D12": largest[["Loan Number", COUNTRY, ORIGINAL]].values.tolist(),
        "D13": [[int((loans["Loan Status"] == "Fully Cancelled").sum())]],
        "D14": [[country("Argentina")[CANCELLED].sum()]],
        "D15": [[int((loans[FY] == 2027).sum())]],
        "D16": [[mexico[CANCELLED].sum() / mexico[ORIGINAL].sum()]],
        "D17": [[country("Jordan")["Board Approval Date"].max().isoformat()]],
        "H01": [[len(country("India"))]],
        "H02": top(ranked.groupby(COUNTRY)[ORIGINAL].sum(), 5),
        "H03": [[country("Egypt, Arab Republic of")[OBLIGATION].sum()]],
        "H04": [[loans.loc[loans[FY] == 2023, ORIGINAL].sum()]],
        "H05": [[country("China").query("`Interest Rate` > 0")["Interest Rate"].mean()]],
        "H06": [[country("Indonesia")["Project ID"].nunique()]],
        "H07": top(loans.groupby("Region")[OBLIGATION].sum(), 1),
        "H08": [[int((loans["Loan Status"] == "Fully Repaid").sum())]],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--split", choices=["dev", "heldout", "all"], default="all")
    args = parser.parse_args()

    spec = yaml.safe_load(QUESTIONS.read_text())
    scoring = spec["scoring"]
    mine = answers(load_raw())

    failures = 0
    print(f"{'id':4} {'match':6} gold vs pandas")
    for q in spec["questions"]:
        if q["expected_behavior"] != "answer" or args.split not in ("all", q["split"]):
            continue
        if q["gold_result"] is None:
            print(f"{q['id']:4} {'MISSING':6} no gold_result")
            failures += 1
            continue
        gold_rows = q["gold_result"]["rows"]
        mine_rows = [[plain(v) for v in row] for row in mine[q["id"]]]
        ok = rows_match(gold_rows, mine_rows, q, scoring)
        failures += not ok
        print(f"{q['id']:4} {'ok' if ok else 'DIFF':6} {gold_rows if ok else f'gold={gold_rows}  pandas={mine_rows}'}")

    print(f"\n{'All gold answers match pandas.' if not failures else f'{failures} disagreement(s).'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
