"""SQLite connection helper for the medication tracker.

Every connection returned by this module has foreign-key enforcement
enabled (PRAGMA foreign_keys = ON), which is required for the
REFERENCES clauses in the schema to actually be enforced.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional


def connect(path: Optional[str] = None) -> sqlite3.Connection:
    """Open a SQLite connection with foreign keys enabled.

    Args:
        path: Filesystem path to the SQLite database file. When ``None``
            an in-memory database (``:memory:``) is used.

    The returned connection uses ``Row`` as its row factory so results
    behave like read-only mappings keyed by column name.
    """
    target = path if path is not None else ":memory:"
    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # foreign_pragma is a no-op read but keeps the pragma sticky per connection.
    return conn


def initialize(path: Optional[str] = None) -> sqlite3.Connection:
    """Open a connection and apply all pending migrations.

    Convenience wrapper around :func:`connect` and
    :func:`medication_tracker.migrations.runner.run_migrations` for
    callers that want a ready-to-use database in one step.
    """
    from .migrations.runner import run_migrations

    conn = connect(path)
    run_migrations(conn)
    return conn


def database_file() -> Path:
    """Return the default on-disk database location for the package."""
    import os

    env = os.environ.get("MEDICATION_TRACKER_DB")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent / "medication_tracker.db"