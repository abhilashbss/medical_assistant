"""Repository for prescription persistence and lifecycle transitions."""

from __future__ import annotations

from datetime import datetime, timezone

from typing import List, Optional

from uuid import UUID, uuid4

from .database import Database

from .models import (
    DoseLog,
    DoseStatus,
    Prescription,
    PrescriptionStatus,
    StatusTransition,
)

import sqlite3

import uuid

from typing import Any, Optional

from .models import (
    DoseLogCreate,
    PrescriptionCreate,
    StatusTransition,
    ValidationError,
)



def _now_iso() -> str:
    """Current UTC time as an ISO 8601 string with timezone."""
    return datetime.now(timezone.utc).isoformat()

class PrescriptionRepository:
    """Repository for prescription CRUD and lifecycle operations."""

    def __init__(self, database: Database):
        self.db = database
        # Compatibility for Version B which expects self.conn
        self.conn = database

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
    # Create / read
    # ------------------------------------------------------------------
    def create(self, prescription: Prescription) -> Prescription:
        """Persist a new prescription row."""
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

    def create_prescription(self, data: PrescriptionCreate) -> dict[str, Any]:
        """Version B compatibility: Create prescription from DTO."""
        data.validate()
        rx_id = _new_id()
        # Map DTO to Model for consistency
        prescription = Prescription(
            id=UUID(rx_id),
            patient_id=UUID(data.patient_id),
            doctor_id=UUID(data.doctor_id),
            medicine_name=data.medicine_name,
            dosage_amount=data.dosage_amount,
            dosage_unit=data.dosage_unit,
            frequency=data.frequency,
            start_date=datetime.fromisoformat(data.start_date),
            end_date=datetime.fromisoformat(data.end_date) if data.end_date else None,
            status=PrescriptionStatus.ACTIVE
        )
        self.create(prescription)
        return self.get_prescription(rx_id)

    def get_by_id(self, prescription_id: UUID) -> Optional[Prescription]:
        """Return a single prescription by id, or None."""
        cursor = self.db.execute(
            "SELECT * FROM prescriptions WHERE id = ?",
            (str(prescription_id),),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return self._row_to_prescription(row)

    def get_prescription(self, rx_id: str) -> dict[str, Any]:
        """Version B compatibility: Return prescription as dict or raise NotFoundError."""
        prescription = self.get_by_id(UUID(rx_id))
        if prescription is None:
            raise NotFoundError(f"prescription {rx_id} not found")
        
        # Return as dict to match Version B's expected return type
        cursor = self.db.execute("SELECT * FROM prescriptions WHERE id = ?", (rx_id,))
        return dict(cursor.fetchone())

    def get_by_patient(self, patient_id: UUID) -> dict:
        """Return a patient's full prescription history."""
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

    def list_by_patient(self, patient_id: str) -> dict[str, list[dict[str, Any]]]:
        """Version B compatibility: Return active and historical as dicts."""
        cursor = self.db.execute(
            "SELECT * FROM prescriptions WHERE patient_id = ? ORDER BY start_date DESC",
            (patient_id,),
        )
        rows = cursor.fetchall()
        active = [dict(r) for r in rows if r["status"] == "active"]
        historical = [dict(r) for r in rows if r["status"] != "active"]
        return {"active": active, "historical": historical}

    def list_history_by_patient(self, patient_id: str) -> list[dict[str, Any]]:
        """Version B compatibility: Full history as dicts."""
        cursor = self.db.execute(
            "SELECT * FROM prescriptions WHERE patient_id = ? ORDER BY start_date DESC",
            (patient_id,),
        )
        return [dict(r) for r in cursor.fetchall()]

    def list_by_patient_and_status(self, patient_id: str, status: str) -> list[dict[str, Any]]:
        """Version B compatibility: Filtered history as dicts."""
        cursor = self.db.execute(
            "SELECT * FROM prescriptions WHERE patient_id = ? AND status = ? ORDER BY start_date DESC",
            (patient_id, status),
        )
        return [dict(r) for r in cursor.fetchall()]

    # ------------------------------------------------------------------
    # Status transitions
    # ------------------------------------------------------------------
    def complete(self, prescription_id: UUID | str) -> Prescription | dict[str, Any]:
        """Transition an active prescription to completed."""
        pid = UUID(prescription_id) if isinstance(prescription_id, str) else prescription_id
        res = self._transition(pid, PrescriptionStatus.COMPLETED, reason=None)
        return dict(self.db.execute("SELECT * FROM prescriptions WHERE id = ?", (str(pid),)).fetchone()) if isinstance(prescription_id, str) else res

    def discontinue(self, prescription_id: UUID | str, reason: str) -> Prescription | dict[str, Any]:
        """Transition an active prescription to discontinued with a mandatory reason."""
        if not reason or not isinstance(reason, str) or not reason.strip():
            raise ValueError("a non-empty reason is required to discontinue a prescription")
        pid = UUID(prescription_id) if isinstance(prescription_id, str) else prescription_id
        res = self._transition(pid, PrescriptionStatus.DISCONTINUED, reason=reason)
        return dict(self.db.execute("SELECT * FROM prescriptions WHERE id = ?", (str(pid),)).fetchone()) if isinstance(prescription_id, str) else res

    def transition_status(self, rx_id: str, transition: StatusTransition) -> dict[str, Any]:
        """Version B compatibility: Transition status using StatusTransition object."""
        transition.validate()
        pid = UUID(rx_id)
        # Use the internal _transition logic to ensure audit logs and atomicity
        self._transition(pid, transition.to_status, reason=transition.reason)
        return self.get_prescription(rx_id)

    def _transition(self, prescription_id: UUID, to_status: PrescriptionStatus, reason: Optional[str]) -> Prescription:
        """Perform a status transition atomically."""
        prescription = self.get_by_id(prescription_id)
        if prescription is None:
            raise ValueError(f"prescription {prescription_id} not found")

        if not PrescriptionStatus.transition_allowed(prescription.status, to_status):
            raise ValueError(
                f"cannot transition prescription from '{prescription.status.value}' to '{to_status.value}': "
                "only active prescriptions may transition to completed or discontinued"
            )

        transition = StatusTransition(
            prescription_id=prescription_id,
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
                (str(transition.id), str(prescription_id), prescription.status.value, to_status.value, reason, now),
            )
            conn.execute(
                "UPDATE prescriptions SET status = ?, updated_at = ? WHERE id = ?",
                (to_status.value, now, str(prescription_id)),
            )

        prescription.status = to_status
        prescription.updated_at = datetime.fromisoformat(now)
        return prescription

    def get_transitions(self, prescription_id: UUID) -> List[StatusTransition]:
        """Return the audit trail of status transitions for a prescription."""
        cursor = self.db.execute(
            "SELECT * FROM status_transitions WHERE prescription_id = ? ORDER BY transitioned_at ASC",
            (str(prescription_id),),
        )
        transitions: List[StatusTransition] = []
        for row in cursor.fetchall():
            transitions.append(
                StatusTransition(
                    id=UUID(row["id"]),
                    prescription_id=UUID(row["prescription_id"]),
                    from_status=PrescriptionStatus(row["from_status"]) if row["from_status"] else None,
                    to_status=PrescriptionStatus(row["to_status"]) if row["to_status"] else None,
                    reason=row["reason"],
                    transitioned_at=datetime.fromisoformat(row["transitioned_at"]) if row["transitioned_at"] else None,
                )
            )
        return transitions

    # ------------------------------------------------------------------
    # Dose logs
    # ------------------------------------------------------------------
    def log_dose(self, dose: DoseLog) -> DoseLog:
        """Append a dose log entry for a prescription."""
        now = _now_iso()
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO dose_logs (id, prescription_id, taken_at, status) VALUES (?, ?, ?, ?)",
                (str(dose.id), str(dose.prescription_id), dose.taken_at.isoformat(), dose.status.value),
            )
        return dose

    def add_dose_log(self, data: DoseLogCreate) -> dict[str, Any]:
        """Version B compatibility: Log dose from DTO."""
        data.validate()
        rx = self.db.execute("SELECT status FROM prescriptions WHERE id = ?", (data.prescription_id,)).fetchone()
        if rx is None:
            raise NotFoundError(f"prescription {data.prescription_id} not found")
        if rx["status"] != "active":
            raise ValidationError({"prescription_id": "cannot log doses for a non-active prescription"})
        
        # Map DTO to Model
        dose = DoseLog(
            id=UUID(_new_id()),
            prescription_id=UUID(data.prescription_id),
            taken_at=datetime.fromisoformat(data.timestamp),
            status=DoseStatus.TAKEN # Defaulting to TAKEN as per Version A/B logic
        )
        self.log_dose(dose)
        
        cursor = self.db.execute("SELECT * FROM dose_logs WHERE prescription_id = ? ORDER BY taken_at DESC LIMIT 1", (data.prescription_id,))
        return dict(cursor.fetchone())

    def get_dose_logs(self, prescription_id: UUID | str, start_ts: Optional[str] = None, end_ts: Optional[str] = None) -> List[DoseLog] | list[dict[str, Any]]:
        """Return dose logs for a prescription. Supports both Model list and dict list."""
        pid = str(prescription_id)
        sql = "SELECT * FROM dose_logs WHERE prescription_id = ?"
        params = [pid]

        if start_ts and end_ts:
            sql += " AND timestamp >= ? AND timestamp <= ?"
            params.extend([start_ts, end_ts])
        elif start_ts:
            sql += " AND timestamp >= ?"
            params.append(start_ts)
        elif end_ts:
            sql += " AND timestamp <= ?"
            params.append(end_ts)
        
        sql += " ORDER BY timestamp ASC"
        cursor = self.db.execute(sql, tuple(params))
        rows = cursor.fetchall()

        if isinstance(prescription_id, str):
            return [dict(r) for r in rows]
        
        logs: List[DoseLog] = []
        for row in rows:
            logs.append(
                DoseLog(
                    id=UUID(row["id"]),
                    prescription_id=UUID(row["prescription_id"]),
                    taken_at=datetime.fromisoformat(row["taken_at"] if "taken_at" in row else row["timestamp"]),
                    status=DoseStatus(row["status"] if "status" in row else "taken"),
                )
            )
        return logs

    # ------------------------------------------------------------------
    # Query plan (Version B)
    # ------------------------------------------------------------------
    def explain_query_plan(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        rows = self.db.execute("EXPLAIN QUERY PLAN " + sql, params).fetchall()
        return [dict(r) for r in rows]

    def _plan_detail(self, sql: str, params: tuple = ()) -> str:
        return " ".join(r["detail"] for r in self.explain_query_plan(sql, params))

    def plan_history_by_patient(self, patient_id: str) -> str:
        return self._plan_detail("SELECT * FROM prescriptions WHERE patient_id = ? ORDER BY start_date DESC", (patient_id,))

    def plan_by_patient_and_status(self, patient_id: str, status: str) -> str:
        return self._plan_detail("SELECT * FROM prescriptions WHERE patient_id = ? AND status = ?", (patient_id, status))

    def plan_dose_logs(self, prescription_id: str) -> str:
        return self._plan_detail("SELECT * FROM dose_logs WHERE prescription_id = ? ORDER BY timestamp ASC", (prescription_id,))

    def uses_full_scan(self, plan: str) -> bool:
        return "SCAN" in plan.upper() and "USING INDEX" not in plan.upper()

    # ------------------------------------------------------------------
    # Row mapping
    # ------------------------------------------------------------------
    def _row_to_prescription(self, row) -> Prescription:
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

def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _new_id() -> str:
    return str(uuid.uuid4())

class NotFoundError(Exception):
    pass
