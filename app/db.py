import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")  # SQLite ignores foreign keys unless asked
    return conn


def init_schema(conn):
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))


@contextmanager
def write_transaction(conn):
    """Take the write lock first, so 'check the quota, then insert' can not race."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        conn.rollback()
        raise
    conn.commit()
