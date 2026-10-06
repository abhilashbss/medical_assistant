"""Data-access layer for the prescription tracker.

Parameterized SQL only — no string interpolation. This module is the
single chokepoint through which prescription rows are inserted and read.
It enforces the application-level invariants that the schema cannot:
ISO 8601-with-timezone datetime strings, and the end_date-after-start_date
rule for the API path (the schema CHECK is the backstop).

The schema layer (migrations/0001_init.sql) enforces:
  * foreign keys (with PRAGMA foreign_keys = ON from db.connect)
  * dosage_amount > 0
  * status IN ('active','completed','discontinued')
  * end_date IS NULL OR end_date > start_date
  * one active prescription per (patient_id, medicine_name)
"""

from __future__ import annotations

import re

import sqlite3

import uuid

from datetime import datetime

from typing import Any, Dict, List, Optional

from datetime import datetime, timezone

from medication_tracker.models import Prescription, PrescriptionStatus

from typing import List, Optional

from .database import Database

from .models import Prescription, PrescriptionStatus, StatusTransition



_ISO8601_TZ = re.compile(
    r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}"
    r"(\.\d+)?"
    r"(Z|[+-]\d{2}:?\d{2})$"
)

class ValidationError(ValueError):
    """Raised when input fails application-level validation (API path).

    Carries ``field`` and ``message`` so the HTTP layer can surface a
    per-field 400 response. This is distinct from
    :class:`medication_tracker.errors.ValidationError`, which aggregates
    multiple ``(field, message)`` tuples for the validator layer.
    """

    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message
        super().__init__(f"{field}: {message}")

def _require(value: Any, field: str) -> Any:
    if value is None or (isinstance(value, str) and value.strip() == ""):
        raise ValidationError(field, "is required")
    return value

def _validate_iso8601_tz(value: str, field: str) -> str:
    if not isinstance(value, str) or not _ISO8601_TZ.match(value):
        raise ValidationError(field, "must be an ISO 8601 datetime with timezone")
    return value

def _now_iso() -> str:
    """Current UTC time as an ISO 8601 string with an offset."""
    return datetime.now(timezone.utc).isoformat()

def ensure_patient(conn: sqlite3.Connection, patient_id: str) -> str:
    """Insert a patient row if absent so prescriptions can reference it."""
    _require(patient_id, "patient_id")
    conn.execute(
        "INSERT OR IGNORE INTO patients (id, created_at) VALUES (?, ?)",
        (patient_id, _now_iso()),
    )
    conn.commit()
    return patient_id

def ensure_doctor(conn: sqlite3.Connection, doctor_id: str, name: str = "Unknown") -> str:
    _require(doctor_id, "doctor_id")
    conn.execute(
        "INSERT OR IGNORE INTO doctors (id, name, created_at) VALUES (?, ?, ?)",
        (doctor_id, name, _now_iso()),
    )
    conn.commit()
    return doctor_id

REQUIRED_CREATE_FIELDS = (
    "patient_id", "doctor_id", "medicine_name",
    "dosage_amount", "dosage_unit", "frequency", "start_date",
)

def create_prescription(conn: sqlite3.Connection, data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and insert a prescription. Returns the stored row.

    Raises :class:`ValidationError` for missing/invalid input and lets the
    sqlite3 integrity errors (FK / CHECK / UNIQUE) surface to the caller.
    """
    for field in REQUIRED_CREATE_FIELDS:
        _require(data.get(field), field)

    dosage_amount = data["dosage_amount"]
    if not isinstance(dosage_amount, (int, float)) or isinstance(dosage_amount, bool):
        raise ValidationError("dosage_amount", "must be a number")
    if dosage_amount <= 0:
        raise ValidationError("dosage_amount", "must be greater than 0")

    dosage_unit = data["dosage_unit"]
    if not isinstance(dosage_unit, str) or not dosage_unit.strip():
        raise ValidationError("dosage_unit", "must not be empty")

    start_date = _validate_iso8601_tz(data["start_date"], "start_date")
    end_date = data.get("end_date")
    if end_date is not None:
        end_date = _validate_iso8601_tz(end_date, "end_date")
        if end_date <= start_date:
            raise ValidationError("end_date", "must be after start_date")

    rx_id = data.get("id") or str(uuid.uuid4())
    now = _now_iso()
    row = {
        "id": rx_id,
        "patient_id": data["patient_id"],
        "doctor_id": data["doctor_id"],
        "medicine_name": data["medicine_name"],
        "dosage_amount": float(dosage_amount),
        "dosage_unit": dosage_unit,
        "frequency": data["frequency"],
        "start_date": start_date,
        "end_date": end_date,
        "status": "active",
        "discontinue_reason": None,
        "created_at": now,
        "updated_at": now,
    }
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
        row,
    )
    conn.commit()
    return get_prescription(conn, rx_id)

def get_prescription(conn: sqlite3.Connection, rx_id: str) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        "SELECT * FROM prescriptions WHERE id = ?", (rx_id,)
    ).fetchone()
    return dict(row) if row else None

def list_by_patient(conn: sqlite3.Connection, patient_id: str) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT * FROM prescriptions
        WHERE patient_id = ?
        ORDER BY start_date DESC
        """,
        (patient_id,),
    ).fetchall()
    return [dict(r) for r in rows]

def _record_transition(conn, rx_id, from_status, to_status, reason):
    conn.execute(
        """
        INSERT INTO status_transitions
            (id, prescription_id, from_status, to_status, reason, transitioned_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (str(uuid.uuid4()), rx_id, from_status, to_status, reason, _now_iso()),
    )

def discontinue_prescription(
    conn: sqlite3.Connection, rx_id: str, reason: str
) -> Dict[str, Any]:
    """Mark an active prescription discontinued with a mandatory reason."""
    _require(reason, "reason")
    row = get_prescription(conn, rx_id)
    if row is None:
        raise KeyError(rx_id)
    if row["status"] != "active":
        raise ValidationError("status", "only active prescriptions can be discontinued")
    now = _now_iso()
    conn.execute(
        """
        UPDATE prescriptions
        SET status = 'discontinued',
            discontinue_reason = ?,
            updated_at = ?
        WHERE id = ? AND status = 'active'
        """,
        (reason, now, rx_id),
    )
    _record_transition(conn, rx_id, "active", "discontinued", reason)
    conn.commit()
    updated = get_prescription(conn, rx_id)
    assert updated is not None
    return updated

def complete_prescription(conn: sqlite3.Connection, rx_id: str) -> Dict[str, Any]:
    row = get_prescription(conn, rx_id)
    if row is None:
        raise KeyError(rx_id)
    if row["status"] != "active":
        raise ValidationError("status", "only active prescriptions can be completed")
    now = _now_iso()
    conn.execute(
        "UPDATE prescriptions SET status = 'completed', updated_at = ? "
        "WHERE id = ? AND status = 'active'",
        (now, rx_id),
    )
    _record_transition(conn, rx_id, "active", "completed", None)
    conn.commit()
    updated = get_prescription(conn, rx_id)
    assert updated is not None
    return updated

class PrescriptionNotFoundError(Exception):
    """Raised when a prescription is not found in the repository."""
    def __init__(self, prescription_id: str = None):
        self.prescription_id = prescription_id
        message = f"Prescription not found: {prescription_id}" if prescription_id else "Prescription not found"
        super().__init__(message)

def init_schema(conn: sqlite3.Connection) -> None:
    """Apply the prescription-tracker schema to ``conn``.

    Idempotent — safe to call on a fresh or existing database. Used by the
    repository and by tests to set up an in-memory database. Delegates to the
    schema-foundation migration runner so there is a single source of truth
    for the DDL.
    """
    from medication_tracker.migrations.runner import run_migrations

    run_migrations(conn)

class PrescriptionRepository:
    """Persist and retrieve prescriptions via parameterized SQL.

    The repository deliberately exposes no arbitrary column-update method so
    that prescription rows stay immutable after creation. The only mutations
    are the status-transition methods.
    """

    def __init__(self, conn_or_db):
        # Support both sqlite3.Connection (Version A) and Database wrapper (Version B)
        if hasattr(conn_or_db, 'transaction'):
            self.db = conn_or_db
            self.conn = None
        else:
            self.conn = conn_or_db
            self.conn.row_factory = sqlite3.Row
            self.db = None

    def _get_conn(self):
        """Helper to get a connection regardless of initialization style."""
        if self.conn:
            return self.conn
        # For Version B's Database object, we use a context manager for transactions
        # but for simple reads we can use the execute method directly.
        return self.db

    # -- helpers ---------------------------------------------------------

    @staticmethod
    def _ensure_id(prescription: Prescription) -> None:
        if not prescription.id:
            prescription.id = str(uuid.uuid4())
        if not prescription.created_at:
            prescription.created_at = _now_iso()

    # -- reference tables -------------------------------------------------

    def add_patient(self, patient_id: str, name: str = "Test Patient") -> None:
        """Insert a patient reference row (for FK satisfaction in tests/usage)."""
        now = _now_iso()
        if self.db:
            with self.db.transaction() as conn:
                conn.execute(
                    "INSERT INTO patients (id, name, created_at) VALUES (?, ?, ?) ON CONFLICT(id) DO NOTHING",
                    (patient_id, name, now),
                )
        else:
            self.conn.execute(
                "INSERT OR IGNORE INTO patients (id, created_at) VALUES (?, ?)",
                (patient_id, now),
            )
            self.conn.commit()

    def add_doctor(self, doctor_id: str, name: str = "Doctor") -> None:
        """Insert a doctor reference row (for FK satisfaction in tests/usage)."""
        now = _now_iso()
        if self.db:
            with self.db.transaction() as conn:
                conn.execute(
                    "INSERT INTO doctors (id, name, created_at) VALUES (?, ?, ?) ON CONFLICT(id) DO NOTHING",
                    (doctor_id, name, now),
                )
        else:
            self.conn.execute(
                "INSERT OR IGNORE INTO doctors (id, name, created_at) VALUES (?, ?, ?)",
                (doctor_id, name, now),
            )
            self.conn.commit()

    def upsert_patient(self, patient_id: str, name: str = "Test Patient") -> None:
        self.add_patient(patient_id, name)

    def upsert_doctor(self, doctor_id: str, name: str = "Test Doctor") -> None:
        self.add_doctor(doctor_id, name)

    # -- write path ------------------------------------------------------

    def create(self, prescription: Prescription) -> Prescription:
        """Insert ``prescription`` and return it with id/created_at set."""
        self._ensure_id(prescription)
        self.upsert_patient(prescription.patient_id)
        self.upsert_doctor(prescription.doctor_id)

        params = (
            prescription.id,
            prescription.patient_id,
            prescription.doctor_id,
            prescription.medicine_name,
            float(prescription.dosage_amount),
            prescription.dosage_unit,
            prescription.frequency,
            prescription.start_date,
            prescription.end_date,
            prescription.status.value if isinstance(prescription.status, PrescriptionStatus) else prescription.status,
            prescription.created_at,
        )

        if self.db:
            with self.db.transaction() as conn:
                conn.execute(
                    """
                    INSERT INTO prescriptions
                        (id, patient_id, doctor_id, medicine_name, dosage_amount,
                         dosage_unit, frequency, start_date, end_date, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    params,
                )
        else:
            self.conn.execute(
                """
                INSERT INTO prescriptions
                    (id, patient_id, doctor_id, medicine_name, dosage_amount,
                     dosage_unit, frequency, start_date, end_date, status,
                     discontinue_reason, created_at, updated_at)
                VALUES
                    (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
                """,
                (*params, prescription.created_at),
            )
            self.conn.commit()
        return prescription

    # -- read path -------------------------------------------------------

    def get_by_id(self, prescription_id: str) -> Optional[Prescription]:
        """Return the prescription with ``prescription_id`` or ``None``."""
        if self.db:
            cursor = self.db.execute("SELECT * FROM prescriptions WHERE id = ?", (prescription_id,))
            row = cursor.fetchone()
        else:
            row = self.conn.execute("SELECT * FROM prescriptions WHERE id = ?", (prescription_id,)).fetchone()
        return Prescription.from_row(row) if row else None

    def list_by_patient(self, patient_id: str, status: Optional[PrescriptionStatus] = None) -> List[Prescription]:
        """Return a patient's full history ordered by ``start_date`` DESC."""
        if status is not None:
            query = "SELECT * FROM prescriptions WHERE patient_id = ? AND status = ? ORDER BY start_date DESC"
            params = (patient_id, status.value)
        else:
            query = "SELECT * FROM prescriptions WHERE patient_id = ? ORDER BY start_date DESC"
            params = (patient_id,)

        if self.db:
            cursor = self.db.execute(query, params)
            rows = cursor.fetchall()
        else:
            rows = self.conn.execute(query, params).fetchall()
        return [Prescription.from_row(r) for r in rows]

    # -- transition-only mutations --------------------------------------

    def _record_transition(
        self,
        prescription_id: str,
        from_status: PrescriptionStatus,
        to_status: PrescriptionStatus,
        reason: Optional[str],
    ) -> str:
        transitioned_at = _now_iso()
        # Support both 'transitioned_at' (A) and 'timestamp' (B) column names
        # We use the logic from B for the ID generation if StatusTransition exists
        try:
            tx_id = StatusTransition(
                prescription_id=prescription_id,
                from_status=from_status,
                to_status=to_status,
                reason=reason,
                timestamp=transitioned_at,
            ).id
        except NameError:
            tx_id = str(uuid.uuid4())

        sql = """
            INSERT INTO status_transitions
                (id, prescription_id, from_status, to_status, reason, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        # Fallback for Version A's 'transitioned_at' column
        if not self.db:
            sql = sql.replace("timestamp", "transitioned_at")

        if self.db:
            # This is usually called inside a transaction from complete/discontinue
            # but we handle it here for safety.
            with self.db.transaction() as conn:
                conn.execute(sql, (tx_id, prescription_id, from_status.value, to_status.value, reason, transitioned_at))
        else:
            self.conn.execute(sql, (tx_id, prescription_id, from_status.value, to_status.value, reason, transitioned_at))
            self.conn.commit()
        return transitioned_at

    def complete(self, prescription_id: str) -> Optional[Prescription]:
        rx = self.get_by_id(prescription_id)
        if rx is None:
            if self.db: raise PrescriptionNotFoundError(f"Prescription {prescription_id} not found")
            return None
        if rx.status != PrescriptionStatus.ACTIVE:
            raise ValueError(f"cannot complete a prescription that is {rx.status.value} (only active can transition)")
        
        now = _now_iso()
        if self.db:
            with self.db.transaction() as conn:
                conn.execute("UPDATE prescriptions SET status = ? WHERE id = ?", (PrescriptionStatus.COMPLETED.value, prescription_id))
        else:
            self.conn.execute("UPDATE prescriptions SET status = ?, updated_at = ? WHERE id = ?", (PrescriptionStatus.COMPLETED.value, now, prescription_id))
            self.conn.commit()
        
        self._record_transition(prescription_id, rx.status, PrescriptionStatus.COMPLETED, None)
        return self.get_by_id(prescription_id)

    def discontinue(self, prescription_id: str, reason: str) -> Optional[Prescription]:
        if not reason or not isinstance(reason, str) or reason.strip() == "":
            raise ValueError("a non-empty reason is required to discontinue a prescription")
        
        rx = self.get_by_id(prescription_id)
        if rx is None:
            if self.db: raise PrescriptionNotFoundError(f"Prescription {prescription_id} not found")
            return None
        if rx.status != PrescriptionStatus.ACTIVE:
            raise ValueError(f"cannot discontinue a prescription that is {rx.status.value} (only active can transition)")
        
        now = _now_iso()
        reason = reason.strip()
        if self.db:
            with self.db.transaction() as conn:
                conn.execute("UPDATE prescriptions SET status = ? WHERE id = ?", (PrescriptionStatus.DISCONTINUED.value, prescription_id))
        else:
            self.conn.execute("UPDATE prescriptions SET status = ?, discontinue_reason = ?, updated_at = ? WHERE id = ?", (PrescriptionStatus.DISCONTINUED.value, reason, now, prescription_id))
            self.conn.commit()
            
        self._record_transition(prescription_id, rx.status, PrescriptionStatus.DISCONTINUED, reason)
        return self.get_by_id(prescription_id)

    def list_transitions(self, prescription_id: str) -> List:
        """Return status transitions for a prescription."""
        sql = "SELECT * FROM status_transitions WHERE prescription_id = ? ORDER BY timestamp ASC"
        if not self.db:
            sql = sql.replace("timestamp", "transitioned_at")
            
        if self.db:
            cursor = self.db.execute(sql, (prescription_id,))
            rows = cursor.fetchall()
        else:
            rows = self.conn.execute(sql, (prescription_id,)).fetchall()

        # Try to return StatusTransition objects (Version B), fallback to dicts (Version A)
        results = []
        for row in rows:
            try:
                # Attempt to build StatusTransition object
                results.append(StatusTransition(
                    id=row["id"],
                    prescription_id=row["prescription_id"],
                    from_status=PrescriptionStatus(row["from_status"]),
                    to_status=PrescriptionStatus(row["to_status"]),
                    reason=row["reason"],
                    timestamp=row.get("timestamp") or row.get("transitioned_at"),
                ))
            except (NameError, ValueError, KeyError):
                results.append(dict(row))
        return results

    def create_prescription(self, data: dict) -> Prescription:
        from medication_tracker.validators import validate_prescription
        rx = validate_prescription(data)
        return self.create(rx)

    def log_dose(self, prescription_id: str, event: str, logged_at: str) -> dict:
        if event not in ("taken", "skipped"):
            raise ValueError("event must be 'taken' or 'skipped'")
        rx = self.get_by_id(prescription_id)
        if rx is None:
            raise ValueError("prescription not found")
        if rx.status != PrescriptionStatus.ACTIVE:
            raise ValueError(f"cannot log doses against a {rx.status.value} prescription")
        
        if self.db:
            with self.db.transaction() as conn:
                conn.execute("INSERT INTO dose_logs (id, prescription_id, event, logged_at) VALUES (?, ?, ?, ?)", (str(uuid.uuid4()), prescription_id, event, logged_at))
            row = self.db.execute("SELECT * FROM dose_logs WHERE prescription_id = ? AND logged_at = ? AND event = ? ORDER BY id DESC LIMIT 1", (prescription_id, logged_at, event)).fetchone()
        else:
            self.conn.execute("INSERT INTO dose_logs (id, prescription_id, event, logged_at) VALUES (?, ?, ?, ?)", (str(uuid.uuid4()), prescription_id, event, logged_at))
            self.conn.commit()
            row = self.conn.execute("SELECT * FROM dose_logs WHERE prescription_id = ? AND logged_at = ? AND event = ? ORDER BY id DESC LIMIT 1", (prescription_id, logged_at, event)).fetchone()
        return dict(row)

    def list_dose_logs(self, prescription_id: str) -> List[dict]:
        sql = "SELECT * FROM dose_logs WHERE prescription_id = ? ORDER BY logged_at ASC, id ASC"
        if self.db:
            rows = self.db.execute(sql, (prescription_id,)).fetchall()
        else:
            rows = self.conn.execute(sql, (prescription_id,)).fetchall()
        return [dict(r) for r in rows]
