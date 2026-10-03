"""Prescription repository for database operations."""

import sqlite3
from datetime import datetime, timezone
from typing import List, Optional

from .database import Database
from .models import Prescription, PrescriptionStatus, StatusTransition


class PrescriptionNotFoundError(Exception):
    """Raised when a prescription is not found."""


class PrescriptionRepository:
    """Repository for prescription CRUD and lifecycle operations.

    All queries use parameterized SQL. Prescription rows are immutable after
    creation except through the explicit status-transition methods
    (complete / discontinue), which also append a status_transitions audit row.
    """

    def __init__(self, database: Database):
        self.db = database

    # -- reference tables -------------------------------------------------

    def upsert_patient(self, patient_id: str, name: str = "Test Patient") -> None:
        """Insert a patient reference row if it does not exist."""
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO patients (id, name, created_at) VALUES (?, ?, ?) "
                "ON CONFLICT(id) DO NOTHING",
                (patient_id, name, datetime.now(timezone.utc).isoformat()),
            )

    def upsert_doctor(self, doctor_id: str, name: str = "Test Doctor") -> None:
        """Insert a doctor reference row if it does not exist."""
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO doctors (id, name, created_at) VALUES (?, ?, ?) "
                "ON CONFLICT(id) DO NOTHING",
                (doctor_id, name, datetime.now(timezone.utc).isoformat()),
            )

    # -- create / read ----------------------------------------------------

    def create(self, prescription: Prescription) -> Prescription:
        """Persist a new prescription row.

        Raises sqlite3.IntegrityError if the partial unique index on active
        prescriptions is violated (a second concurrent active prescription for
        the same patient+medicine).
        """
        self.upsert_patient(prescription.patient_id)
        self.upsert_doctor(prescription.doctor_id)
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO prescriptions
                    (id, patient_id, doctor_id, medicine_name, dosage_amount,
                     dosage_unit, frequency, start_date, end_date, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    prescription.id,
                    prescription.patient_id,
                    prescription.doctor_id,
                    prescription.medicine_name,
                    prescription.dosage_amount,
                    prescription.dosage_unit,
                    prescription.frequency,
                    prescription.start_date,
                    prescription.end_date,
                    prescription.status.value,
                    prescription.created_at,
                ),
            )
        return prescription

    def get_by_id(self, prescription_id: str) -> Optional[Prescription]:
        """Return a single prescription by id, or None."""
        cursor = self.db.execute(
            "SELECT * FROM prescriptions WHERE id = ?",
            (prescription_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return Prescription.from_row(row)

    def list_by_patient(
        self, patient_id: str, status: Optional[PrescriptionStatus] = None
    ) -> List[Prescription]:
        """List a patient's prescriptions sorted by start_date descending."""
        if status is not None:
            cursor = self.db.execute(
                "SELECT * FROM prescriptions WHERE patient_id = ? AND status = ? "
                "ORDER BY start_date DESC",
                (patient_id, status.value),
            )
        else:
            cursor = self.db.execute(
                "SELECT * FROM prescriptions WHERE patient_id = ? ORDER BY start_date DESC",
                (patient_id,),
            )
        return [Prescription.from_row(row) for row in cursor.fetchall()]

    # -- lifecycle (the only permitted mutations) -------------------------

    def complete(self, prescription_id: str) -> Prescription:
        """Transition an active prescription to completed.

        Appends a status_transitions audit row. Refuses if the prescription is
        not found or not active.
        """
        return self._transition(
            prescription_id, PrescriptionStatus.COMPLETED, reason=None
        )

    def discontinue(self, prescription_id: str, reason: str) -> Prescription:
        """Transition an active prescription to discontinued with a reason.

        The reason must be a non-empty string.
        """
        if not reason or not str(reason).strip():
            raise ValueError("discontinue requires a non-empty reason")
        return self._transition(
            prescription_id, PrescriptionStatus.DISCONTINUED, reason=reason.strip()
        )

    def _transition(
        self,
        prescription_id: str,
        to_status: PrescriptionStatus,
        reason: Optional[str],
    ) -> Prescription:
        prescription = self.get_by_id(prescription_id)
        if prescription is None:
            raise PrescriptionNotFoundError(
                f"Prescription {prescription_id} not found"
            )
        if prescription.status != PrescriptionStatus.ACTIVE:
            raise ValueError(
                f"Cannot transition a prescription with status "
                f"'{prescription.status.value}' to '{to_status.value}'"
            )
        now = datetime.now(timezone.utc).isoformat()
        from_status = prescription.status
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE prescriptions SET status = ? WHERE id = ?",
                (to_status.value, prescription_id),
            )
            conn.execute(
                """
                INSERT INTO status_transitions
                    (id, prescription_id, from_status, to_status, reason, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    StatusTransition(
                        prescription_id=prescription_id,
                        from_status=from_status,
                        to_status=to_status,
                        reason=reason,
                        timestamp=now,
                    ).id,
                    prescription_id,
                    from_status.value,
                    to_status.value,
                    reason,
                    now,
                ),
            )
        prescription.status = to_status
        return prescription

    def list_transitions(self, prescription_id: str) -> List[StatusTransition]:
        """Return status-transition audit rows for a prescription, oldest first."""
        cursor = self.db.execute(
            "SELECT * FROM status_transitions WHERE prescription_id = ? "
            "ORDER BY timestamp ASC",
            (prescription_id,),
        )
        transitions: List[StatusTransition] = []
        for row in cursor.fetchall():
            try:
                from_status = PrescriptionStatus(row["from_status"])
                to_status = PrescriptionStatus(row["to_status"])
            except ValueError:
                continue
            transitions.append(
                StatusTransition(
                    id=row["id"],
                    prescription_id=row["prescription_id"],
                    from_status=from_status,
                    to_status=to_status,
                    reason=row["reason"],
                    timestamp=row["timestamp"],
                )
            )
        return transitions

    # -- delete is intentionally NOT exposed for prescriptions ------------
    # The only way to remove a prescription is via ON DELETE CASCADE on a
    # patient/doctor delete, which the RESTRICT FK prevents. Historical
    # records must be preserved (discontinue-with-reason is the escape hatch).