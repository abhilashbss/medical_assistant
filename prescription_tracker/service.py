"""Service layer enforcing prescription business rules."""

import sqlite3
from typing import List, Optional
from uuid import UUID

from .database import Database
from .models import DoseLog, Prescription, PrescriptionStatus
from .repository import PrescriptionRepository


class ConflictError(Exception):
    """Raised when a create violates the one-active-per-medicine rule."""

    pass


class PrescriptionService:
    """Service coordinating prescription creation and lifecycle transitions."""

    def __init__(self, database: Database):
        self.db = database
        self.repository = PrescriptionRepository(database)

    def create_prescription(self, prescription: Prescription) -> Prescription:
        """Create a prescription, enforcing the one-active-per-medicine rule.

        Raises:
            ConflictError: If an active prescription for the same patient
                and medicine already exists (caught from the partial unique index).
        """
        try:
            return self.repository.create(prescription)
        except sqlite3.IntegrityError as exc:
            message = str(exc)
            if "idx_one_active_per_medicine" in message or "UNIQUE constraint failed" in message:
                raise ConflictError(
                    "an active prescription for this patient and medicine already exists"
                ) from exc
            raise

    def get_prescription(self, prescription_id: UUID) -> Optional[Prescription]:
        return self.repository.get_by_id(prescription_id)

    def get_patient_history(self, patient_id: UUID) -> dict:
        return self.repository.get_by_patient(patient_id)

    def complete_prescription(self, prescription_id: UUID) -> Prescription:
        return self.repository.complete(prescription_id)

    def discontinue_prescription(self, prescription_id: UUID, reason: str) -> Prescription:
        return self.repository.discontinue(prescription_id, reason)

    def get_transitions(self, prescription_id: UUID) -> list:
        return self.repository.get_transitions(prescription_id)

    def log_dose(self, dose: DoseLog) -> DoseLog:
        return self.repository.log_dose(dose)

    def get_dose_logs(self, prescription_id: UUID) -> List[DoseLog]:
        return self.repository.get_dose_logs(prescription_id)