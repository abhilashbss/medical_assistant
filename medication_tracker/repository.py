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

# ISO 8601 with an explicit timezone offset (Z or ±HH:MM).
# Rejects naive datetimes per the hard constraint in the REQ_SPEC.
_ISO8601_TZ = re.compile(
    r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}"
    r"(\.\d+)?"
    r"(Z|[+-]\d{2}:?\d{2})$"
)


class ValidationError(ValueError):
    """Raised when input fails application-level validation."""

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
    return datetime.utcnow().isoformat() + "+00:00"


# --------------------------------------------------------------------------- #
# Patients / doctors
# --------------------------------------------------------------------------- #

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


# --------------------------------------------------------------------------- #
# Prescriptions
# --------------------------------------------------------------------------- #

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