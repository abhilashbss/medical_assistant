"""Database connection and management."""

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Optional


class Database:
    """SQLite database manager for the prescription tracker."""

    def __init__(self, db_path: Optional[str] = None):
        """Initialize database connection.

        Args:
            db_path: Path to SQLite database file. Defaults to in-memory database.
        """
        if db_path is None:
            self.db_path = ":memory:"
        else:
            self.db_path = db_path
        self._connection: Optional[sqlite3.Connection] = None
        # A single shared connection is used across threads (uvicorn dispatches
        # sync endpoints to a threadpool). sqlite3 permits cross-thread access
        # with check_same_thread=False, but a shared connection is NOT safe for
        # concurrent use: interleaved statements/commits from two threads
        # deadlock. This lock serializes all access so the connection is only
        # ever used by one thread at a time.
        self._lock = threading.RLock()

    def connect(self) -> sqlite3.Connection:
        """Create and return a database connection."""
        with self._lock:
            if self._connection is None:
                self._connection = sqlite3.connect(self.db_path, check_same_thread=False)
                self._connection.row_factory = sqlite3.Row
                # Enable foreign key enforcement
                self._connection.execute("PRAGMA foreign_keys = ON")
            return self._connection

    def close(self):
        """Close the database connection."""
        with self._lock:
            if self._connection:
                self._connection.close()
                self._connection = None

    @contextmanager
    def transaction(self):
        """Context manager for a database transaction.

        Commits on success, rolls back on exception. Holds the connection lock
        for the duration so concurrent callers cannot interleave statements
        within a transaction.
        """
        with self._lock:
            conn = self.connect()
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def execute(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        """Execute a SQL query with parameterized params and return the cursor."""
        with self._lock:
            conn = self.connect()
            return conn.execute(query, params)

    def init_schema(self):
        """Initialize the full schema from the migration files."""
        migrations_dir = Path(__file__).resolve().parent.parent / "migrations"
        conn = self.connect()
        # 0001_init.sql first (creates prescriptions etc.)
        init_path = migrations_dir / "0001_init.sql"
        if init_path.exists():
            conn.executescript(init_path.read_text())
        # dose_logs migration second (references prescriptions)
        dose_logs_path = migrations_dir / "create_dose_logs_table.sql"
        if dose_logs_path.exists():
            conn.executescript(dose_logs_path.read_text())
        conn.commit()


def get_database(db_path: Optional[str] = None) -> Database:
    """Get a Database instance."""
    return Database(db_path)