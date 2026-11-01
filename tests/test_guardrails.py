"""Guardrail tests: the SQL checker, plus the executor on its own (defense in depth).

    pytest -q
"""

import pytest

from scripts.build_db import ensure_database
from src.agent import config
from src.agent.executor import ExecutionError, run_query
from src.agent.guardrails import check_sql


@pytest.fixture(scope="session", autouse=True)
def database():
    ensure_database(config.DB_PATH)


BLOCKED = {
    "drop": "DROP TABLE ibrd_loans",
    "delete": "DELETE FROM ibrd_loans WHERE country = 'Brazil'",
    "insert": "INSERT INTO ibrd_loans (loan_number) VALUES ('X')",
    "update": "UPDATE ibrd_loans SET interest_rate = 0",
    "create": "CREATE TABLE x AS SELECT * FROM ibrd_loans",
    "select_then_drop": "SELECT 1; DROP TABLE ibrd_loans",
    "comment_then_drop": "SELECT 1 /* harmless */ ; /* */ DROP TABLE ibrd_loans",
    "line_comment_then_drop": "SELECT 1 --\n; DROP TABLE ibrd_loans",
    "delete_in_cte": "WITH d AS (DELETE FROM ibrd_loans RETURNING *) SELECT * FROM d",
    "read_csv": "SELECT * FROM read_csv('/etc/hosts')",
    "read_csv_in_subquery": "SELECT * FROM ibrd_loans WHERE country IN (SELECT * FROM read_csv('/etc/hosts'))",
    "file_path_as_table": "SELECT * FROM '/etc/hosts'",
    "attach": "ATTACH '/tmp/other.duckdb' AS other",
    "pragma": "PRAGMA database_list",
    "set": "SET enable_external_access = true",
    "copy": "COPY ibrd_loans TO '/tmp/out.csv'",
    "install": "INSTALL httpfs",
    "load": "LOAD httpfs",
    "call": "CALL pragma_version()",
    "describe": "DESCRIBE ibrd_loans",
    "other_table": "SELECT * FROM users",
    "join_other_table": "SELECT * FROM ibrd_loans l JOIN secrets s ON l.loan_number = s.id",
    "information_schema": "SELECT * FROM information_schema.tables",
    "qualified_table": "SELECT * FROM other.main.ibrd_loans",
    "duckdb_settings": "SELECT * FROM duckdb_settings()",
    "query_function": "SELECT * FROM query('DROP TABLE ibrd_loans')",
    "getenv": "SELECT getenv('HOME')",
    "current_setting": "SELECT current_setting('enable_external_access')",
    "range_source": "SELECT * FROM range(10)",
    "unparseable": "SELEC country FROM ibrd_loans",
    "empty": "   ",
}

ALLOWED = {
    "plain": "SELECT COUNT(*) FROM ibrd_loans WHERE is_guarantee = FALSE",
    "cte": """
        WITH by_country AS (
            SELECT country, SUM(original_principal_amount_usd) AS total
            FROM ibrd_loans WHERE is_guarantee = FALSE GROUP BY country
        )
        SELECT * FROM by_country ORDER BY total DESC LIMIT 5""",
    "union": """
        SELECT 'loans' AS kind, COUNT(*) FROM ibrd_loans WHERE is_guarantee = FALSE
        UNION ALL
        SELECT 'guarantees', COUNT(*) FROM ibrd_loans WHERE is_guarantee = TRUE""",
    "subquery": """
        SELECT country, original_principal_amount_usd FROM ibrd_loans
        WHERE original_principal_amount_usd = (SELECT MAX(original_principal_amount_usd) FROM ibrd_loans)""",
    "window": """
        SELECT country, board_approval_fy, original_principal_amount_usd,
               RANK() OVER (PARTITION BY board_approval_fy ORDER BY original_principal_amount_usd DESC) AS rnk
        FROM ibrd_loans WHERE board_approval_fy = 2024""",
    "trailing_semicolon": "SELECT COUNT(*) FROM ibrd_loans;",
    "comment_only": "SELECT COUNT(*) FROM ibrd_loans -- ; DROP TABLE ibrd_loans",
}


@pytest.mark.parametrize("sql", BLOCKED.values(), ids=BLOCKED.keys())
def test_blocked(sql):
    ok, reason = check_sql(sql)
    assert not ok
    assert reason


@pytest.mark.parametrize("sql", ALLOWED.values(), ids=ALLOWED.keys())
def test_allowed_passes_and_runs(sql):
    ok, reason = check_sql(sql)
    assert ok, reason
    result = run_query(sql)
    assert result.rows


# Defense in depth: the executor alone, with no guardrail in front, must still refuse these.
EXECUTOR_BLOCKED = {
    "read_csv": "SELECT * FROM read_csv('/etc/hosts')",
    "delete": "DELETE FROM ibrd_loans WHERE country = 'Brazil'",
    "create": "CREATE TABLE x AS SELECT 1",
    "set": "SET enable_external_access = true",
}


@pytest.mark.parametrize("sql", EXECUTOR_BLOCKED.values(), ids=EXECUTOR_BLOCKED.keys())
def test_executor_refuses_without_guardrails(sql):
    with pytest.raises(ExecutionError):
        run_query(sql)


def test_executor_data_unchanged_after_blocked_write():
    count = run_query("SELECT COUNT(*) FROM ibrd_loans").rows[0][0]
    assert count == 9538


def test_row_limit_sets_truncated():
    result = run_query("SELECT loan_number FROM ibrd_loans", row_limit=10)
    assert len(result.rows) == 10
    assert result.truncated
    small = run_query("SELECT loan_number FROM ibrd_loans LIMIT 10", row_limit=10)
    assert len(small.rows) == 10
    assert not small.truncated


def test_timeout_interrupts_long_query():
    slow = "SELECT COUNT(*) FROM ibrd_loans a, ibrd_loans b, ibrd_loans c"
    with pytest.raises(ExecutionError, match="longer than"):
        run_query(slow, timeout_s=0.5)
