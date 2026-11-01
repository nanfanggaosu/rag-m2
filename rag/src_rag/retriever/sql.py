"""SQL path (partner B): read-only execution layer for LLM-generated queries."""
from __future__ import annotations

import re
import sqlite3
import time
from contextlib import closing
from itertools import islice
from pathlib import Path

from rag.src_rag.interfaces import SqlRagResult

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DB_PATH = PROJECT_ROOT / "rag" / "data" / "raw" / "wahadb.sqlite"

_READ_ONLY_PREFIX = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)

# A single function call like randomblob(1e9) is one VM step, so the timeout can't stop it;
# capping value size can.
MAX_VALUE_BYTES = 1_000_000

MAX_COUNTED_ROWS = 100_000

# Enforced by SQLite itself at prepare time, so keyword tricks in string literals or
# comments can't smuggle a write, PRAGMA or ATTACH past a regex check.
_ALLOWED_ACTIONS = {
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_FUNCTION,
    sqlite3.SQLITE_RECURSIVE,
}


class UnsafeSqlError(ValueError):
    pass


def _authorizer(action: int, *_: object) -> int:
    return sqlite3.SQLITE_OK if action in _ALLOWED_ACTIONS else sqlite3.SQLITE_DENY


def _connect_read_only(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"{db_path.as_uri()}?mode=ro", uri=True)
    conn.set_authorizer(_authorizer)
    conn.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, MAX_VALUE_BYTES)
    return conn


def run_sql(
    sql: str,
    *,
    max_rows: int = 50,
    timeout_s: float = 10.0,
    db_path: Path = DB_PATH,
) -> SqlRagResult:
    """Execute one read-only query; failures come back in `error` instead of raising."""
    t0 = time.perf_counter()

    def result(**kwargs) -> SqlRagResult:
        elapsed = (time.perf_counter() - t0) * 1000
        return SqlRagResult(sql=sql, elapsed_ms=elapsed, **kwargs)

    try:
        if not _READ_ONLY_PREFIX.match(sql):
            raise UnsafeSqlError("only SELECT / WITH queries are allowed")

        with closing(_connect_read_only(db_path)) as conn:
            deadline = t0 + timeout_s
            conn.set_progress_handler(lambda: time.perf_counter() > deadline, 10_000)
            cur = conn.execute(sql)
            columns = [d[0] for d in cur.description or []]
            rows = [dict(zip(columns, r)) for r in cur.fetchmany(max_rows)]
            total_rows = len(rows) + sum(1 for _ in islice(cur, MAX_COUNTED_ROWS))
    except (sqlite3.Error, UnsafeSqlError) as e:
        return result(rows=[], columns=[], error=f"{type(e).__name__}: {e}")

    return result(rows=rows, columns=columns, total_rows=total_rows)
