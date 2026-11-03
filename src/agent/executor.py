"""Run one already-validated SELECT on the local DuckDB file.

Defense in depth, independent of guardrails.py: the connection is read-only, external access
(files, network, extensions) is off, memory and threads are capped, spilling to disk is off
(temp_directory ''), and the configuration is locked so a query cannot change any of it.
A wall-clock timer interrupts queries that run too long.
"""

import threading
from dataclasses import dataclass
from pathlib import Path

import duckdb

from src.agent import config


class ExecutionError(Exception):
    """The query failed or timed out. The message is safe to show the model and the user."""


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[tuple]
    truncated: bool  # True when the query returned more than the row limit; rows holds the first row_limit


def connect(db_path: Path = config.DB_PATH) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(
        str(db_path),
        read_only=True,
        config={
            "enable_external_access": False,
            "memory_limit": config.MEMORY_LIMIT,
            "threads": config.THREADS,
            "temp_directory": "",  # no spilling: a query over the memory limit fails instead of filling the disk
            "lock_configuration": True,  # a query cannot SET any of the options above
        },
    )


def run_query(
    sql: str,
    db_path: Path = config.DB_PATH,
    row_limit: int = config.ROW_LIMIT,
    timeout_s: float = config.TIMEOUT_S,
) -> QueryResult:
    """Execute sql. The SQL is never rewritten: the row limit is applied with fetchmany."""
    con = connect(db_path)
    timer = threading.Timer(timeout_s, con.interrupt)
    timer.start()
    try:
        cursor = con.execute(sql)
        if cursor.description is None:
            raise ExecutionError("The statement returned no result set.")
        columns = [d[0] for d in cursor.description]
        rows = cursor.fetchmany(row_limit + 1)
    except duckdb.InterruptException:
        raise ExecutionError(f"That query took too long (over {timeout_s:g} s) and was stopped.") from None
    except duckdb.OutOfMemoryException:
        raise ExecutionError(f"That query needed too much memory (over {config.MEMORY_LIMIT}) and was stopped.") from None
    except duckdb.Error as e:
        raise ExecutionError(f"{type(e).__name__}: {e}") from None
    finally:
        timer.cancel()
        con.close()
    return QueryResult(columns=columns, rows=rows[:row_limit], truncated=len(rows) > row_limit)
