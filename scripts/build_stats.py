"""Headline numbers for the page, computed from the frozen snapshot: web/src/data/stats.json.

    python scripts/build_stats.py

Queries the DuckDB file built from data/raw/ (the same table and derived flags the agent uses). Loans only:
guarantees (is_guarantee) are left out, as in every loan question. tests/test_stats.py recomputes each number
with pandas straight from the raw CSV. Values are raw US$; rounding happens in the page.
"""

import json
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_db import DB_PATH, ensure_database  # noqa: E402

OUT = ROOT / "web" / "src" / "data" / "stats.json"

# Display names for the region values (data_dictionary.yaml, region.allowed_values). The current World Bank
# administrative regions; the Middle East and North Africa region also includes Afghanistan and Pakistan.
REGION_LABELS = {
    "LATIN AMERICA AND CARIBBEAN": "Latin America & Caribbean",
    "EUROPE AND CENTRAL ASIA": "Europe & Central Asia",
    "EAST ASIA AND PACIFIC": "East Asia & Pacific",
    "MID EAST,NORTH AFRICA,AFG,PAK": "Middle East, N. Africa, Afg. & Pak.",
    "SOUTH ASIA": "South Asia",
    "EASTERN AND SOUTHERN AFRICA": "Eastern & Southern Africa",
    "WESTERN AND CENTRAL AFRICA": "Western & Central Africa",
}


def compute(con: duckdb.DuckDBPyConnection) -> dict:
    end_of_period, loans, outstanding, approved, first_fy, countries = con.execute("""
        SELECT max(end_of_period), count(*), sum(borrowers_obligation_usd), sum(original_principal_amount_usd),
               min(board_approval_fy), count(DISTINCT country) FILTER (WHERE NOT is_regional_entry)
        FROM ibrd_loans WHERE NOT is_guarantee
    """).fetchone()
    regions = con.execute("""
        SELECT region, sum(borrowers_obligation_usd) AS usd
        FROM ibrd_loans WHERE NOT is_guarantee
        GROUP BY region ORDER BY usd DESC
    """).fetchall()
    unknown = {r for r, _ in regions} - set(REGION_LABELS)
    if unknown:
        raise SystemExit(f"no display name for region(s): {sorted(unknown)}")
    return {
        "end_of_period": end_of_period.isoformat(),
        "loans": loans,
        "outstanding_usd": outstanding,
        "approved_usd": approved,
        "first_fy": first_fy,
        "countries": countries,
        "outstanding_by_region": [{"region": r, "label": REGION_LABELS[r], "usd": usd} for r, usd in regions],
    }


def main() -> int:
    ensure_database()
    with duckdb.connect(str(DB_PATH), read_only=True) as con:
        stats = compute(con)
    OUT.write_text(json.dumps(stats, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps(stats, indent=1))
    print(f"\nOK: wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
