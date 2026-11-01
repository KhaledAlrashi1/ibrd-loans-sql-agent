"""Report-only profile of the built database, config.DB_PATH (prefixes, interest rates, categories, identities, quirks).

    python scripts/profile_data.py [--countries-csv PATH]
"""
import argparse
import sys
from pathlib import Path

import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agent.config import DB_PATH  # noqa: E402

pd.set_option("display.width", 250)
pd.set_option("display.max_columns", None)
pd.set_option("display.max_rows", 300)

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("--countries-csv", type=Path, help="also save the full country list to this CSV")
args = parser.parse_args()

con = duckdb.connect(str(DB_PATH), read_only=True)
show = lambda title, sql: print(f"\n=== {title}\n" + con.sql(sql).df().to_string(index=False))

con.execute("""
CREATE TEMP VIEW v AS SELECT *,
  CASE WHEN regexp_matches(loan_number, '^IBRD[0-9]') THEN 'IBRD+digit'
       ELSE substr(loan_number, 1, 5) END AS prefix
FROM ibrd_loans
""")
show("prefix counts", "SELECT prefix, count(*) n FROM v GROUP BY 1 ORDER BY 2 DESC")
show("loan_number shapes", "SELECT length(loan_number) len, regexp_replace(loan_number, '[0-9]', '9', 'g') shape, count(*) n FROM v GROUP BY ALL ORDER BY n DESC LIMIT 25")
show("prefix x loan_type", "PIVOT v ON loan_type USING count(*) GROUP BY prefix ORDER BY prefix")
show("prefix x loan_status", "PIVOT v ON loan_status USING count(*) GROUP BY prefix ORDER BY prefix")
show("IBRDK / IBRDS rows (sample)", "SELECT loan_number, loan_type, loan_status, country, borrower, project_name, original_principal_amount_usd FROM v WHERE prefix IN ('IBRDK','IBRDS') ORDER BY loan_number LIMIT 12")
show("guarantee rows: money profile", """
SELECT prefix, loan_type, count(*) n, sum(original_principal_amount_usd)/1e6 orig_musd, sum(disbursed_amount_usd)/1e6 disb_musd,
       sum(due_to_ibrd_usd)/1e6 due_musd, sum(loans_held_usd)/1e6 held_musd
FROM v WHERE prefix IN ('IBRDB','IBRDG') OR loan_type IN ('GURB','GUBF','BLNR','BLNC') GROUP BY ALL ORDER BY ALL""")

show("interest_rate = 0.0 by loan_type", """
SELECT loan_type, count(*) n, count(*) FILTER (WHERE interest_rate = 0) zero, count(*) FILTER (WHERE interest_rate IS NULL) nulls,
       round(100.0 * count(*) FILTER (WHERE interest_rate = 0) / count(*), 1) pct_zero
FROM v GROUP BY 1 ORDER BY n DESC""")
show("non-zero interest_rate", """
SELECT count(*) n, min(interest_rate) min, median(interest_rate) median, max(interest_rate) max
FROM v WHERE interest_rate <> 0""")
show("non-zero interest_rate by loan_type", """
SELECT loan_type, count(*) n, min(interest_rate) min, median(interest_rate) median, max(interest_rate) max
FROM v WHERE interest_rate <> 0 GROUP BY 1 ORDER BY n DESC""")
show("interest_rate=0 by loan_status (FSL/SCL vs other)", """
SELECT loan_type IN ('FSL','SCL') AS fsl_or_scl, loan_status, count(*) n FROM v WHERE interest_rate = 0 GROUP BY ALL ORDER BY ALL""")

for col in ["loan_status", "loan_type", "region"]:
    show(f"distinct {col} (exact, quoted)", f"SELECT '[' || {col} || ']' AS value, count(*) n FROM v GROUP BY {col} ORDER BY n DESC")

countries = con.sql("SELECT country, country_code, region, is_regional_entry, count(*) n FROM v GROUP BY ALL ORDER BY country, region").df()
print(f"\ncountry values: {countries['country'].nunique()} ({(~countries['is_regional_entry']).sum()} countries + "
      f"{countries['is_regional_entry'].sum()} regional entries), {len(countries)} country x code x region combos")
if args.countries_csv:
    countries.to_csv(args.countries_csv, index=False)
    print(f"country list -> {args.countries_csv}")
show("is_regional_entry rows", "SELECT country_code, country, region, count(*) n, min(board_approval_fy) fy_min, max(board_approval_fy) fy_max FROM v WHERE is_regional_entry GROUP BY ALL ORDER BY 1")
show("countries with >1 code or region", """
SELECT country, list(DISTINCT country_code) codes, list(DISTINCT region) regions FROM v GROUP BY 1
HAVING count(DISTINCT country_code) > 1 OR count(DISTINCT region) > 1""")
show("codes with >1 country name", "SELECT country_code, list(DISTINCT country) names FROM v GROUP BY 1 HAVING count(DISTINCT country) > 1")
show("World / Other / IFC rows", "SELECT country, country_code, region, count(*) n FROM v WHERE country ILIKE '%world%' OR region ILIKE '%other%' OR borrower ILIKE '%finance corp%' GROUP BY ALL")

# --- extras: official-definition identities and oddities ---
show("NULL counts (non-money cols)", "SELECT " + ", ".join(
    f"count(*) FILTER (WHERE {c} IS NULL) AS {c}" for c in [
        "country_code", "borrower", "guarantor_country_code", "guarantor", "project_id", "project_name",
        "first_repayment_date", "last_repayment_date", "agreement_signing_date", "board_approval_date",
        "effective_date_most_recent", "closed_date_most_recent", "last_disbursement_date"]) + " FROM v")
show("borrowers_obligation = due_to_ibrd + exchange_adjustment (official def) within $1", """
SELECT count(*) FILTER (WHERE abs(borrowers_obligation_usd - (due_to_ibrd_usd + exchange_adjustment_usd)) <= 1) pass,
       count(*) FILTER (WHERE abs(borrowers_obligation_usd - (due_to_ibrd_usd + exchange_adjustment_usd)) > 1) fail FROM v""")
show("loans_held = due_to_ibrd + undisbursed (official def) within $1", """
SELECT count(*) FILTER (WHERE abs(loans_held_usd - (due_to_ibrd_usd + undisbursed_amount_usd)) <= 1) pass,
       count(*) FILTER (WHERE abs(loans_held_usd - (due_to_ibrd_usd + undisbursed_amount_usd)) > 1) fail FROM v""")
show("sold_3rd_party = repaid_3rd_party + due_3rd_party within $1", """
SELECT count(*) FILTER (WHERE abs(sold_3rd_party_usd - (repaid_3rd_party_usd + due_3rd_party_usd)) <= 1) pass,
       count(*) FILTER (WHERE abs(sold_3rd_party_usd - (repaid_3rd_party_usd + due_3rd_party_usd)) > 1) fail FROM v""")
show("principal identity failures by loan_type x status", """
SELECT loan_type, loan_status, count(*) fail FROM v
WHERE abs(original_principal_amount_usd - (cancelled_amount_usd + undisbursed_amount_usd + disbursed_amount_usd)) > 1
GROUP BY ALL ORDER BY fail DESC LIMIT 15""")
show("principal identity pass rate by loan_type", """
SELECT loan_type, count(*) n, count(*) FILTER (WHERE abs(original_principal_amount_usd - (cancelled_amount_usd + undisbursed_amount_usd + disbursed_amount_usd)) > 1) fail
FROM v GROUP BY 1 ORDER BY n DESC""")
show("disbursed identity failures by loan_type x status", """
SELECT loan_type, loan_status, count(*) fail FROM v
WHERE abs(disbursed_amount_usd - (repaid_to_ibrd_usd + due_to_ibrd_usd + sold_3rd_party_usd)) > 1
GROUP BY ALL ORDER BY fail DESC LIMIT 15""")
show("negative due_to_ibrd: worst 8", """
SELECT loan_number, loan_type, loan_status, country, disbursed_amount_usd, repaid_to_ibrd_usd, due_to_ibrd_usd, exchange_adjustment_usd, borrowers_obligation_usd, loans_held_usd
FROM v WHERE due_to_ibrd_usd < 0 ORDER BY due_to_ibrd_usd LIMIT 8""")
show("negative due_to_ibrd by type/status", "SELECT loan_type, loan_status, count(*) n, sum(due_to_ibrd_usd)/1e6 musd FROM v WHERE due_to_ibrd_usd < 0 GROUP BY ALL ORDER BY n DESC")
show("exchange_adjustment non-zero by loan_type", "SELECT loan_type, count(*) n, count(*) FILTER (WHERE exchange_adjustment_usd <> 0) nonzero FROM v GROUP BY 1 ORDER BY n DESC")
show("board_approval_fy vs date check", """
SELECT count(*) FILTER (WHERE board_approval_fy <> year(board_approval_date) + (month(board_approval_date) >= 7)::INT) fy_mismatch,
       count(*) FILTER (WHERE board_approval_cy <> year(board_approval_date)) cy_mismatch,
       min(board_approval_date) min_date, max(board_approval_date) max_date, min(board_approval_fy) min_fy, max(board_approval_fy) max_fy FROM v""")
show("dates after end_of_period", """
SELECT count(*) FILTER (WHERE board_approval_date > end_of_period) approval_future,
       count(*) FILTER (WHERE last_disbursement_date > end_of_period) last_disb_future,
       count(*) FILTER (WHERE closed_date_most_recent > end_of_period) closed_future,
       count(*) FILTER (WHERE agreement_signing_date < board_approval_date) signed_before_approval FROM v""")
show("guarantor null vs country", "SELECT guarantor IS NULL g_null, guarantor_country_code = country_code same_code, count(*) n FROM v GROUP BY ALL ORDER BY ALL")
show("project_id: loans per project (top)", "SELECT max(c) max_loans_per_project, count(*) FILTER (WHERE c > 1) projects_with_multi FROM (SELECT project_id, count(*) c FROM v WHERE project_id IS NOT NULL GROUP BY 1)")
