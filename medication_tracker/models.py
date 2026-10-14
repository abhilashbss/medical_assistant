"""Prescription data model.

A ``Prescription`` is a plain dataclass — validation lives in
:mod:`medication_tracker.validators`, persistence in
:mod:`medication_tracker.repository`. Patient and doctor are stored as foreign
key references (``patient_id`` / ``doctor_id``), never duplicated inline.
Dosage is a structured pair: ``dosage_amount`` (positive number) +
``dosage_unit`` (non-empty string).
"""

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class PrescriptionStatus(str, Enum):
    """Lifecycle states for a prescription.

    - ``active``: currently prescribed and in effect.
    - ``completed``: course of treatment finished.
    - ``discontinued``: stopped before completion (a reason is required).
    """

    ACTIVE = "active"
    COMPLETED = "completed"
    DISCONTINUED = "discontinued"


@dataclass
class Prescription:
    """A single prescription record.

    Fields
    ------
    id : str
        UUID identifying the prescription.
    patient_id : str
        UUID of the patient (foreign key into ``patients``).
    doctor_id : str
        UUID of the prescribing doctor (foreign key into ``doctors``).
    medicine_name : str
        Name of the prescribed medicine.
    dosage_amount : float
        Numeric dose amount; must be positive.
    dosage_unit : str
        Unit of the dose (e.g. ``"mg"``, ``"ml"``); must be non-empty.
    frequency : str
        Dosing frequency (e.g. ``"twice daily"``).
    start_date : str
        ISO 8601 datetime string with a timezone offset.
    end_date : Optional[str]
        Optional ISO 8601 datetime string with a timezone offset. Must be
        later than ``start_date`` when present.
    status : PrescriptionStatus
        Lifecycle status; defaults to ``active``.
    created_at : Optional[str]
        ISO 8601 datetime string with a timezone offset; set when persisted.
    """

    patient_id: str
    doctor_id: str
    medicine_name: str
    dosage_amount: float
    dosage_unit: str
    frequency: str
    start_date: str
    id: str = field(default_factory=lambda: str(uuid4()))
    end_date: Optional[str] = None
    status: PrescriptionStatus = PrescriptionStatus.ACTIVE
    created_at: Optional[str] = None

    def to_dict(self) -> dict:
        """Return a JSON-serializable dict with ``status`` as its string value."""
        data = asdict(self)
        data["status"] = self.status.value if isinstance(self.status, PrescriptionStatus) else self.status
        return data

    @classmethod
    def from_row(cls, row: dict) -> "Prescription":
        """Build a ``Prescription`` from a database row (dict or sqlite3.Row)."""
        return cls(
            id=row["id"],
            patient_id=row["patient_id"],
            doctor_id=row["doctor_id"],
            medicine_name=row["medicine_name"],
            dosage_amount=row["dosage_amount"],
            dosage_unit=row["dosage_unit"],
            frequency=row["frequency"],
            start_date=row["start_date"],
            end_date=row["end_date"],
            status=PrescriptionStatus(row["status"]),
            created_at=row["created_at"],
        )