"""One way to open SQLite, used by both databases."""
import sqlite3
from contextlib import contextmanager


def connect(path: str) -> sqlite3.Connection:
    """Autocommit connection; transactions are explicit. Waits up to 5 s for another writer."""
    conn = sqlite3.connect(path, isolation_level=None, timeout=5.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection):
    """BEGIN IMMEDIATE (write lock first: no deadlock). Joins a transaction that is already open."""
    if conn.in_transaction:
        yield conn
        return
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")
