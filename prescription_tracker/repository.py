"""Repository for prescription persistence and lifecycle transitions."""

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


def _now_iso() -> str:
    """Current UTC time as an ISO 8601 string with timezone."""
    return datetime.now(timezone.utc).isoformat()


class PrescriptionRepository:
    """Repository for prescription CRUD and lifecycle operations."""

    def __init__(self, database: Database):
        self.db = database

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
        """Persist a new prescription row.

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

    def get_by_patient(self, patient_id: UUID) -> dict:
        """Return a patient's full prescription history.

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
    # Status transitions (the only permitted mutations on a prescription)
    # ------------------------------------------------------------------
    def complete(self, prescription_id: UUID) -> Prescription:
        """Transition an active prescription to completed.

        Raises:
            ValueError: If the prescription does not exist or is not active.
        """
        return self._transition(prescription_id, PrescriptionStatus.COMPLETED, reason=None)

    def discontinue(self, prescription_id: UUID, reason: str) -> Prescription:
        """Transition an active prescription to discontinued with a mandatory reason.

        Raises:
            ValueError: If reason is missing/empty or the prescription is not active.
        """
        if not reason or not isinstance(reason, str) or not reason.strip():
            raise ValueError("a non-empty reason is required to discontinue a prescription")
        return self._transition(prescription_id, PrescriptionStatus.DISCONTINUED, reason=reason)

    def _transition(
        self,
        prescription_id: UUID,
        to_status: PrescriptionStatus,
        reason: Optional[str],
    ) -> Prescription:
        """Perform a status transition atomically.

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

    def get_dose_logs(self, prescription_id: UUID) -> List[DoseLog]:
        """Return dose logs for a prescription ordered by taken_at ascending."""
        cursor = self.db.execute(
            "SELECT * FROM dose_logs WHERE prescription_id = ? ORDER BY taken_at ASC",
            (str(prescription_id),),
        )
        logs: List[DoseLog] = []
        for row in cursor.fetchall():
            logs.append(
                DoseLog(
                    id=UUID(row["id"]),
                    prescription_id=UUID(row["prescription_id"]),
                    taken_at=datetime.fromisoformat(row["taken_at"]),
                    status=DoseStatus(row["status"]) if row["status"] else DoseStatus.TAKEN,
                )
            )
        return logs

    # ------------------------------------------------------------------
    # Row mapping
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