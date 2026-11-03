"""Build the DuckDB file (one table, ibrd_loans) from the frozen raw CSV, at config.DB_PATH in the temp directory.

The column mapping (original CSV name -> column, type) comes from src/agent/data_dictionary.yaml.
Deletes and rebuilds the database on every run. Stops with a clear error if any
hard check fails; report-only checks are printed and never stop the build.

    python scripts/build_db.py

The app calls ensure_database() to build the file only when it is missing.
"""

import sys
from datetime import date
from pathlib import Path

import duckdb
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.agent import config  # noqa: E402

RAW_CSV = ROOT / "data" / "raw" / "ibrd_snapshot_2026-09-30.csv"
DICTIONARY_PATH = ROOT / "src" / "agent" / "data_dictionary.yaml"
DB_PATH = config.DB_PATH
TABLE = "ibrd_loans"

EXPECTED_ROWS = 9538
EXPECTED_END_OF_PERIOD = date(2026, 9, 30)
EXPECTED_REGIONAL_CODES = {"3E", "3S", "3W", "6R"}
EXPECTED_REGIONAL_ROWS = 25
DATE_FORMAT = "%m/%d/%Y"
TOLERANCE_USD = 1.0

# Derived columns (original_name: null in the dictionary) and the SQL that computes them.
DERIVED = {
    "is_guarantee": "starts_with(loan_number, 'IBRDB') OR starts_with(loan_number, 'IBRDG')",
    "is_regional_entry": "regexp_matches(country_code, '[0-9]')",
}


class CheckFailed(Exception):
    pass


def load_dictionary_columns(path: Path = DICTIONARY_PATH) -> list[dict]:
    """Return the dictionary's column entries, in table order."""
    columns = yaml.safe_load(path.read_text())["columns"]
    derived = [c["column"] for c in columns if c["original_name"] is None]
    if set(derived) != set(DERIVED):
        raise CheckFailed(f"Derived columns in {path.name} {derived} do not match build_db.DERIVED {list(DERIVED)}")
    return columns


def q(name: str) -> str:
    """Quote an identifier for DuckDB."""
    return '"' + name.replace('"', '""') + '"'


def blank_to_null(original: str) -> str:
    return f"NULLIF(TRIM({q(original)}), '')"


def cast_expr(original: str, sql_type: str) -> str:
    value = blank_to_null(original)
    if sql_type == "VARCHAR":
        return value
    if sql_type == "DATE":
        return f"CAST(strptime({value}, '{DATE_FORMAT}') AS DATE)"
    if sql_type in ("DOUBLE", "INTEGER"):
        return f"CAST({value} AS {sql_type})"
    raise ValueError(f"unsupported type {sql_type!r} for {original!r}")


def print_table(con, title: str, sql: str) -> None:
    print(f"\n{title}")
    print(con.sql(sql).df().to_string(index=False))


def load_raw(con, source: list[dict]) -> None:
    con.execute(
        "CREATE TEMP TABLE raw AS SELECT * FROM read_csv(?, header = true, all_varchar = true)",
        [str(RAW_CSV)],
    )
    actual = [row[0] for row in con.execute("DESCRIBE raw").fetchall()]
    expected = [c["original_name"] for c in source]
    if actual != expected:
        raise CheckFailed(f"CSV header does not match the dictionary's original_name list.\n  expected: {expected}\n  actual:   {actual}")


def check_dates_parse(con, source: list[dict]) -> None:
    """Every non-blank date value must parse as MM/DD/YYYY."""
    failures = []
    for c in source:
        if c["type"] != "DATE":
            continue
        value = blank_to_null(c["original_name"])
        bad = con.execute(
            f"SELECT count(*), any_value({value}) FROM raw "
            f"WHERE {value} IS NOT NULL AND try_strptime({value}, '{DATE_FORMAT}') IS NULL"
        ).fetchall()[0]
        if bad[0]:
            failures.append(f"{c['column']}: {bad[0]} unparseable (e.g. {bad[1]!r})")
    if failures:
        raise CheckFailed("Date parse failures:\n  " + "\n  ".join(failures))
    print("  [pass] zero date parse failures (8 date columns)")


def build_table(con, columns: list[dict]) -> None:
    selects = [
        f"{cast_expr(c['original_name'], c['type'])} AS {c['column']}"
        for c in columns if c["original_name"] is not None
    ]
    con.execute(f"CREATE TEMP TABLE cleaned AS SELECT {', '.join(selects)} FROM raw")
    final = [f"{DERIVED[c['column']]} AS {c['column']}" if c["original_name"] is None else c["column"] for c in columns]
    con.execute(f"CREATE TABLE {TABLE} AS SELECT {', '.join(final)} FROM cleaned")

    actual = con.execute(f"SELECT column_name, column_type FROM (DESCRIBE {TABLE})").fetchall()
    expected = [(c["column"], c["type"]) for c in columns]
    if actual != expected:
        raise CheckFailed(f"Table schema does not match the dictionary.\n  expected: {expected}\n  actual:   {actual}")


def hard_checks(con) -> None:
    rows = con.execute(f"SELECT count(*) FROM {TABLE}").fetchall()[0][0]
    if rows != EXPECTED_ROWS:
        raise CheckFailed(f"Expected {EXPECTED_ROWS} rows, got {rows}")
    print(f"  [pass] row count = {rows}")

    nulls, dupes = con.execute(
        f"SELECT count(*) FILTER (WHERE loan_number IS NULL), count(loan_number) - count(DISTINCT loan_number) FROM {TABLE}"
    ).fetchall()[0]
    if nulls or dupes:
        raise CheckFailed(f"loan_number has {nulls} NULLs and {dupes} duplicates (both must be 0)")
    print("  [pass] loan_number: 0 NULLs, 0 duplicates")

    periods = [r[0] for r in con.execute(f"SELECT DISTINCT end_of_period FROM {TABLE}").fetchall()]
    if periods != [EXPECTED_END_OF_PERIOD]:
        raise CheckFailed(f"Expected exactly one end_of_period = {EXPECTED_END_OF_PERIOD}, got {periods}")
    print(f"  [pass] exactly one end_of_period = {EXPECTED_END_OF_PERIOD}")

    flagged, codes = con.execute(
        f"SELECT count(*), list(DISTINCT country_code ORDER BY country_code) FROM {TABLE} WHERE is_regional_entry"
    ).fetchall()[0]
    if flagged != EXPECTED_REGIONAL_ROWS or set(codes or []) != EXPECTED_REGIONAL_CODES:
        raise CheckFailed(
            f"is_regional_entry: expected {EXPECTED_REGIONAL_ROWS} rows with codes {sorted(EXPECTED_REGIONAL_CODES)}, "
            f"got {flagged} rows with codes {codes}"
        )
    print(f"  [pass] is_regional_entry = {flagged} rows, codes {codes}")


def report_checks(con, columns: list[dict]) -> None:
    money_columns = [c["column"] for c in columns if c["column"].endswith("_usd")]
    print_table(
        con,
        f"original_principal = cancelled + undisbursed + disbursed (within ${TOLERANCE_USD:g})",
        f"""
        SELECT count(*) AS total_rows,
               count(*) FILTER (WHERE abs(original_principal_amount_usd - (cancelled_amount_usd + undisbursed_amount_usd + disbursed_amount_usd)) <= {TOLERANCE_USD}) AS pass,
               count(*) FILTER (WHERE abs(original_principal_amount_usd - (cancelled_amount_usd + undisbursed_amount_usd + disbursed_amount_usd)) > {TOLERANCE_USD}) AS fail,
               count(*) FILTER (WHERE original_principal_amount_usd IS NULL OR cancelled_amount_usd IS NULL OR undisbursed_amount_usd IS NULL OR disbursed_amount_usd IS NULL) AS has_null
        FROM {TABLE}
        """,
    )
    print_table(
        con,
        "  5 failing rows:",
        f"""
        SELECT loan_number, loan_type, loan_status, original_principal_amount_usd AS original, cancelled_amount_usd AS cancelled,
               undisbursed_amount_usd AS undisbursed, disbursed_amount_usd AS disbursed,
               round(original_principal_amount_usd - (cancelled_amount_usd + undisbursed_amount_usd + disbursed_amount_usd), 2) AS diff
        FROM {TABLE}
        WHERE abs(original_principal_amount_usd - (cancelled_amount_usd + undisbursed_amount_usd + disbursed_amount_usd)) > {TOLERANCE_USD}
        ORDER BY loan_number LIMIT 5
        """,
    )

    variants = {
        "repaid + due + sold": "repaid_to_ibrd_usd + due_to_ibrd_usd + sold_3rd_party_usd",
        "repaid + due + sold + exch_adj": "repaid_to_ibrd_usd + due_to_ibrd_usd + sold_3rd_party_usd + exchange_adjustment_usd",
        "repaid + due + sold - exch_adj": "repaid_to_ibrd_usd + due_to_ibrd_usd + sold_3rd_party_usd - exchange_adjustment_usd",
    }
    union = " UNION ALL ".join(
        f"SELECT '{label}' AS disbursed_equals, "
        f"count(*) FILTER (WHERE abs(disbursed_amount_usd - ({expr})) <= {TOLERANCE_USD}) AS pass, "
        f"count(*) FILTER (WHERE abs(disbursed_amount_usd - ({expr})) > {TOLERANCE_USD}) AS fail FROM {TABLE}"
        for label, expr in variants.items()
    )
    print_table(con, f"disbursed = repaid_to_ibrd + due_to_ibrd + sold_3rd_party (within ${TOLERANCE_USD:g})", union)
    print_table(
        con,
        "  5 rows failing the base identity:",
        f"""
        SELECT loan_number, loan_type, loan_status, disbursed_amount_usd AS disbursed, repaid_to_ibrd_usd AS repaid,
               due_to_ibrd_usd AS due, sold_3rd_party_usd AS sold, exchange_adjustment_usd AS exch_adj,
               round(disbursed_amount_usd - ({variants['repaid + due + sold']}), 2) AS diff
        FROM {TABLE}
        WHERE abs(disbursed_amount_usd - ({variants['repaid + due + sold']})) > {TOLERANCE_USD}
        ORDER BY loan_number LIMIT 5
        """,
    )

    negatives = " UNION ALL ".join(
        f"SELECT '{c}' AS money_column, count(*) FILTER (WHERE {c} < 0) AS negative_rows, min({c}) AS min_value, "
        f"count(*) FILTER (WHERE {c} IS NULL) AS null_rows FROM {TABLE}"
        for c in money_columns
    )
    print_table(con, "Negative values per money column", negatives)

    non_null = con.execute(f"SELECT count(currency_of_commitment) FROM {TABLE}").fetchall()[0][0]
    print(f"\ncurrency_of_commitment non-null count: {non_null}")


def build(db_path: Path = DB_PATH, report: bool = True) -> Path:
    """Delete and rebuild db_path. Raises CheckFailed (and leaves no file) if a hard check fails."""
    tmp_path = db_path.with_suffix(".duckdb.tmp")
    db_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    for path in (db_path, tmp_path, tmp_path.with_suffix(".tmp.wal")):
        path.unlink(missing_ok=True)

    print(f"Building {db_path} from {RAW_CSV.relative_to(ROOT)}")
    columns = load_dictionary_columns()
    source = [c for c in columns if c["original_name"] is not None]
    con = duckdb.connect(str(tmp_path))
    try:
        print("\nHard checks")
        load_raw(con, source)
        check_dates_parse(con, source)
        build_table(con, columns)
        hard_checks(con)
        if report:
            print("\nReport-only checks")
            report_checks(con, columns)
    except Exception:
        con.close()
        tmp_path.unlink(missing_ok=True)
        raise
    con.close()
    tmp_path.rename(db_path)
    return db_path


def ensure_database(db_path: Path = DB_PATH) -> Path:
    """Return db_path, building it first (hard checks only) if the file is missing."""
    if not db_path.exists():
        build(db_path, report=False)
    return db_path


def main() -> int:
    try:
        build()
    except CheckFailed as e:
        print(f"\nBUILD FAILED: {e}", file=sys.stderr)
        return 1
    print(f"\nOK: wrote {DB_PATH} (table {TABLE})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
