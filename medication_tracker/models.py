"""Prescription and dose-log data models."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4


class PrescriptionStatus(str, Enum):
    """Lifecycle status of a prescription."""

    ACTIVE = "active"
    COMPLETED = "completed"
    DISCONTINUED = "discontinued"


def _now_iso() -> str:
    """Current UTC time as an ISO 8601 string with timezone."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Prescription:
    """A prescription record for a single patient.

    Rows are immutable after creation except through explicit status-transition
    update paths. Dosage is a structured amount+unit pair.

    Attributes:
        patient_id: Reference to the patient.
        doctor_id: Reference to the prescribing doctor.
        medicine_name: Name of the prescribed medicine.
        dosage_amount: Numeric dosage amount (must be > 0).
        dosage_unit: Unit of the dosage (e.g. 'mg', 'ml').
        frequency: Dosing frequency (e.g. 'twice daily').
        start_date: ISO 8601 start date/time with timezone (required).
        end_date: Optional ISO 8601 end date/time; must be after start_date.
        status: Lifecycle status (active/completed/discontinued).
        id: Unique identifier (UUID string).
        created_at: Record creation timestamp.
    """

    patient_id: str
    doctor_id: str
    medicine_name: str
    dosage_amount: float
    dosage_unit: str
    frequency: str
    start_date: str
    end_date: Optional[str] = None
    status: PrescriptionStatus = PrescriptionStatus.ACTIVE
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=_now_iso)

    def __post_init__(self):
        """Validate required fields and invariants."""
        required = {
            "patient_id": self.patient_id,
            "doctor_id": self.doctor_id,
            "medicine_name": self.medicine_name,
            "dosage_unit": self.dosage_unit,
            "frequency": self.frequency,
            "start_date": self.start_date,
        }
        for name, value in required.items():
            if value is None or (isinstance(value, str) and not value.strip()):
                raise ValueError(f"{name} must be a non-empty string")
        if self.dosage_amount is None or self.dosage_amount <= 0:
            raise ValueError("dosage_amount must be a positive number")
        # Status coercion
        if not isinstance(self.status, PrescriptionStatus):
            if isinstance(self.status, str):
                try:
                    self.status = PrescriptionStatus(self.status)
                except ValueError:
                    raise ValueError(
                        f"status must be one of {[s.value for s in PrescriptionStatus]}, "
                        f"got '{self.status}'"
                    )
            else:
                raise ValueError("status must be a PrescriptionStatus or string")
        # Start date must be ISO 8601 with timezone
        _validate_iso8601_tz(self.start_date, "start_date")
        if self.end_date is not None:
            _validate_iso8601_tz(self.end_date, "end_date")
            if self.end_date < self.start_date:
                raise ValueError("end_date must be after start_date")

    def to_dict(self) -> dict:
        """Convert to a JSON-serializable dictionary."""
        return {
            "id": self.id,
            "patient_id": self.patient_id,
            "doctor_id": self.doctor_id,
            "medicine_name": self.medicine_name,
            "dosage_amount": self.dosage_amount,
            "dosage_unit": self.dosage_unit,
            "frequency": self.frequency,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "status": self.status.value if isinstance(self.status, PrescriptionStatus) else self.status,
            "created_at": self.created_at,
        }

    @classmethod
    def from_row(cls, row) -> "Prescription":
        """Build a Prescription from a sqlite3.Row."""
        status_val = row["status"]
        try:
            status = PrescriptionStatus(status_val)
        except ValueError:
            status = PrescriptionStatus.ACTIVE
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
            status=status,
            created_at=row["created_at"],
        )


@dataclass
class StatusTransition:
    """An append-only audit row recording a prescription status transition."""

    prescription_id: str
    from_status: PrescriptionStatus
    to_status: PrescriptionStatus
    timestamp: str
    id: str = field(default_factory=lambda: str(uuid4()))
    reason: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "prescription_id": self.prescription_id,
            "from_status": (
                self.from_status.value
                if isinstance(self.from_status, PrescriptionStatus)
                else self.from_status
            ),
            "to_status": (
                self.to_status.value
                if isinstance(self.to_status, PrescriptionStatus)
                else self.to_status
            ),
            "reason": self.reason,
            "timestamp": self.timestamp,
        }


class DoseEvent(str, Enum):
    """Adherence event recorded per dose."""

    TAKEN = "taken"
    SKIPPED = "skipped"


@dataclass
class DoseLog:
    """A single append-only dose adherence event for a prescription.

    Attributes:
        prescription_id: Reference to the prescription.
        event: 'taken' or 'skipped'.
        timestamp: ISO 8601 timestamp with timezone of the event.
        id: Unique identifier (UUID string).
        notes: Optional free-text notes.
    """

    prescription_id: str
    event: DoseEvent
    timestamp: str
    id: str = field(default_factory=lambda: str(uuid4()))
    notes: Optional[str] = None

    def __post_init__(self):
        """Validate dose log fields."""
        if not self.prescription_id or not str(self.prescription_id).strip():
            raise ValueError("prescription_id must be a non-empty string")
        if not isinstance(self.event, DoseEvent):
            if isinstance(self.event, str):
                try:
                    self.event = DoseEvent(self.event)
                except ValueError:
                    raise ValueError(
                        f"event must be 'taken' or 'skipped', got '{self.event}'"
                    )
            else:
                raise ValueError("event must be a DoseEvent or string")
        _validate_iso8601_tz(self.timestamp, "timestamp")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "prescription_id": self.prescription_id,
            "event": self.event.value if isinstance(self.event, DoseEvent) else self.event,
            "timestamp": self.timestamp,
            "notes": self.notes,
        }

    @classmethod
    def from_row(cls, row) -> "DoseLog":
        """Build a DoseLog from a sqlite3.Row."""
        event_val = row["event"]
        try:
            event = DoseEvent(event_val)
        except ValueError:
            event = DoseEvent.TAKEN
        return cls(
            id=row["id"],
            prescription_id=row["prescription_id"],
            event=event,
            timestamp=row["timestamp"],
            notes=row["notes"],
        )


def _validate_iso8601_tz(value: str, field_name: str) -> None:
    """Reject non-ISO-8601 strings and naive datetimes lacking timezone info."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty ISO 8601 string")
    # Normalize a trailing 'Z' (UTC) to '+00:00' so fromisoformat accepts it
    # on Python versions that don't handle 'Z' natively.
    normalized = value
    if normalized.rstrip().endswith("Z"):
        normalized = normalized.rstrip()[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a valid ISO 8601 datetime: {value}") from exc
    # Require timezone awareness (offset or 'Z')
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must include timezone information: {value}")