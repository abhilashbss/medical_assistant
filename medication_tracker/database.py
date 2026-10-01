"""Database connection and management."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Optional


class Database:
    """SQLite database manager for medication tracker."""

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

    def connect(self) -> sqlite3.Connection:
        """Create and return a database connection."""
        if self._connection is None:
            self._connection = sqlite3.connect(self.db_path)
            self._connection.row_factory = sqlite3.Row
            # Enable foreign keys
            self._connection.execute("PRAGMA foreign_keys = ON")
        return self._connection

    def close(self):
        """Close the database connection."""
        if self._connection:
            self._connection.close()
            self._connection = None

    @contextmanager
    def transaction(self):
        """Context manager for database transactions."""
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def execute(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        """Execute a SQL query and return the cursor."""
        conn = self.connect()
        return conn.execute(query, params)

    def executemany(self, query: str, params_list: list) -> sqlite3.Cursor:
        """Execute a SQL query with multiple parameter sets."""
        conn = self.connect()
        return conn.executemany(query, params_list)

    def init_schema(self):
        """Initialize the database schema."""
        with self.transaction() as conn:
            # Create medications table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS medications (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    dosage TEXT NOT NULL,
                    frequency TEXT NOT NULL,
                    start_date TEXT,
                    end_date TEXT,
                    status TEXT DEFAULT 'active' NOT NULL,
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now')),
                    CONSTRAINT chk_status CHECK (status IN ('active', 'completed')),
                    CONSTRAINT chk_name_not_empty CHECK (name <> '' AND name IS NOT NULL),
                    CONSTRAINT chk_dosage_not_empty CHECK (dosage <> '' AND dosage IS NOT NULL),
                    CONSTRAINT chk_frequency_not_empty CHECK (frequency <> '' AND frequency IS NOT NULL)
                )
            """)

            # Create indexes
            conn.execute("CREATE INDEX IF NOT EXISTS idx_medications_status ON medications(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_medications_created_at ON medications(created_at DESC)")

            # Create dose_records table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS dose_records (
                    id TEXT PRIMARY KEY,
                    medication_id TEXT NOT NULL,
                    date TEXT NOT NULL,
                    timestamp TEXT,
                    status TEXT DEFAULT 'taken' NOT NULL,
                    FOREIGN KEY (medication_id) REFERENCES medications(id) ON DELETE CASCADE,
                    CONSTRAINT chk_dose_status CHECK (status IN ('taken', 'skipped', 'missed')),
                    CONSTRAINT unique_medication_date UNIQUE (medication_id, date)
                )
            """)

            # Create indexes for dose_records
            conn.execute("CREATE INDEX IF NOT EXISTS idx_dose_records_medication_id ON dose_records(medication_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_dose_records_date ON dose_records(date)")


def get_database(db_path: Optional[str] = None) -> Database:
    """Get a database instance.

    Args:
        db_path: Optional path to database file

    Returns:
        Database instance
    """
    return Database(db_path)
