"""Data-access layer for the prescription tracker.

This module hosts a single :class:`PrescriptionRepository` that supports two
cooperating stacks:

* The **Flask/service stack** (``database.Database`` + dataclass models) uses
  the model-returning methods (:meth:`create`, :meth:`get_by_id`,
  :meth:`get_by_patient`, :meth:`complete`/:meth:`discontinue` with UUIDs,
  :meth:`log_dose`, :meth:`get_transitions`). These run through
  ``Database.transaction``/``Database.execute`` and return ``Prescription`` /
  ``DoseLog`` / ``StatusTransition`` instances.

* The **FastAPI/dict stack** (raw ``sqlite3.Connection`` + ``*Create`` models)
  uses the dict-returning methods (:meth:`create_prescription`,
  :meth:`get_prescription`, :meth:`list_by_patient`,
  :meth:`list_history_by_patient`, :meth:`list_by_patient_and_status`,
  :meth:`transition_status`, :meth:`add_dose_log`,
  :meth:`explain_query_plan`). These use parameterized SQL and return plain
  dicts.

All queries use parameterized SQL — no string interpolation — to prevent SQL
injection. Prescription rows are immutable after creation; only explicit
status transitions (complete / discontinue) mutate status, and those insert
timestamped audit rows into ``status_transitions``.
"""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional
from uuid import UUID, uuid4

from .database import Database
from .models import (
    DoseLog,
    DoseLogCreate,
    DoseStatus,
    Prescription,
    PrescriptionCreate,
    PrescriptionStatus,
    StatusTransition,
    ValidationError,
)


def _now_iso() -> str:
    """Current UTC time as an ISO 8601 string with timezone."""
    return datetime.now(timezone.utc).isoformat()


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


class NotFoundError(Exception):
    """Raised by dict-stack methods when a prescription is not found."""
    pass


class PrescriptionRepository:
    """Repository for prescription CRUD and lifecycle operations.

    Accepts either a :class:`~prescription_tracker.database.Database` (Flask
    stack) or a raw ``sqlite3.Connection`` (FastAPI stack). The connection
    used by the dict-stack methods is exposed as ``self.conn`` so callers and
    tests that hold the connection can continue to reach it.
    """

    def __init__(self, database_or_conn):
        if isinstance(database_or_conn, Database):
            self.db = database_or_conn
            self.conn = database_or_conn.connect()
        else:
            # Assume a raw sqlite3.Connection (row factory already set).
            self.db = None
            self.conn = database_or_conn

    # ------------------------------------------------------------------
    # Reference data helpers
    # ------------------------------------------------------------------
    def ensure_patient(self, patient_id: UUID, name: str = "Patient") -> None:
        """Insert a patient row if it does not already exist."""
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO patients (id, name, created_at) VALUES (?, ?, ?)",
                (str(patient_id), name, _now_iso()),
            )

    def ensure_doctor(self, doctor_id: UUID, name: str = "Doctor") -> None:
        """Insert a doctor row if it does not already exist."""
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO doctors (id, name, created_at) VALUES (?, ?, ?)",
                (str(doctor_id), name, _now_iso()),
            )

    # ------------------------------------------------------------------
    # Create / read (model stack)
    # ------------------------------------------------------------------
    def create(self, prescription: Prescription) -> Prescription:
        """Persist a new prescription row (model stack).

        The caller is expected to have validated the model. Reference rows for
        the patient and doctor are ensured first so foreign keys resolve.
        """
        self.ensure_patient(prescription.patient_id)
        self.ensure_doctor(prescription.doctor_id)

        now = _now_iso()
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO prescriptions
                    (id, patient_id, doctor_id, medicine_name, dosage_amount, dosage_unit,
                     frequency, start_date, end_date, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(prescription.id),
                    str(prescription.patient_id),
                    str(prescription.doctor_id),
                    prescription.medicine_name,
                    prescription.dosage_amount,
                    prescription.dosage_unit,
                    prescription.frequency,
                    prescription.start_date.isoformat(),
                    prescription.end_date.isoformat() if prescription.end_date else None,
                    prescription.status.value,
                    now,
                    now,
                ),
            )

        prescription.created_at = datetime.fromisoformat(now)
        prescription.updated_at = datetime.fromisoformat(now)
        return prescription

    def get_by_id(self, prescription_id) -> Optional[Prescription]:
        """Return a single prescription by id, or None (model stack)."""
        cursor = self.db.execute(
            "SELECT * FROM prescriptions WHERE id = ?",
            (str(prescription_id),),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return self._row_to_prescription(row)

    def get_by_patient(self, patient_id) -> dict:
        """Return a patient's full prescription history (model stack).

        Results are sorted by start_date descending. Active prescriptions are
        separated from historical (completed/discontinued) entries.
        """
        cursor = self.db.execute(
            "SELECT * FROM prescriptions WHERE patient_id = ? ORDER BY start_date DESC",
            (str(patient_id),),
        )
        active: List[Prescription] = []
        historical: List[Prescription] = []
        for row in cursor.fetchall():
            prescription = self._row_to_prescription(row)
            if prescription.status == PrescriptionStatus.ACTIVE:
                active.append(prescription)
            else:
                historical.append(prescription)
        return {"active": active, "historical": historical}

    # ------------------------------------------------------------------
    # Status transitions (model stack) — the only permitted mutations
    # ------------------------------------------------------------------
    def complete(self, prescription_id):
        """Transition an active prescription to completed.

        Dispatches by stack: model stack (built from a ``Database``) returns a
        ``Prescription``; dict stack (built from a raw connection) returns a
        dict. Raises ``ValueError`` (model) or ``ValidationError``/
        ``NotFoundError`` (dict) if the prescription is missing or not active.
        """
        if self.db is None:
            return self.complete_dict(str(prescription_id))
        return self._transition(prescription_id, PrescriptionStatus.COMPLETED, reason=None)

    def discontinue(self, prescription_id, reason: str):
        """Transition an active prescription to discontinued with a mandatory
        reason.

        Dispatches by stack: model stack (built from a ``Database``) returns a
        ``Prescription``; dict stack (built from a raw connection) returns a
        dict. Raises ``ValueError`` (model) or ``ValidationError``/
        ``NotFoundError`` (dict) if the reason is empty or the prescription is
        missing/not active.
        """
        if self.db is None:
            return self.discontinue_dict(str(prescription_id), reason)
        if not reason or not isinstance(reason, str) or not reason.strip():
            raise ValueError("a non-empty reason is required to discontinue a prescription")
        return self._transition(prescription_id, PrescriptionStatus.DISCONTINUED, reason=reason)

    def _transition(
        self,
        prescription_id,
        to_status: PrescriptionStatus,
        reason: Optional[str],
    ) -> Prescription:
        """Perform a status transition atomically (model stack).

        Inserts a timestamped status_transitions audit row and updates the
        prescription status in one transaction. Non-transition mutations are
        rejected because this is the only mutation path exposed.
        """
        prescription = self.get_by_id(prescription_id)
        if prescription is None:
            raise ValueError(f"prescription {prescription_id} not found")

        if not PrescriptionStatus.transition_allowed(prescription.status, to_status):
            raise ValueError(
                f"cannot transition prescription from '{prescription.status.value}' to '{to_status.value}': "
                "only active prescriptions may transition to completed or discontinued"
            )

        transition = StatusTransition(
            prescription_id=prescription_id if isinstance(prescription_id, UUID) else UUID(str(prescription_id)),
            from_status=prescription.status,
            to_status=to_status,
            reason=reason,
        )
        now = _now_iso()

        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO status_transitions
                    (id, prescription_id, from_status, to_status, reason, transitioned_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(transition.id),
                    str(prescription_id),
                    prescription.status.value,
                    to_status.value,
                    reason,
                    now,
                ),
            )
            conn.execute(
                "UPDATE prescriptions SET status = ?, updated_at = ? WHERE id = ?",
                (to_status.value, now, str(prescription_id)),
            )

        prescription.status = to_status
        prescription.updated_at = datetime.fromisoformat(now)
        transition.transitioned_at = datetime.fromisoformat(now)
        return prescription

    def get_transitions(self, prescription_id) -> List[StatusTransition]:
        """Return the audit trail of status transitions for a prescription
        (model stack)."""
        cursor = self.db.execute(
            "SELECT * FROM status_transitions WHERE prescription_id = ? ORDER BY transitioned_at ASC",
            (str(prescription_id),),
        )
        transitions: List[StatusTransition] = []
        for row in cursor.fetchall():
            transitions.append(
                StatusTransition(
                    id=UUID(row["id"]) if isinstance(row["id"], str) else uuid4(),
                    prescription_id=UUID(row["prescription_id"]),
                    from_status=PrescriptionStatus(row["from_status"]) if row["from_status"] else None,
                    to_status=PrescriptionStatus(row["to_status"]) if row["to_status"] else None,
                    reason=row["reason"],
                    transitioned_at=datetime.fromisoformat(row["transitioned_at"]) if row["transitioned_at"] else None,
                )
            )
        return transitions

    # ------------------------------------------------------------------
    # Dose logs (model stack)
    # ------------------------------------------------------------------
    def log_dose(self, dose: DoseLog) -> DoseLog:
        """Append a dose log entry for a prescription (model stack)."""
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO dose_logs (id, prescription_id, timestamp, event, taken_at, status)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(dose.id),
                    str(dose.prescription_id),
                    dose.taken_at.isoformat(),
                    dose.status.value,
                    dose.taken_at.isoformat(),
                    dose.status.value,
                ),
            )
        return dose

    def get_dose_logs_model(self, prescription_id) -> List[DoseLog]:
        """Return dose logs for a prescription ordered by taken_at ascending
        (model stack)."""
        cursor = self.db.execute(
            "SELECT * FROM dose_logs WHERE prescription_id = ? ORDER BY timestamp ASC",
            (str(prescription_id),),
        )
        logs: List[DoseLog] = []
        for row in cursor.fetchall():
            logs.append(
                DoseLog(
                    id=UUID(row["id"]) if isinstance(row["id"], str) else uuid4(),
                    prescription_id=UUID(row["prescription_id"]),
                    taken_at=datetime.fromisoformat(row["timestamp"]),
                    status=DoseStatus(row["event"]) if row["event"] else DoseStatus.TAKEN,
                )
            )
        return logs

    # ------------------------------------------------------------------
    # Row mapping (model stack)
    # ------------------------------------------------------------------
    def _row_to_prescription(self, row) -> Prescription:
        """Convert a sqlite3.Row into a Prescription."""
        status_value = row["status"]
        try:
            status = PrescriptionStatus(status_value)
        except ValueError:
            status = PrescriptionStatus.ACTIVE

        return Prescription(
            id=UUID(row["id"]),
            patient_id=UUID(row["patient_id"]),
            doctor_id=UUID(row["doctor_id"]),
            medicine_name=row["medicine_name"],
            dosage_amount=row["dosage_amount"],
            dosage_unit=row["dosage_unit"],
            frequency=row["frequency"],
            start_date=datetime.fromisoformat(row["start_date"]),
            end_date=datetime.fromisoformat(row["end_date"]) if row["end_date"] else None,
            status=status,
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
            updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None,
        )

    # ------------------------------------------------------------------
    # Create / read (dict stack)
    # ------------------------------------------------------------------
    def create_prescription(self, data: PrescriptionCreate) -> dict[str, Any]:
        data.validate()
        rx_id = _new_id()
        self.conn.execute(
            """
            INSERT INTO prescriptions
                (id, patient_id, doctor_id, medicine_name,
                 dosage_amount, dosage_unit, frequency,
                 start_date, end_date, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
            """,
            (
                rx_id,
                data.patient_id,
                data.doctor_id,
                data.medicine_name,
                data.dosage_amount,
                data.dosage_unit,
                data.frequency,
                data.start_date,
                data.end_date,
            ),
        )
        self.conn.commit()
        return self.get_prescription(rx_id)

    def get_prescription(self, rx_id: str) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT * FROM prescriptions WHERE id = ?", (rx_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"prescription {rx_id} not found")
        return dict(row)

    def list_by_patient(self, patient_id: str) -> dict[str, list[dict[str, Any]]]:
        """Return active and historical prescriptions, sorted by start_date DESC."""
        rows = self.conn.execute(
            """
            SELECT * FROM prescriptions
            WHERE patient_id = ?
            ORDER BY start_date DESC
            """,
            (patient_id,),
        ).fetchall()
        active = [dict(r) for r in rows if r["status"] == "active"]
        historical = [dict(r) for r in rows if r["status"] != "active"]
        return {"active": active, "historical": historical}

    def list_history_by_patient(self, patient_id: str) -> list[dict[str, Any]]:
        """Full prescription history sorted by start_date DESC."""
        rows = self.conn.execute(
            """
            SELECT * FROM prescriptions
            WHERE patient_id = ?
            ORDER BY start_date DESC
            """,
            (patient_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def list_by_patient_and_status(
        self, patient_id: str, status: str
    ) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT * FROM prescriptions
            WHERE patient_id = ? AND status = ?
            ORDER BY start_date DESC
            """,
            (patient_id, status),
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Transitions (dict stack)
    # ------------------------------------------------------------------
    def transition_status(
        self, rx_id: str, transition: StatusTransition
    ) -> dict[str, Any]:
        transition.validate()
        row = self.conn.execute(
            "SELECT status FROM prescriptions WHERE id = ?", (rx_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"prescription {rx_id} not found")
        from_status = row["status"]
        to_status = transition.to_status

        if from_status == to_status:
            raise ValidationError(
                {"to_status": f"prescription already {to_status}"}
            )
        if from_status != "active":
            raise ValidationError(
                {"to_status": f"cannot transition from {from_status} to {to_status}"}
            )

        self.conn.execute("BEGIN")
        try:
            self.conn.execute(
                "UPDATE prescriptions SET status = ? WHERE id = ?",
                (to_status, rx_id),
            )
            self.conn.execute(
                """
                INSERT INTO status_transitions
                    (id, prescription_id, from_status, to_status, reason)
                VALUES (?, ?, ?, ?, ?)
                """,
                (_new_id(), rx_id, from_status, to_status, transition.reason),
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        return self.get_prescription(rx_id)

    def complete_dict(self, rx_id: str) -> dict[str, Any]:
        return self.transition_status(rx_id, StatusTransition(to_status="completed"))

    def discontinue_dict(self, rx_id: str, reason: str) -> dict[str, Any]:
        return self.transition_status(
            rx_id, StatusTransition(to_status="discontinued", reason=reason)
        )

    # ------------------------------------------------------------------
    # Dose logs (dict stack)
    # ------------------------------------------------------------------
    def add_dose_log(self, data: DoseLogCreate) -> dict[str, Any]:
        data.validate()
        rx = self.conn.execute(
            "SELECT status FROM prescriptions WHERE id = ?",
            (data.prescription_id,),
        ).fetchone()
        if rx is None:
            raise NotFoundError(f"prescription {data.prescription_id} not found")
        if rx["status"] != "active":
            raise ValidationError(
                {"prescription_id": "cannot log doses for a non-active prescription"}
            )
        log_id = _new_id()
        self.conn.execute(
            """
            INSERT INTO dose_logs (id, prescription_id, event, timestamp, notes)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                log_id,
                data.prescription_id,
                data.event,
                data.timestamp,
                data.notes,
            ),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT * FROM dose_logs WHERE id = ?", (log_id,)
        ).fetchone()
        return dict(row)

    def get_dose_logs(
        self,
        prescription_id,
        start_ts: Optional[str] = None,
        end_ts: Optional[str] = None,
    ):
        """Dose logs for a prescription ordered by time ascending.

        Dispatches by stack: when the repository was built from a
        :class:`Database` (model stack) this returns ``DoseLog`` instances;
        when built from a raw connection (dict stack) it returns plain dicts,
        optionally filtered by an ISO 8601 ``start_ts``/``end_ts`` range.
        """
        if self.db is not None and start_ts is None and end_ts is None:
            return self.get_dose_logs_model(prescription_id)
        rx_id = str(prescription_id)
        if start_ts and end_ts:
            rows = self.conn.execute(
                """
                SELECT * FROM dose_logs
                WHERE prescription_id = ? AND timestamp >= ? AND timestamp <= ?
                ORDER BY timestamp ASC
                """,
                (rx_id, start_ts, end_ts),
            ).fetchall()
        elif start_ts:
            rows = self.conn.execute(
                """
                SELECT * FROM dose_logs
                WHERE prescription_id = ? AND timestamp >= ?
                ORDER BY timestamp ASC
                """,
                (rx_id, start_ts),
            ).fetchall()
        elif end_ts:
            rows = self.conn.execute(
                """
                SELECT * FROM dose_logs
                WHERE prescription_id = ? AND timestamp <= ?
                ORDER BY timestamp ASC
                """,
                (rx_id, end_ts),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """
                SELECT * FROM dose_logs
                WHERE prescription_id = ?
                ORDER BY timestamp ASC
                """,
                (rx_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Query plan
    # ------------------------------------------------------------------
    def explain_query_plan(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        """Return EXPLAIN QUERY PLAN rows for a query."""
        rows = self.conn.execute("EXPLAIN QUERY PLAN " + sql, params).fetchall()
        return [dict(r) for r in rows]