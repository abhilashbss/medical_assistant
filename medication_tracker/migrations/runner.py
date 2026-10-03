"""Idempotent migration runner for the medication tracker.

Migrations are plain ``.sql`` files in ``migrations/`` named
``NNNN_description.sql``. They are applied in lexical (numeric) order.
A ``schema_migrations`` table records which migrations have already been
applied so re-running the runner is a no-op.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import List


MIGRATIONS_DIR = Path(__file__).resolve().parent.parent.parent / "migrations"


def _ensure_tracking_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            name        TEXT PRIMARY KEY,
            applied_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        )
        """
    )
    conn.commit()


def _applied_migrations(conn: sqlite3.Connection) -> set:
    _ensure_tracking_table(conn)
    rows = conn.execute("SELECT name FROM schema_migrations").fetchall()
    return {r[0] for r in rows}


def _pending_migrations(applied: set) -> List[Path]:
    if not MIGRATIONS_DIR.is_dir():
        return []
    files = sorted(p for p in MIGRATIONS_DIR.glob("*.sql"))
    return [p for p in files if p.name not in applied]


def run_migrations(conn: sqlite3.Connection) -> List[str]:
    """Apply all pending ``.sql`` migrations to *conn* idempotently.

    Returns the names of migrations applied during this call (empty list
    when the database is already up to date). Each migration is executed
    in its own transaction; on failure the transaction is rolled back and
    the error propagates without recording the migration as applied.
    """
    applied = _applied_migrations(conn)
    pending = _pending_migrations(applied)
    applied_now: List[str] = []
    for path in pending:
        sql = path.read_text(encoding="utf-8")
        try:
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO schema_migrations (name) VALUES (?)",
                (path.name,),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        applied_now.append(path.name)
    return applied_now