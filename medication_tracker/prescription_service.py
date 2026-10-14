"""Prescription service: validation and business logic over the repository."""

from typing import List, Optional

from .models import Prescription, PrescriptionStatus
from .repository import PrescriptionNotFoundError, PrescriptionRepository


class PrescriptionService:
    """Service layer for prescription CRUD and lifecycle operations."""

    def __init__(self, repository: PrescriptionRepository):
        self.repository = repository

    def create_prescription(self, data: dict) -> Prescription:
        """Create a prescription from a request dict, enforcing validation."""
        required = [
            "patient_id",
            "doctor_id",
            "medicine_name",
            "dosage_amount",
            "dosage_unit",
            "frequency",
            "start_date",
        ]
        missing = [f for f in required if f not in data or data[f] is None or (isinstance(data[f], str) and not data[f].strip())]
        if missing:
            raise ValueError(f"missing required fields: {', '.join(missing)}")
        try:
            dosage_amount = float(data["dosage_amount"])
        except (TypeError, ValueError) as exc:
            raise ValueError("dosage_amount must be a number") from exc
        if dosage_amount <= 0:
            raise ValueError("dosage_amount must be a positive number")
        end_date = data.get("end_date")
        if end_date is not None and end_date < data["start_date"]:
            raise ValueError("end_date must be after start_date")
        status = data.get("status", PrescriptionStatus.ACTIVE)
        prescription = Prescription(
            patient_id=str(data["patient_id"]),
            doctor_id=str(data["doctor_id"]),
            medicine_name=str(data["medicine_name"]),
            dosage_amount=dosage_amount,
            dosage_unit=str(data["dosage_unit"]),
            frequency=str(data["frequency"]),
            start_date=str(data["start_date"]),
            end_date=end_date,
            status=status,
        )
        return self.repository.create(prescription)

    def get_prescription(self, prescription_id: str) -> Prescription:
        prescription = self.repository.get_by_id(prescription_id)
        if prescription is None:
            raise PrescriptionNotFoundError(f"Prescription {prescription_id} not found")
        return prescription

    def list_by_patient(
        self, patient_id: str, status: Optional[PrescriptionStatus] = None
    ) -> List[Prescription]:
        return self.repository.list_by_patient(patient_id, status=status)

    def complete(self, prescription_id: str) -> Prescription:
        return self.repository.complete(prescription_id)

    def discontinue(self, prescription_id: str, reason: str) -> Prescription:
        return self.repository.discontinue(prescription_id, reason)

    def get_status_history(self, prescription_id: str):
        return self.repository.list_transitions(prescription_id)