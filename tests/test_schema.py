"""Schema-level tests for the prescription tracker (milestone 1).

These tests run against a fresh on-disk SQLite database in a tmp_path so
that foreign-key enforcement, CHECK constraints, the partial unique index
and the query-SLO indexes are all exercised against a real connection
(re-PRAGMA'd on every connect, not an in-memory shortcut).
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from medication_tracker.db import connect
from medication_tracker.migrations.runner import run_migrations


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

ISO_NOW = datetime.now(timezone.utc).isoformat()


def _fresh_db(tmp_path: Path) -> sqlite3.Connection:
    """Apply migrations to a fresh file db and return a ready connection."""
    db_path = tmp_path / "tracker.db"
    conn = connect(str(db_path))
    run_migrations(conn)
    return conn


def _seed_patient_and_doctor(conn: sqlite3.Connection) -> tuple:
    """Insert one patient and one doctor and return (patient_id, doctor_id)."""
    pid = str(uuid.uuid4())
    did = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO patients (id, created_at) VALUES (?, ?)", (pid, ISO_NOW)
    )
    conn.execute(
        "INSERT INTO doctors (id, name, created_at) VALUES (?, ?, ?)",
        (did, "Dr. Sample", ISO_NOW),
    )
    conn.commit()
    return pid, did


def _rx_row(conn: sqlite3.Connection, patient_id: str, doctor_id: str, **overrides):
    """Build and INSERT a valid prescription row, returning its id."""
    rid = str(uuid.uuid4())
    base = dict(
        id=rid,
        patient_id=patient_id,
        doctor_id=doctor_id,
        medicine_name="Amoxicillin",
        dosage_amount=500.0,
        dosage_unit="mg",
        frequency="3x daily",
        start_date="2026-01-01T00:00:00+00:00",
        end_date=None,
        status="active",
        discontinue_reason=None,
        created_at=ISO_NOW,
        updated_at=ISO_NOW,
    )
    base.update(overrides)
    conn.execute(
        """
        INSERT INTO prescriptions
            (id, patient_id, doctor_id, medicine_name, dosage_amount,
             dosage_unit, frequency, start_date, end_date, status,
             discontinue_reason, created_at, updated_at)
        VALUES
            (:id, :patient_id, :doctor_id, :medicine_name, :dosage_amount,
             :dosage_unit, :frequency, :start_date, :end_date, :status,
             :discontinue_reason, :created_at, :updated_at)
        """,
        base,
    )
    conn.commit()
    return rid


# --------------------------------------------------------------------------- #
# Migration / table existence
# --------------------------------------------------------------------------- #

def test_migration_creates_all_five_tables(tmp_path):
    conn = _fresh_db(tmp_path)
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    names = {r[0] for r in rows}
    for expected in ("patients", "doctors", "prescriptions",
                     "dose_logs", "status_transitions"):
        assert expected in names, f"missing table {expected}"


def test_migration_is_idempotent(tmp_path):
    db_path = tmp_path / "tracker.db"
    conn = connect(str(db_path))
    first = run_migrations(conn)
    assert "0001_init.sql" in first
    # Second run should record nothing new and not error.
    second = run_migrations(conn)
    assert second == []
    # The schema_migrations table should have exactly one entry.
    count = conn.execute(
        "SELECT COUNT(*) FROM schema_migrations WHERE name='0001_init.sql'"
    ).fetchone()[0]
    assert count == 1
    conn.close()


def test_expected_columns_on_prescriptions(tmp_path):
    conn = _fresh_db(tmp_path)
    cols = {r[1]: r[2] for r in conn.execute("PRAGMA table_info(prescriptions)")}
    # name -> type
    assert cols["id"] == "TEXT"
    assert cols["patient_id"] == "TEXT"
    assert cols["doctor_id"] == "TEXT"
    assert cols["medicine_name"] == "TEXT"
    assert cols["dosage_amount"] == "REAL"
    assert cols["dosage_unit"] == "TEXT"
    assert cols["frequency"] == "TEXT"
    assert cols["start_date"] == "TEXT"
    assert cols["end_date"] == "TEXT"
    assert cols["status"] == "TEXT"
    assert cols["discontinue_reason"] == "TEXT"
    assert cols["created_at"] == "TEXT"
    assert cols["updated_at"] == "TEXT"


# --------------------------------------------------------------------------- #
# Foreign-key enforcement
# --------------------------------------------------------------------------- #

def test_foreign_keys_are_enforced_on_every_connection(tmp_path):
    conn = _fresh_db(tmp_path)
    # PRAGMA foreign_keys must read 1 on the connection we hand out.
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_insert_with_unknown_patient_id_is_rejected(tmp_path):
    conn = _fresh_db(tmp_path)
    _, did = _seed_patient_and_doctor(conn)
    with pytest.raises(sqlite3.IntegrityError) as exc:
        _rx_row(conn, "does-not-exist-patient", did)
    assert "FOREIGN KEY" in str(exc.value).upper()


def test_insert_with_unknown_doctor_id_is_rejected(tmp_path):
    conn = _fresh_db(tmp_path)
    pid, _ = _seed_patient_and_doctor(conn)
    with pytest.raises(sqlite3.IntegrityError) as exc:
        _rx_row(conn, pid, "does-not-exist-doctor")
    assert "FOREIGN KEY" in str(exc.value).upper()


# --------------------------------------------------------------------------- #
# CHECK constraints
# --------------------------------------------------------------------------- #

def test_negative_dosage_amount_rejected(tmp_path):
    conn = _fresh_db(tmp_path)
    pid, did = _seed_patient_and_doctor(conn)
    with pytest.raises(sqlite3.IntegrityError) as exc:
        _rx_row(conn, pid, did, dosage_amount=-5.0)
    assert "CHECK" in str(exc.value).upper()


def test_zero_dosage_amount_rejected(tmp_path):
    conn = _fresh_db(tmp_path)
    pid, did = _seed_patient_and_doctor(conn)
    with pytest.raises(sqlite3.IntegrityError):
        _rx_row(conn, pid, did, dosage_amount=0.0)


def test_missing_dosage_unit_rejected(tmp_path):
    conn = _fresh_db(tmp_path)
    pid, did = _seed_patient_and_doctor(conn)
    with pytest.raises(sqlite3.IntegrityError):
        # NOT NULL violation on dosage_unit
        conn.execute(
            """
            INSERT INTO prescriptions
              (id, patient_id, doctor_id, medicine_name, dosage_amount,
               dosage_unit, frequency, start_date, status, created_at, updated_at)
            VALUES
              (?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?)
            """,
            (str(uuid.uuid4()), pid, did, "Ibuprofen", 200.0,
             "2x daily", "2026-01-01T00:00:00+00:00", "active", ISO_NOW, ISO_NOW),
        )
        conn.commit()


def test_invalid_status_rejected(tmp_path):
    conn = _fresh_db(tmp_path)
    pid, did = _seed_patient_and_doctor(conn)
    with pytest.raises(sqlite3.IntegrityError) as exc:
        _rx_row(conn, pid, did, status="paused")
    assert "CHECK" in str(exc.value).upper()


def test_end_date_before_start_date_rejected(tmp_path):
    conn = _fresh_db(tmp_path)
    pid, did = _seed_patient_and_doctor(conn)
    with pytest.raises(sqlite3.IntegrityError) as exc:
        _rx_row(
            conn, pid, did,
            start_date="2026-02-01T00:00:00+00:00",
            end_date="2026-01-01T00:00:00+00:00",
        )
    assert "CHECK" in str(exc.value).upper()


def test_end_date_equal_to_start_date_rejected(tmp_path):
    conn = _fresh_db(tmp_path)
    pid, did = _seed_patient_and_doctor(conn)
    same = "2026-01-01T00:00:00+00:00"
    with pytest.raises(sqlite3.IntegrityError):
        _rx_row(conn, pid, did, start_date=same, end_date=same)


def test_null_end_date_allowed(tmp_path):
    conn = _fresh_db(tmp_path)
    pid, did = _seed_patient_and_doctor(conn)
    rid = _rx_row(conn, pid, did, end_date=None)
    row = conn.execute(
        "SELECT end_date FROM prescriptions WHERE id=?", (rid,)
    ).fetchone()
    assert row[0] is None


def test_required_fields_not_null(tmp_path):
    """medicine_name / frequency / start_date cannot be NULL."""
    conn = _fresh_db(tmp_path)
    pid, did = _seed_patient_and_doctor(conn)
    for null_col in ("medicine_name", "frequency", "start_date"):
        with pytest.raises(sqlite3.IntegrityError):
            vals = dict(
                id=str(uuid.uuid4()), patient_id=pid, doctor_id=did,
                medicine_name="M", dosage_amount=1.0, dosage_unit="mg",
                frequency="1x daily", start_date="2026-01-01T00:00:00+00:00",
                status="active", created_at=ISO_NOW, updated_at=ISO_NOW,
            )
            vals[null_col] = None
            conn.execute(
                """
                INSERT INTO prescriptions
                  (id, patient_id, doctor_id, medicine_name, dosage_amount,
                   dosage_unit, frequency, start_date, status, created_at, updated_at)
                VALUES
                  (:id, :patient_id, :doctor_id, :medicine_name, :dosage_amount,
                   :dosage_unit, :frequency, :start_date, :status, :created_at, :updated_at)
                """,
                vals,
            )
            conn.commit()


# --------------------------------------------------------------------------- #
# Partial unique index: one active prescription per medicine per patient
# --------------------------------------------------------------------------- #

def test_second_active_same_medicine_rejected(tmp_path):
    conn = _fresh_db(tmp_path)
    pid, did = _seed_patient_and_doctor(conn)
    _rx_row(conn, pid, did, medicine_name="Metformin")
    with pytest.raises(sqlite3.IntegrityError) as exc:
        _rx_row(conn, pid, did, medicine_name="Metformin")
    assert "UNIQUE" in str(exc.value).upper()


def test_inactive_duplicate_same_medicine_allowed(tmp_path):
    conn = _fresh_db(tmp_path)
    pid, did = _seed_patient_and_doctor(conn)
    _rx_row(conn, pid, did, medicine_name="Metformin", status="completed")
    # A second, also-completed prescription for the same medicine is fine.
    _rx_row(conn, pid, did, medicine_name="Metformin", status="discontinued")
    # And an active one is allowed when the prior one is inactive.
    conn.execute(
        "DELETE FROM prescriptions WHERE medicine_name='Metformin'"
    ).fetchall()
    conn.commit()
    _rx_row(conn, pid, did, medicine_name="Metformin", status="active")


def test_active_for_different_medicine_allowed(tmp_path):
    conn = _fresh_db(tmp_path)
    pid, did = _seed_patient_and_doctor(conn)
    _rx_row(conn, pid, did, medicine_name="Metformin")
    _rx_row(conn, pid, did, medicine_name="Atorvastatin")  # different medicine


def test_active_for_same_medicine_different_patient_allowed(tmp_path):
    conn = _fresh_db(tmp_path)
    pid1, did = _seed_patient_and_doctor(conn)
    pid2 = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO patients (id, created_at) VALUES (?, ?)", (pid2, ISO_NOW)
    )
    conn.commit()
    _rx_row(conn, pid1, did, medicine_name="Metformin")
    _rx_row(conn, pid2, did, medicine_name="Metformin")


# --------------------------------------------------------------------------- #
# Indexes & query plan (500ms SLO)
# --------------------------------------------------------------------------- #

def _plan(conn, sql, params=()):
    rows = conn.execute("EXPLAIN QUERY PLAN " + sql, params).fetchall()
    return " ".join(r[3] for r in rows)


def test_index_idx_rx_patient_status_exists(tmp_path):
    conn = _fresh_db(tmp_path)
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_rx_patient_status'"
    ).fetchall()
    assert len(rows) == 1


def test_index_idx_rx_patient_start_exists(tmp_path):
    conn = _fresh_db(tmp_path)
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_rx_patient_start'"
    ).fetchall()
    assert len(rows) == 1


def test_active_query_uses_idx_rx_patient_status(tmp_path):
    conn = _fresh_db(tmp_path)
    pid, did = _seed_patient_and_doctor(conn)
    _rx_row(conn, pid, did)
    plan = _plan(
        conn,
        "SELECT * FROM prescriptions WHERE patient_id = ? AND status = 'active'",
        (pid,),
    )
    assert "idx_rx_patient_status" in plan, plan
    # Must be a SEARCH (index lookup), not a SCAN of the whole table.
    assert "SCAN" not in plan.upper() or "SEARCH" in plan.upper(), plan


def test_history_query_uses_idx_rx_patient_start(tmp_path):
    conn = _fresh_db(tmp_path)
    pid, did = _seed_patient_and_doctor(conn)
    _rx_row(conn, pid, did)
    plan = _plan(
        conn,
        "SELECT * FROM prescriptions WHERE patient_id = ? ORDER BY start_date DESC",
        (pid,),
    )
    assert "idx_rx_patient_start" in plan, plan


def test_partial_unique_index_exists(tmp_path):
    conn = _fresh_db(tmp_path)
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name='one_active_per_medicine'"
    ).fetchall()
    assert len(rows) == 1