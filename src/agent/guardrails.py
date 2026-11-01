"""Check model-written SQL before it runs. Uses the parsed sqlglot AST, never regex.

    ok, reason = check_sql(sql)

Rules: exactly one statement; the root is a SELECT (CTEs allowed) or a set operation of SELECTs;
no write, DDL, PRAGMA, SET, ATTACH, COPY, INSTALL/LOAD or command node anywhere in the tree;
the only tables are ibrd_loans and CTEs defined in the query; no table functions or
file/system functions.
"""

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

from src.agent import config

DIALECT = "duckdb"

ALLOWED_ROOTS = (exp.Select, exp.Union, exp.Intersect, exp.Except)

FORBIDDEN_NODES = {
    exp.Insert: "INSERT", exp.Update: "UPDATE", exp.Delete: "DELETE", exp.Merge: "MERGE",
    exp.Create: "CREATE", exp.Drop: "DROP", exp.Alter: "ALTER", exp.TruncateTable: "TRUNCATE",
    exp.Command: "a command", exp.Pragma: "PRAGMA", exp.Set: "SET", exp.Attach: "ATTACH",
    exp.Detach: "DETACH", exp.Copy: "COPY", exp.Install: "INSTALL", exp.Use: "USE",
    exp.Transaction: "a transaction", exp.Commit: "COMMIT", exp.Rollback: "ROLLBACK",
    exp.Describe: "DESCRIBE", exp.Summarize: "SUMMARIZE", exp.Grant: "GRANT", exp.Revoke: "REVOKE",
    exp.Export: "EXPORT", exp.Analyze: "ANALYZE",
}

# Functions that read files, settings, the environment or the catalog. Checked by lower-case name.
FORBIDDEN_FUNCTION_PREFIXES = ("read_", "duckdb_", "pragma_", "parquet_", "sqlite_", "postgres_", "mysql_",
                               "iceberg_", "delta_")
FORBIDDEN_FUNCTIONS = {"glob", "getenv", "current_setting", "query", "query_table", "sniff_csv",
                       "which_secret", "checkpoint", "force_checkpoint"}


def function_name(node: exp.Func) -> str:
    return (node.name if isinstance(node, exp.Anonymous) else node.sql_name()).lower()


def check_sql(sql: str) -> tuple[bool, str]:
    """Return (True, "") if the SQL may run, else (False, plain-English reason)."""
    if not sql or not sql.strip():
        return False, "The SQL is empty."
    try:
        statements = sqlglot.parse(sql, dialect=DIALECT)
    except SqlglotError as e:
        return False, f"The SQL could not be parsed: {str(e).splitlines()[0]}"
    statements = [s for s in statements if s is not None and not isinstance(s, exp.Semicolon)]
    if len(statements) != 1:
        return False, f"Exactly one statement is allowed; found {len(statements)}."
    tree = statements[0]

    if not isinstance(tree, ALLOWED_ROOTS):
        return False, f"Only SELECT queries are allowed; this is {tree.key.upper()}."

    for node in tree.walk():
        for node_type, label in FORBIDDEN_NODES.items():
            if isinstance(node, node_type):
                return False, f"The query contains {label}, which is not allowed. Only reading is allowed."
        if isinstance(node, exp.Func):
            name = function_name(node)
            if name in FORBIDDEN_FUNCTIONS or name.startswith(FORBIDDEN_FUNCTION_PREFIXES):
                return False, f"The function {name}() is not allowed."

    cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    allowed_tables = {config.TABLE} | cte_names

    for table in tree.find_all(exp.Table):
        if not isinstance(table.this, exp.Identifier):
            return False, f"Table functions are not allowed ({table.this.sql(dialect=DIALECT)}). Query {config.TABLE} only."
        if table.db or table.catalog:
            return False, f"Only the table {config.TABLE} may be queried, not {table.sql(dialect=DIALECT)}."
        if table.name.lower() not in allowed_tables:
            return False, f"Only the table {config.TABLE} may be queried, not {table.name}."

    for clause in (*tree.find_all(exp.From), *tree.find_all(exp.Join)):
        source = clause.this
        if not isinstance(source, (exp.Table, exp.Subquery)):
            return False, f"Only {config.TABLE}, CTEs and subqueries may appear in FROM/JOIN, not {source.sql(dialect=DIALECT)}."

    return True, ""
