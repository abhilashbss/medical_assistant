"""Data-access layer for the prescription tracker.

This module exposes two complementary surfaces over the prescription tables:

1. **Module-level free functions** (``create_prescription``, ``get_prescription``,
   ``list_by_patient``, ``discontinue_prescription``, ``complete_prescription``,
   ``ensure_patient`` / ``ensure_doctor``) used by the FastAPI HTTP layer in
   :mod:`medication_tracker.app`. These operate on plain dicts and enforce the
   application-level invariants the schema cannot: ISO 8601-with-timezone
   datetime strings and the end_date-after-start_date rule for the API path
   (the schema CHECK is the backstop). They target the schema applied by the
   migration runner in :mod:`medication_tracker.migrations.runner`
   (``migrations/0001_init.sql``), which carries ``discontinue_reason`` and
   ``updated_at`` columns.

2. **The :class:`PrescriptionRepository` class** plus :func:`init_schema`, used
   by the validation/data-model layer and the repository/functional unit
   tests. The repository exposes no generic update method: prescription rows
   are immutable after creation, and the only permitted mutations are the
   dedicated status-transition methods (:meth:`PrescriptionRepository.complete`
   and :meth:`PrescriptionRepository.discontinue`), which also append a
   timestamped row to ``status_transitions``. Dose-adherence events are
   recorded append-only via :meth:`PrescriptionRepository.log_dose`.

All SQL uses parameter binding (``?`` / named) — no string interpolation.
"""

from __future__ import annotations

import re
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from medication_tracker.models import Prescription, PrescriptionStatus

# ISO 8601 with an explicit timezone offset (Z or ±HH:MM).
# Rejects naive datetimes per the hard constraint in the REQ_SPEC.
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


# --------------------------------------------------------------------------- #
# Schema bootstrap (class-based repository path)
# --------------------------------------------------------------------------- #

_SCHEMA_PATH_SQL = None  # set by tests via init_schema; otherwise migrations file used


def init_schema(conn: sqlite3.Connection) -> None:
    """Create the prescription-tracker schema on ``conn``.

    Idempotent — safe to call on a fresh or existing database. Used by the
    repository and by tests to set up an in-memory database.
    """
    conn.executescript(
        """
        PRAGMA foreign_keys = ON;

        CREATE TABLE IF NOT EXISTS patients (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS doctors (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS prescriptions (
            id TEXT PRIMARY KEY,
            patient_id TEXT NOT NULL,
            doctor_id TEXT NOT NULL,
            medicine_name TEXT NOT NULL CHECK (medicine_name <> ''),
            dosage_amount REAL NOT NULL CHECK (dosage_amount > 0),
            dosage_unit TEXT NOT NULL CHECK (dosage_unit <> ''),
            frequency TEXT NOT NULL CHECK (frequency <> ''),
            start_date TEXT NOT NULL,
            end_date TEXT,
            status TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'completed', 'discontinued')),
            created_at TEXT NOT NULL,
            FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE RESTRICT,
            FOREIGN KEY (doctor_id) REFERENCES doctors(id) ON DELETE RESTRICT,
            CHECK (end_date IS NULL OR end_date > start_date)
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_rx_active_unique
            ON prescriptions(patient_id, medicine_name)
            WHERE status = 'active';

        CREATE INDEX IF NOT EXISTS idx_rx_patient_status
            ON prescriptions(patient_id, status);

        CREATE INDEX IF NOT EXISTS idx_rx_patient_start
            ON prescriptions(patient_id, start_date DESC);

        CREATE TABLE IF NOT EXISTS status_transitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prescription_id TEXT NOT NULL,
            from_status TEXT NOT NULL
                CHECK (from_status IN ('active', 'completed', 'discontinued')),
            to_status TEXT NOT NULL
                CHECK (to_status IN ('active', 'completed', 'discontinued')),
            reason TEXT,
            transitioned_at TEXT NOT NULL,
            FOREIGN KEY (prescription_id) REFERENCES prescriptions(id) ON DELETE RESTRICT
        );

        CREATE INDEX IF NOT EXISTS idx_transitions_rx
            ON status_transitions(prescription_id, transitioned_at);

        CREATE TABLE IF NOT EXISTS dose_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prescription_id TEXT NOT NULL,
            event TEXT NOT NULL CHECK (event IN ('taken', 'skipped')),
            logged_at TEXT NOT NULL,
            FOREIGN KEY (prescription_id) REFERENCES prescriptions(id) ON DELETE RESTRICT
        );

        CREATE INDEX IF NOT EXISTS idx_dose_logs_rx_time
            ON dose_logs(prescription_id, logged_at);
        """
    )
    conn.commit()


# --------------------------------------------------------------------------- #
# Patients / doctors (free-function API path)
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
# Prescriptions (free-function API path)
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


# --------------------------------------------------------------------------- #
# Class-based repository (validation / data-model path)
# --------------------------------------------------------------------------- #

class PrescriptionRepository:
    """Persist and retrieve prescriptions via parameterized SQL.

    The repository deliberately exposes no arbitrary column-update method so
    that prescription rows stay immutable after creation. The only mutations
    are the status-transition methods.
    """

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row

    # -- helpers ---------------------------------------------------------

    @staticmethod
    def _ensure_id(prescription: Prescription) -> None:
        if not prescription.id:
            prescription.id = str(uuid.uuid4())
        if not prescription.created_at:
            prescription.created_at = _now_iso()

    # -- write path ------------------------------------------------------

    def create(self, prescription: Prescription) -> Prescription:
        """Insert ``prescription`` and return it with id/created_at set.

        Uses a parameterized INSERT. Raises ``sqlite3.IntegrityError`` on a
        CHECK / foreign-key / unique-constraint violation (e.g. a second active
        prescription for the same medicine and patient).
        """
        self._ensure_id(prescription)
        self.conn.execute(
            """
            INSERT INTO prescriptions
                (id, patient_id, doctor_id, medicine_name, dosage_amount,
                 dosage_unit, frequency, start_date, end_date, status, created_at)
            VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                prescription.id,
                prescription.patient_id,
                prescription.doctor_id,
                prescription.medicine_name,
                float(prescription.dosage_amount),
                prescription.dosage_unit,
                prescription.frequency,
                prescription.start_date,
                prescription.end_date,
                prescription.status.value
                if isinstance(prescription.status, PrescriptionStatus)
                else prescription.status,
                prescription.created_at,
            ),
        )
        self.conn.commit()
        return prescription

    def add_patient(self, patient_id: str, name: str = "Patient") -> None:
        """Insert a patient reference row (for FK satisfaction in tests/usage)."""
        self.conn.execute(
            "INSERT OR IGNORE INTO patients (id, name, created_at) VALUES (?, ?, ?)",
            (patient_id, name, _now_iso()),
        )
        self.conn.commit()

    def add_doctor(self, doctor_id: str, name: str = "Doctor") -> None:
        """Insert a doctor reference row (for FK satisfaction in tests/usage)."""
        self.conn.execute(
            "INSERT OR IGNORE INTO doctors (id, name, created_at) VALUES (?, ?, ?)",
            (doctor_id, name, _now_iso()),
        )
        self.conn.commit()

    # -- read path -------------------------------------------------------

    def get_by_id(self, prescription_id: str) -> Optional[Prescription]:
        """Return the prescription with ``prescription_id`` or ``None``."""
        row = self.conn.execute(
            "SELECT * FROM prescriptions WHERE id = ?",
            (prescription_id,),
        ).fetchone()
        return Prescription.from_row(row) if row else None

    def list_by_patient(self, patient_id: str) -> List[Prescription]:
        """Return a patient's full history ordered by ``start_date`` DESC."""
        rows = self.conn.execute(
            "SELECT * FROM prescriptions WHERE patient_id = ? ORDER BY start_date DESC",
            (patient_id,),
        ).fetchall()
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
        self.conn.execute(
            """
            INSERT INTO status_transitions
                (prescription_id, from_status, to_status, reason, transitioned_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                prescription_id,
                from_status.value,
                to_status.value,
                reason,
                transitioned_at,
            ),
        )
        return transitioned_at

    def complete(self, prescription_id: str) -> Optional[Prescription]:
        """Transition a prescription from active to completed.

        Returns the updated prescription, or ``None`` if not found. Raises
        ``sqlite3.IntegrityError`` if the prescription is not currently active
        (the partial unique index moves with it).
        """
        rx = self.get_by_id(prescription_id)
        if rx is None:
            return None
        if rx.status != PrescriptionStatus.ACTIVE:
            raise ValueError(
                f"cannot complete a prescription that is {rx.status.value} (only active can transition)"
            )
        self.conn.execute(
            "UPDATE prescriptions SET status = ? WHERE id = ?",
            (PrescriptionStatus.COMPLETED.value, prescription_id),
        )
        self._record_transition(prescription_id, rx.status, PrescriptionStatus.COMPLETED, None)
        self.conn.commit()
        return self.get_by_id(prescription_id)

    def discontinue(self, prescription_id: str, reason: str) -> Optional[Prescription]:
        """Transition a prescription from active to discontinued.

        ``reason`` is mandatory and must be a non-empty string — this is the
        audit escape hatch that preserves the historical record instead of
        allowing edits or deletion.
        """
        if not reason or not isinstance(reason, str) or reason.strip() == "":
            raise ValueError("a non-empty reason is required to discontinue a prescription")
        rx = self.get_by_id(prescription_id)
        if rx is None:
            return None
        if rx.status != PrescriptionStatus.ACTIVE:
            raise ValueError(
                f"cannot discontinue a prescription that is {rx.status.value} (only active can transition)"
            )
        self.conn.execute(
            "UPDATE prescriptions SET status = ? WHERE id = ?",
            (PrescriptionStatus.DISCONTINUED.value, prescription_id),
        )
        self._record_transition(prescription_id, rx.status, PrescriptionStatus.DISCONTINUED, reason)
        self.conn.commit()
        return self.get_by_id(prescription_id)

    def list_transitions(self, prescription_id: str) -> List[dict]:
        """Return timestamped status transitions for a prescription (audit trail)."""
        rows = self.conn.execute(
            "SELECT * FROM status_transitions WHERE prescription_id = ? ORDER BY transitioned_at ASC",
            (prescription_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # -- convenience: validate + persist in one step --------------------

    def create_prescription(self, data: dict) -> Prescription:
        """Validate ``data`` and persist the resulting prescription.

        A thin convenience wrapper so callers don't need to import the
        validator separately. Raises :class:`ValidationError` on invalid input
        and ``sqlite3.IntegrityError`` on constraint violations.
        """
        from medication_tracker.validators import validate_prescription

        rx = validate_prescription(data)
        return self.create(rx)

    # -- dose adherence logging (append-only) ---------------------------

    def log_dose(self, prescription_id: str, event: str, logged_at: str) -> dict:
        """Append a dose-adherence event for ``prescription_id``.

        ``event`` must be ``"taken"`` or ``"skipped"``; ``logged_at`` must be
        an ISO 8601 datetime string with a timezone. Logging against a
        discontinued or completed prescription is rejected so adherence history
        only reflects active prescriptions.
        """
        if event not in ("taken", "skipped"):
            raise ValueError("event must be 'taken' or 'skipped'")
        rx = self.get_by_id(prescription_id)
        if rx is None:
            raise ValueError("prescription not found")
        if rx.status != PrescriptionStatus.ACTIVE:
            raise ValueError(f"cannot log doses against a {rx.status.value} prescription")
        self.conn.execute(
            "INSERT INTO dose_logs (prescription_id, event, logged_at) VALUES (?, ?, ?)",
            (prescription_id, event, logged_at),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT * FROM dose_logs WHERE prescription_id = ? AND logged_at = ? AND event = ? "
            "ORDER BY id DESC LIMIT 1",
            (prescription_id, logged_at, event),
        ).fetchone()
        return dict(row)

    def list_dose_logs(self, prescription_id: str) -> List[dict]:
        """Return dose-adherence events for a prescription ordered by time ascending."""
        rows = self.conn.execute(
            "SELECT * FROM dose_logs WHERE prescription_id = ? ORDER BY logged_at ASC, id ASC",
            (prescription_id,),
        ).fetchall()
        return [dict(r) for r in rows]