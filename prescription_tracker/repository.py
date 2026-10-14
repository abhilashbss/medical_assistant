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

    def __init__(self, database: Union[Database, sqlite3.Connection]):
        # Support both Database wrapper (Version A) and raw sqlite3.Connection (Version B)
        self.db = database
        self.conn = database if isinstance(database, sqlite3.Connection) else database

    def _execute(self, sql: str, params: tuple = (), commit: bool = False):
        """Internal helper to unify execution across Database and Connection objects."""
        if hasattr(self.db, 'execute') and not isinstance(self.db, sqlite3.Connection):
            # Version A style: Database object
            cursor = self.db.execute(sql, params)
            if commit:
                # Database wrapper usually handles transactions via context managers, 
                # but we ensure consistency here.
                pass 
            return cursor
        else:
            # Version B style: sqlite3.Connection
            cursor = self.conn.execute(sql, params)
            if commit:
                self.conn.commit()
            return cursor

    # ------------------------------------------------------------------
    # Reference data helpers (Version A)
    # ------------------------------------------------------------------
    def ensure_patient(self, patient_id: UUID, name: str = "Patient") -> None:
        """Insert a patient row if it does not already exist."""
        with self._transaction():
            self._execute(
                "INSERT OR IGNORE INTO patients (id, name, created_at) VALUES (?, ?, ?)",
                (str(patient_id), name, _now_iso()),
            )

    def ensure_doctor(self, doctor_id: UUID, name: str = "Doctor") -> None:
        """Insert a doctor row if it does not already exist."""
        with self._transaction():
            self._execute(
                "INSERT OR IGNORE INTO doctors (id, name, created_at) VALUES (?, ?, ?)",
                (str(doctor_id), name, _now_iso()),
            )

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------
    def create(self, prescription: Prescription) -> Prescription:
        """Persist a new prescription row (Version A)."""
        self.ensure_patient(prescription.patient_id)
        self.ensure_doctor(prescription.doctor_id)

        now = _now_iso()
        with self._transaction():
            self._execute(
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
        """Persist a new prescription row (Version B)."""
        data.validate()
        rx_id = _new_id()
        with self._transaction():
            self._execute(
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
        return self.get_prescription(rx_id)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------
    def get_by_id(self, prescription_id: UUID) -> Optional[Prescription]:
        """Return a single prescription by id, or None (Version A)."""
        cursor = self._execute(
            "SELECT * FROM prescriptions WHERE id = ?",
            (str(prescription_id),),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return self._row_to_prescription(row)

    def get_prescription(self, rx_id: str) -> dict[str, Any]:
        """Return a single prescription by id as dict (Version B)."""
        row = self._execute(
            "SELECT * FROM prescriptions WHERE id = ?", (rx_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"prescription {rx_id} not found")
        return dict(row)

    def get_by_patient(self, patient_id: UUID) -> dict:
        """Return a patient's full prescription history (Version A)."""
        cursor = self._execute(
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
        """Return active and historical prescriptions as dicts (Version B)."""
        rows = self._execute(
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
        """Full prescription history sorted by start_date DESC (Version B)."""
        rows = self._execute(
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
        """Filter by patient_id and status (Version B)."""
        rows = self._execute(
            """
            SELECT * FROM prescriptions
            WHERE patient_id = ? AND status = ?
            ORDER BY start_date DESC
            """,
            (patient_id, status),
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Status transitions
    # ------------------------------------------------------------------
    def complete(self, prescription_id: Union[UUID, str]) -> Union[Prescription, dict]:
        """Transition an active prescription to completed."""
        # Handle both Version A (UUID -> Prescription) and Version B (str -> dict)
        if isinstance(prescription_id, UUID):
            return self._transition(prescription_id, PrescriptionStatus.COMPLETED, reason=None)
        else:
            return self.transition_status(prescription_id, StatusTransition(to_status="completed"))

    def discontinue(self, prescription_id: Union[UUID, str], reason: str) -> Union[Prescription, dict]:
        """Transition an active prescription to discontinued."""
        if isinstance(prescription_id, UUID):
            if not reason or not isinstance(reason, str) or not reason.strip():
                raise ValueError("a non-empty reason is required to discontinue a prescription")
            return self._transition(prescription_id, PrescriptionStatus.DISCONTINUED, reason=reason)
        else:
            return self.transition_status(
                prescription_id, StatusTransition(to_status="discontinued", reason=reason)
            )

    def _transition(
        self,
        prescription_id: UUID,
        to_status: PrescriptionStatus,
        reason: Optional[str],
    ) -> Prescription:
        """Perform a status transition atomically (Version A)."""
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

        with self._transaction():
            self._execute(
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
            self._execute(
                "UPDATE prescriptions SET status = ?, updated_at = ? WHERE id = ?",
                (to_status.value, now, str(prescription_id)),
            )

        prescription.status = to_status
        prescription.updated_at = datetime.fromisoformat(now)
        transition.transitioned_at = datetime.fromisoformat(now)
        return prescription

    def transition_status(
        self, rx_id: str, transition: StatusTransition
    ) -> dict[str, Any]:
        """Perform a status transition atomically (Version B)."""
        transition.validate()
        row = self._execute(
            "SELECT status FROM prescriptions WHERE id = ?", (rx_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"prescription {rx_id} not found")
        from_status = row["status"]
        to_status = transition.to_status

        if from_status == to_status:
            raise ValidationError({"to_status": f"prescription already {to_status}"})
        if from_status != "active":
            raise ValidationError({"to_status": f"cannot transition from {from_status} to {to_status}"})

        with self._transaction():
            self._execute("UPDATE prescriptions SET status = ? WHERE id = ?", (to_status, rx_id))
            self._execute(
                """
                INSERT INTO status_transitions
                    (prescription_id, from_status, to_status, reason)
                VALUES (?, ?, ?, ?)
                """,
                (rx_id, from_status, to_status, transition.reason),
            )
        return self.get_prescription(rx_id)

    def get_transitions(self, prescription_id: UUID) -> List[StatusTransition]:
        """Return the audit trail of status transitions for a prescription (Version A)."""
        cursor = self._execute(
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
        """Append a dose log entry for a prescription (Version A)."""
        now = _now_iso()
        with self._transaction():
            self._execute(
                """
                INSERT INTO dose_logs (id, prescription_id, taken_at, status)
                VALUES (?, ?, ?, ?)
                """,
                (
                    str(dose.id),
                    str(dose.prescription_id),
                    dose.taken_at.isoformat(),
                    dose.status.value,
                ),
            )
        return dose

    def add_dose_log(self, data: DoseLogCreate) -> dict[str, Any]:
        """Append a dose log entry for a prescription (Version B)."""
        data.validate()
        rx = self._execute(
            "SELECT status FROM prescriptions WHERE id = ?",
            (data.prescription_id,),
        ).fetchone()
        if rx is None:
            raise NotFoundError(f"prescription {data.prescription_id} not found")
        if rx["status"] != "active":
            raise ValidationError({"prescription_id": "cannot log doses for a non-active prescription"})
        
        with self._transaction():
            cur = self._execute(
                """
                INSERT INTO dose_logs (prescription_id, event, timestamp, notes)
                VALUES (?, ?, ?, ?)
                """,
                (data.prescription_id, data.event, data.timestamp, data.notes),
            )
            log_id = cur.lastrowid
            row = self._execute("SELECT * FROM dose_logs WHERE id = ?", (log_id,)).fetchone()
            return dict(row)

    def get_dose_logs(
        self,
        prescription_id: Union[UUID, str],
        start_ts: Optional[str] = None,
        end_ts: Optional[str] = None,
    ) -> Union[List[DoseLog], List[dict]]:
        """Return dose logs for a prescription (Merged A & B)."""
        pid = str(prescription_id)
        
        # If date filters are provided, we must return dicts (Version B behavior)
        if start_ts or end_ts:
            if start_ts and end_ts:
                sql = "SELECT * FROM dose_logs WHERE prescription_id = ? AND timestamp >= ? AND timestamp <= ? ORDER BY timestamp ASC"
                params = (pid, start_ts, end_ts)
            elif start_ts:
                sql = "SELECT * FROM dose_logs WHERE prescription_id = ? AND timestamp >= ? ORDER BY timestamp ASC"
                params = (pid, start_ts)
            else:
                sql = "SELECT * FROM dose_logs WHERE prescription_id = ? AND timestamp <= ? ORDER BY timestamp ASC"
                params = (pid, end_ts)
            
            rows = self._execute(sql, params).fetchall()
            return [dict(r) for r in rows]

        # No filters: check if caller expects DoseLog objects (Version A) or dicts (Version B)
        # Since we can't know the caller, we check the context or provide a unified approach.
        # To maintain compatibility with Version A's return type:
        cursor = self._execute(
            "SELECT * FROM dose_logs WHERE prescription_id = ? ORDER BY taken_at ASC",
            (pid,),
        )
        
        # Version A expects DoseLog objects. Version B expects dicts.
        # We return DoseLog objects if the columns match Version A's schema.
        rows = cursor.fetchall()
        if not rows:
            return []
        
        # Heuristic: if 'taken_at' exists, use Version A mapping. If 'timestamp' exists, use Version B.
        if "taken_at" in rows[0].keys():
            logs: List[DoseLog] = []
            for row in rows:
                logs.append(
                    DoseLog(
                        id=UUID(row["id"]),
                        prescription_id=UUID(row["prescription_id"]),
                        taken_at=datetime.fromisoformat(row["taken_at"]),
                        status=DoseStatus(row["status"]) if row["status"] else DoseStatus.TAKEN,
                    )
                )
            return logs
        else:
            return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Query Plan (Version B)
    # ------------------------------------------------------------------
    def explain_query_plan(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        rows = self._execute("EXPLAIN QUERY PLAN " + sql, params).fetchall()
        return [dict(r) for r in rows]

    def _plan_detail(self, sql: str, params: tuple = ()) -> str:
        return " ".join(r["detail"] for r in self.explain_query_plan(sql, params))

    def plan_history_by_patient(self, patient_id: str) -> str:
        return self._plan_detail(
            "SELECT * FROM prescriptions WHERE patient_id = ? ORDER BY start_date DESC",
            (patient_id,),
        )

    def plan_by_patient_and_status(self, patient_id: str, status: str) -> str:
        return self._plan_detail(
            "SELECT * FROM prescriptions WHERE patient_id = ? AND status = ?",
            (patient_id, status),
        )

    def plan_dose_logs(self, prescription_id: str) -> str:
        return self._plan_detail(
            "SELECT * FROM dose_logs WHERE prescription_id = ? ORDER BY timestamp ASC",
            (prescription_id,),
        )

    def uses_full_scan(self, plan: str) -> bool:
        return "SCAN" in plan.upper() and "USING INDEX" not in plan.upper()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _transaction(self):
        """Unify transaction handling."""
        if hasattr(self.db, 'transaction'):
            return self.db.transaction()
        else:
            # Manual transaction for sqlite3.Connection
            class ConnectionTransaction:
                def __init__(self, conn): self.conn = conn
                def __enter__(self): self.conn.execute("BEGIN")
                def __exit__(self, exc_type, exc_val, exc_tb):
                    if exc_type: self.conn.rollback()
                    else: self.conn.commit()
            return ConnectionTransaction(self.conn)

    def _row_to_prescription(self, row) -> Prescription:
        """Convert a sqlite3.Row into a Prescription (Version A)."""
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
