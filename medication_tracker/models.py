"""Medication data models."""

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4


class MedicationStatus(str, Enum):
    """Status of a medication record."""
    ACTIVE = "active"
    COMPLETED = "completed"


@dataclass
class Medication:
    """Represents a prescribed medication with dosage and schedule information.

    Attributes:
        id: Unique identifier (UUID)
        name: Medication name (required, non-empty)
        dosage: Dosage amount and unit e.g., "500mg" (required, non-empty)
        frequency: How often to take e.g., "twice daily" (required, non-empty)
        start_date: Treatment start date (optional)
        end_date: Treatment end date (optional)
        status: Current status (active/completed)
        created_at: Record creation timestamp
        updated_at: Record last update timestamp
    """
    name: str
    dosage: str
    frequency: str
    id: UUID = field(default_factory=uuid4)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    status: MedicationStatus = MedicationStatus.ACTIVE
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def __post_init__(self):
        """Validate required fields after initialization."""
        if not self.name or not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("name must be a non-empty string")
        if not self.dosage or not isinstance(self.dosage, str) or not self.dosage.strip():
            raise ValueError("dosage must be a non-empty string")
        if not self.frequency or not isinstance(self.frequency, str) or not self.frequency.strip():
            raise ValueError("frequency must be a non-empty string")
        if not isinstance(self.status, MedicationStatus):
            if isinstance(self.status, str):
                try:
                    self.status = MedicationStatus(self.status.lower())
                except ValueError:
                    raise ValueError(f"status must be 'active' or 'completed', got '{self.status}'")
            else:
                raise ValueError("status must be a MedicationStatus or string")

    @classmethod
    def from_dict(cls, data: dict) -> "Medication":
        """Create a Medication from a dictionary."""
        from datetime import date

        # Parse date strings from dictionary
        start_date = data.get("start_date")
        if start_date and isinstance(start_date, str):
            try:
                start_date = date.fromisoformat(start_date)
            except ValueError:
                pass

        end_date = data.get("end_date")
        if end_date and isinstance(end_date, str):
            try:
                end_date = date.fromisoformat(end_date)
            except ValueError:
                pass

        return cls(
            id=UUID(data["id"]) if isinstance(data.get("id"), str) else data.get("id", uuid4()),
            name=data["name"],
            dosage=data["dosage"],
            frequency=data["frequency"],
            start_date=start_date,
            end_date=end_date,
            status=data.get("status", MedicationStatus.ACTIVE),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )

    def to_dict(self) -> dict:
        """Convert medication to dictionary representation."""
        return {
            "id": str(self.id),
            "name": self.name,
            "dosage": self.dosage,
            "frequency": self.frequency,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "status": self.status.value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class DoseStatus(str, Enum):
    """Status of a dose record."""
    TAKEN = "taken"
    SKIPPED = "skipped"
    MISSED = "missed"


@dataclass
class DoseRecord:
    """Represents a single dose taken of a medication.

    Attributes:
        id: Unique identifier (UUID)
        medication_id: Reference to the medication (UUID)
        date: Date the dose was taken
        timestamp: Exact timestamp when dose was recorded
        status: Dose status (taken/skipped/missed)
    """
    medication_id: UUID
    date: date
    id: UUID = field(default_factory=uuid4)
    timestamp: Optional[datetime] = None
    status: str = "taken"

    def __post_init__(self):
        """Validate dose record fields."""
        # Validate date cannot be in the future
        if self.date > date.today():
            raise ValueError("date cannot be in the future")

        # Validate status is a valid enum value
        valid_statuses = {"taken", "skipped", "missed"}
        if self.status not in valid_statuses:
            raise ValueError(f"status must be one of {valid_statuses}, got '{self.status}'")

        # Set default timestamp if not provided
        if self.timestamp is None:
            self.timestamp = datetime.now()

    @classmethod
    def from_dict(cls, data: dict) -> "DoseRecord":
        """Create a DoseRecord from a dictionary."""
        return cls(
            id=UUID(data["id"]) if isinstance(data.get("id"), str) else data.get("id", uuid4()),
            medication_id=UUID(data["medication_id"]) if isinstance(data.get("medication_id"), str) else data["medication_id"],
            date=data["date"] if isinstance(data["date"], date) else date.fromisoformat(data["date"]),
            timestamp=data.get("timestamp"),
            status=data.get("status", "taken"),
        )

    def to_dict(self) -> dict:
        """Convert dose record to dictionary representation."""
        return {
            "id": str(self.id),
            "medication_id": str(self.medication_id),
            "date": self.date.isoformat(),
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "status": self.status,
        }
