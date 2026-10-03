"""Database connection and schema management for the prescription tracker."""

import sqlite3
from contextlib import contextmanager
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

    def connect(self) -> sqlite3.Connection:
        """Create and return a database connection."""
        if self._connection is None:
            self._connection = sqlite3.connect(self.db_path)
            self._connection.row_factory = sqlite3.Row
            self._connection.execute("PRAGMA foreign_keys = ON")
        return self._connection

    def close(self):
        """Close the database connection."""
        if self._connection:
            self._connection.close()
            self._connection = None

    @contextmanager
    def transaction(self):
        """Context manager for a database transaction."""
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

    def init_schema(self):
        """Create the prescription tracker schema (idempotent)."""
        with self.transaction() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS patients (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TEXT
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS doctors (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TEXT
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS prescriptions (
                    id TEXT PRIMARY KEY,
                    patient_id TEXT NOT NULL,
                    doctor_id TEXT NOT NULL,
                    medicine_name TEXT NOT NULL,
                    dosage_amount TEXT NOT NULL,
                    dosage_unit TEXT NOT NULL,
                    frequency TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT,
                    updated_at TEXT,
                    FOREIGN KEY (patient_id) REFERENCES patients(id),
                    FOREIGN KEY (doctor_id) REFERENCES doctors(id),
                    CONSTRAINT chk_rx_status CHECK (status IN ('active', 'completed', 'discontinued')),
                    CONSTRAINT chk_rx_end_date CHECK (end_date IS NULL OR end_date >= start_date),
                    CONSTRAINT chk_rx_medicine CHECK (medicine_name <> ''),
                    CONSTRAINT chk_rx_dosage_amount CHECK (dosage_amount <> ''),
                    CONSTRAINT chk_rx_dosage_unit CHECK (dosage_unit <> ''),
                    CONSTRAINT chk_rx_frequency CHECK (frequency <> '')
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS status_transitions (
                    id TEXT PRIMARY KEY,
                    prescription_id TEXT NOT NULL,
                    from_status TEXT,
                    to_status TEXT,
                    reason TEXT,
                    transitioned_at TEXT,
                    FOREIGN KEY (prescription_id) REFERENCES prescriptions(id) ON DELETE CASCADE
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS dose_logs (
                    id TEXT PRIMARY KEY,
                    prescription_id TEXT NOT NULL,
                    event TEXT NOT NULL CHECK (event IN ('taken', 'skipped', 'missed')),
                    logged_at TEXT,
                    timestamp TEXT,
                    taken_at TEXT,
                    notes TEXT,
                    status TEXT CHECK (status IS NULL OR status IN ('taken', 'skipped', 'missed')),
                    FOREIGN KEY (prescription_id) REFERENCES prescriptions(id) ON DELETE CASCADE
                )
                """
            )

            # Partial unique index: at most one active prescription per medicine per patient.
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_one_active_per_medicine
                ON prescriptions(patient_id, medicine_name)
                WHERE status = 'active'
                """
            )

            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_prescriptions_patient_start "
                "ON prescriptions(patient_id, start_date DESC)"
            )

            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_prescriptions_status ON prescriptions(status)"
            )

            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_rx_patient_status "
                "ON prescriptions(patient_id, status)"
            )

            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_status_transitions_rx "
                "ON status_transitions(prescription_id)"
            )

            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_dose_logs_rx_time "
                "ON dose_logs(prescription_id, timestamp)"
            )

            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_dose_logs_rx_logged "
                "ON dose_logs(prescription_id, logged_at)"
            )


def get_database(db_path: Optional[str] = None) -> Database:
    """Get a Database instance.

    Args:
        db_path: Optional path to database file.

    Returns:
        Database instance.
    """
    return Database(db_path)