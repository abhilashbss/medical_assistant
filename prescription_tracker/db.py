"""SQLite database initialization with foreign key enforcement."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

_MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def get_connection(db_path: str = ":memory:") -> sqlite3.Connection:
    """Open a SQLite connection with PRAGMA foreign_keys = ON and WAL journal.

    The connection is configured to enforce foreign keys at the connection
    level (PRAGMA foreign_keys = ON), use row factory for dict-like access,
    and enable WAL journaling for concurrent read performance.
    """
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # WAL improves read throughput under write load for benchmark workloads.
    if db_path != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """Apply the migration SQL to the given connection.

    The shared migration creates both naming conventions for the query-SLO
    indexes (``idx_prescriptions_patient_*`` used by this stack and
    ``idx_rx_patient_*`` used by the reference stack). Duplicate indexes let
    SQLite's planner pick either, which would make EXPLAIN QUERY PLAN
    assertions non-deterministic, so the reference-stack aliases are dropped
    here to leave this stack with a single deterministic index per query path.
    """
    migration_file = _MIGRATIONS_DIR / "0001_init.sql"
    sql = migration_file.read_text()
    conn.executescript(sql)
    for alias in ("idx_rx_patient_status", "idx_rx_patient_start",
                  "one_active_per_medicine"):
        conn.execute(f"DROP INDEX IF EXISTS {alias}")
    conn.commit()


def init_db(db_path: str = ":memory:") -> sqlite3.Connection:
    """Convenience: open a connection and apply the schema."""
    conn = get_connection(db_path)
    init_schema(conn)
    return conn


def seed_reference_data(conn: sqlite3.Connection, patient_id: str, doctor_id: str,
                        patient_name: Optional[str] = None,
                        doctor_name: Optional[str] = None) -> None:
    """Insert patient and doctor reference rows if absent."""
    if patient_name is None:
        patient_name = f"patient-{patient_id}"
    if doctor_name is None:
        doctor_name = f"doctor-{doctor_id}"
    conn.execute(
        "INSERT OR IGNORE INTO patients (id, name) VALUES (?, ?)",
        (patient_id, patient_name),
    )
    conn.execute(
        "INSERT OR IGNORE INTO doctors (id, name) VALUES (?, ?)",
        (doctor_id, doctor_name),
    )
    conn.commit()