"""Database layer for the medicine tracker.

Uses SQLite for persistence so medication data survives app restarts. The
schema matches Unit #0's contract: a medications table with required name and
dosage NOT NULL columns plus status tracking, and a dose_records table for
timestamped dose records (Unit #2).
"""

import os
import sqlite3
from pathlib import Path
from typing import Optional

DEFAULT_DB_PATH = os.environ.get(
    "MEDICATION_DB_PATH",
    str(Path(__file__).resolve().parent / "medications.db"),
)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS medications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    dosage TEXT NOT NULL,
    frequency TEXT,
    start_date TEXT,
    end_date TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dose_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    medication_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'taken',
    FOREIGN KEY (medication_id) REFERENCES medications(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_dose_medication_id ON dose_records(medication_id);
CREATE INDEX IF NOT EXISTS idx_dose_date ON dose_records(date);
CREATE INDEX IF NOT EXISTS idx_medications_created_at ON medications(created_at);
"""


class Database:
    """Thin wrapper around a sqlite3 connection.

    Each call opens a fresh connection so that simulated app restarts (a new
    Database pointing at the same file) genuinely re-read from disk — this is
    what makes persistence verifiable in tests.
    """

    def __init__(self, path: str = DEFAULT_DB_PATH):
        self.path = path
        self._init_schema()

    def _init_schema(self) -> None:
        conn = sqlite3.connect(self.path)
        try:
            conn.executescript(SCHEMA_SQL)
            conn.commit()
        finally:
            conn.close()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def reset(self) -> None:
        """Drop and recreate all tables (for tests)."""
        conn = sqlite3.connect(self.path)
        try:
            conn.executescript(
                "DROP TABLE IF EXISTS dose_records;"
                "DROP TABLE IF EXISTS medications;"
            )
            conn.commit()
        finally:
            conn.close()
        self._init_schema()


_db: Optional[Database] = None


def get_db(path: Optional[str] = None) -> Database:
    """Return a process-wide Database instance, or a fresh one at ``path``."""
    global _db
    if path is not None or _db is None:
        _db = Database(path or DEFAULT_DB_PATH)
    return _db


def reset_db(path: Optional[str] = None) -> None:
    """Reset the global db (used by tests to start clean)."""
    global _db
    _db = Database(path or DEFAULT_DB_PATH)
    _db.reset()