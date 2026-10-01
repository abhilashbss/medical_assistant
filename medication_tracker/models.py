"""Data models for medications and dose records."""

from datetime import datetime
from typing import Optional


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


class Medication:
    """A prescribed medication entry.

    Required fields: name, dosage, frequency. Optional: start_date, end_date
    (ISO YYYY-MM-DD strings). status is 'active' or 'completed'.
    """

    def __init__(
        self,
        name: str,
        dosage: str,
        frequency: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        status: str = "active",
        id: Optional[int] = None,
        created_at: Optional[str] = None,
        updated_at: Optional[str] = None,
    ):
        self.id = id
        self.name = name
        self.dosage = dosage
        self.frequency = frequency
        self.start_date = start_date
        self.end_date = end_date
        self.status = status
        self.created_at = created_at
        self.updated_at = updated_at

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "dosage": self.dosage,
            "frequency": self.frequency,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_row(cls, row) -> "Medication":
        return cls(
            id=row["id"],
            name=row["name"],
            dosage=row["dosage"],
            frequency=row["frequency"],
            start_date=row["start_date"],
            end_date=row["end_date"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def __repr__(self) -> str:
        return f"Medication(id={self.id!r}, name={self.name!r}, status={self.status!r})"

    def __eq__(self, other) -> bool:
        if not isinstance(other, Medication):
            return NotImplemented
        return self.to_dict() == other.to_dict()


class DoseRecord:
    """A timestamped record of a dose being taken."""

    def __init__(
        self,
        medication_id: int,
        date: str,
        timestamp: str,
        status: str = "taken",
        id: Optional[int] = None,
    ):
        self.id = id
        self.medication_id = medication_id
        self.date = date
        self.timestamp = timestamp
        self.status = status

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "medication_id": self.medication_id,
            "date": self.date,
            "timestamp": self.timestamp,
            "status": self.status,
        }

    @classmethod
    def from_row(cls, row) -> "DoseRecord":
        return cls(
            id=row["id"],
            medication_id=row["medication_id"],
            date=row["date"],
            timestamp=row["timestamp"],
            status=row["status"],
        )