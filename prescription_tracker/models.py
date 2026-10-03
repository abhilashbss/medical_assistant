"""Prescription data models and the validation layer.

This module exposes two cooperating layers:

* The dataclass/enum domain models (``Prescription``, ``PrescriptionStatus``,
  ``DoseLog``, ``DoseStatus``, ``StatusTransition``) used by the Flask service
  stack (``database``/``repository``/``service``/``api``) and their tests.
* The Pydantic-style create models and explicit validation layer
  (``ValidationError``, ``PrescriptionCreate``, ``DoseLogCreate``,
  ``StatusTransition``'s request form) used by the FastAPI stack (``db``/``app`` and
  the repository's dict-returning methods) and their tests.

Validation is deliberately explicit (not relying solely on Pydantic) so
that clear per-field error messages surface before any database write.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4


class PrescriptionStatus(str, Enum):
    """Lifecycle status of a prescription."""
    ACTIVE = "active"
    COMPLETED = "completed"
    DISCONTINUED = "discontinued"

    @classmethod
    def transition_allowed(cls, from_status: "PrescriptionStatus", to_status: "PrescriptionStatus") -> bool:
        """Only active prescriptions may transition to a terminal status."""
        if from_status == cls.ACTIVE and to_status in (cls.COMPLETED, cls.DISCONTINUED):
            return True
        return False


class DoseStatus(str, Enum):
    """Status of a dose log entry."""
    TAKEN = "taken"
    SKIPPED = "skipped"
    MISSED = "missed"


def _parse_tz_datetime(value) -> Optional[datetime]:
    """Parse an ISO 8601 string into a timezone-aware datetime.

    Accepts datetime objects and ISO 8601 strings. Rejects naive datetimes
    (those lacking timezone information) and unparseable strings.

    Args:
        value: A datetime, an ISO 8601 string, or None.

    Returns:
        A timezone-aware datetime, or None when value is None/empty.

    Raises:
        ValueError: If the string is not valid ISO 8601 or is naive.
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("datetime must include timezone information (ISO 8601 with tz)")
        return value
    if not isinstance(value, str):
        raise ValueError(f"datetime must be an ISO 8601 string, got {type(value).__name__}")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"start_date/end_date must be valid ISO 8601, got '{value}'") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"datetime must include timezone information (ISO 8601 with tz), got '{value}'")
    return parsed


class ValidationError(Exception):
    """Raised when prescription or dose-log input fails validation."""

    def __init__(self, errors: dict[str, str] | list[str] | str):
        if isinstance(errors, dict):
            self.errors = errors
        elif isinstance(errors, list):
            self.errors = {"_": "; ".join(errors)}
        else:
            self.errors = {"_": str(errors)}
        super().__init__(str(self.errors))


def _parse_iso8601_tz(value: str, field_name: str) -> str:
    """Validate an ISO 8601 string with timezone; return it unchanged.

    Rejects non-ISO strings and naive datetimes lacking timezone info.
    """
    if not isinstance(value, str):
        raise ValidationError({field_name: f"{field_name} must be an ISO 8601 string"})
    normalized = value.replace("Z", "+00:00") if value.endswith("Z") else value
    try:
        dt = datetime.fromisoformat(normalized)
    except (ValueError, TypeError):
        raise ValidationError(
            {field_name: f"{field_name} is not valid ISO 8601: {value!r}"}
        )
    # Require timezone awareness (offset or Z).
    if dt.tzinfo is None:
        raise ValidationError(
            {field_name: f"{field_name} must include a timezone offset: {value!r}"}
        )
    return value


REQUIRED_PRESCRIPTION_FIELDS = (
    "patient_id",
    "medicine_name",
    "dosage_amount",
    "dosage_unit",
    "frequency",
    "start_date",
    "doctor_id",
)


@dataclass
class Prescription:
    """A patient prescription with structured dosage and lifecycle status.

    Attributes:
        patient_id: UUID identifying the patient (required).
        doctor_id: UUID identifying the prescribing doctor (required).
        medicine_name: Name of the prescribed medicine (required, non-empty).
        dosage_amount: Numeric dosage amount as a string e.g. "500" (required, non-empty).
        dosage_unit: Dosage unit e.g. "mg", "ml" (required, non-empty).
        frequency: Dosing frequency e.g. "twice daily" (required, non-empty).
        start_date: ISO 8601 timezone-aware start datetime (required).
        end_date: Optional ISO 8601 timezone-aware end datetime; must be >= start_date.
        status: Lifecycle status (active/completed/discontinued), defaults to active.
        id: UUID identifier (auto-generated).
        created_at: Record creation timestamp.
        updated_at: Record last update timestamp.
    """
    patient_id: UUID
    doctor_id: UUID
    medicine_name: str
    dosage_amount: str
    dosage_unit: str
    frequency: str
    start_date: datetime
    id: UUID = field(default_factory=uuid4)
    end_date: Optional[datetime] = None
    status: PrescriptionStatus = PrescriptionStatus.ACTIVE
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def __post_init__(self):
        """Validate required fields and date ordering."""
        required = {
            "patient_id": self.patient_id,
            "doctor_id": self.doctor_id,
            "medicine_name": self.medicine_name,
            "dosage_amount": self.dosage_amount,
            "dosage_unit": self.dosage_unit,
            "frequency": self.frequency,
            "start_date": self.start_date,
        }
        for name, value in required.items():
            if value is None:
                raise ValueError(f"{name} is required")
            if name in ("medicine_name", "dosage_amount", "dosage_unit", "frequency"):
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(f"{name} must be a non-empty string")

        if not isinstance(self.patient_id, UUID):
            raise ValueError("patient_id must be a UUID")
        if not isinstance(self.doctor_id, UUID):
            raise ValueError("doctor_id must be a UUID")

        # start_date must be timezone-aware
        self.start_date = _parse_tz_datetime(self.start_date)
        self.end_date = _parse_tz_datetime(self.end_date)

        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("end_date must not precede start_date")

        if not isinstance(self.status, PrescriptionStatus):
            if isinstance(self.status, str):
                try:
                    self.status = PrescriptionStatus(self.status.lower())
                except ValueError:
                    raise ValueError(
                        f"status must be one of {[s.value for s in PrescriptionStatus]}, got '{self.status}'"
                    )
            else:
                raise ValueError("status must be a PrescriptionStatus or string")

    @classmethod
    def from_dict(cls, data: dict) -> "Prescription":
        """Create a Prescription from a dictionary (e.g. API request body)."""
        missing = []
        for key in ("patient_id", "doctor_id", "medicine_name", "dosage_amount",
                    "dosage_unit", "frequency", "start_date"):
            if key not in data or data[key] is None or data[key] == "":
                missing.append(key)
        if missing:
            raise ValueError(f"missing required field(s): {', '.join(missing)}")

        return cls(
            id=UUID(data["id"]) if isinstance(data.get("id"), str) else data.get("id", uuid4()),
            patient_id=UUID(data["patient_id"]) if isinstance(data["patient_id"], str) else data["patient_id"],
            doctor_id=UUID(data["doctor_id"]) if isinstance(data["doctor_id"], str) else data["doctor_id"],
            medicine_name=data["medicine_name"],
            dosage_amount=str(data["dosage_amount"]),
            dosage_unit=data["dosage_unit"],
            frequency=data["frequency"],
            start_date=data["start_date"],
            end_date=data.get("end_date"),
            status=data.get("status", PrescriptionStatus.ACTIVE),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )

    def to_dict(self) -> dict:
        """Convert prescription to a dictionary representation."""
        return {
            "id": str(self.id),
            "patient_id": str(self.patient_id),
            "doctor_id": str(self.doctor_id),
            "medicine_name": self.medicine_name,
            "dosage_amount": self.dosage_amount,
            "dosage_unit": self.dosage_unit,
            "frequency": self.frequency,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "status": self.status.value if isinstance(self.status, PrescriptionStatus) else self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


@dataclass
class PrescriptionCreate:
    patient_id: str
    doctor_id: str
    medicine_name: str
    dosage_amount: float
    dosage_unit: str
    frequency: str
    start_date: str
    end_date: Optional[str] = None

    def validate(self) -> "PrescriptionCreate":
        errors: dict[str, str] = {}
        for f_name in REQUIRED_PRESCRIPTION_FIELDS:
            val = getattr(self, f_name)
            if val is None or (isinstance(val, str) and val.strip() == ""):
                errors[f_name] = f"{f_name} is required"
        if errors:
            raise ValidationError(errors)

        if self.dosage_amount is not None and self.dosage_amount <= 0:
            errors["dosage_amount"] = "dosage_amount must be > 0"
        if self.dosage_unit is not None and len(self.dosage_unit) == 0:
            errors["dosage_unit"] = "dosage_unit must not be empty"

        # Validate date strings (ISO 8601 with timezone).
        start = None
        try:
            start = _parse_iso8601_tz(self.start_date, "start_date")
        except ValidationError as e:
            errors.update(e.errors)

        if self.end_date is not None:
            try:
                _parse_iso8601_tz(self.end_date, "end_date")
            except ValidationError as e:
                errors.update(e.errors)

        # end_date > start_date check (after both parse successfully).
        if "start_date" not in errors and "end_date" not in errors and self.end_date:
            sd = datetime.fromisoformat(self.start_date.replace("Z", "+00:00") if self.start_date.endswith("Z") else self.start_date)
            ed = datetime.fromisoformat(self.end_date.replace("Z", "+00:00") if self.end_date.endswith("Z") else self.end_date)
            if ed <= sd:
                errors["end_date"] = "end_date must be after start_date"

        if errors:
            raise ValidationError(errors)
        return self


@dataclass
class DoseLogCreate:
    prescription_id: str
    event: str
    timestamp: str
    notes: Optional[str] = None

    def validate(self) -> "DoseLogCreate":
        errors: dict[str, str] = {}
        if not self.prescription_id:
            errors["prescription_id"] = "prescription_id is required"
        if self.event not in ("taken", "skipped"):
            errors["event"] = "event must be 'taken' or 'skipped'"
        try:
            _parse_iso8601_tz(self.timestamp, "timestamp")
        except ValidationError as e:
            errors.update(e.errors)
        if errors:
            raise ValidationError(errors)
        return self


@dataclass
class StatusTransition:
    """A prescription lifecycle transition.

    Serves two roles depending on how it is constructed:

    * **Audit row** (Flask/service stack): constructed with ``prescription_id``,
      ``from_status`` and ``to_status`` to record a completed transition.
      ``__post_init__`` then validates the full audit-row shape.
    * **Transition request** (FastAPI/dict stack): constructed with only
      ``to_status`` (and optionally ``reason``); validity is checked via
      :meth:`validate`, and ``from_status`` is resolved from the prescription
      row at transition time.
    """
    to_status: "PrescriptionStatus | str"
    prescription_id: Optional[UUID] = None
    from_status: Optional["PrescriptionStatus | str"] = None
    id: UUID = field(default_factory=uuid4)
    reason: Optional[str] = None
    transitioned_at: Optional[datetime] = None

    def __post_init__(self):
        # Coerce to_status to PrescriptionStatus when it is a recognised value.
        if not isinstance(self.to_status, PrescriptionStatus):
            if isinstance(self.to_status, str):
                try:
                    self.to_status = PrescriptionStatus(self.to_status.lower())
                except ValueError:
                    if self.prescription_id is not None:
                        raise ValueError(
                            f"to_status must be a valid PrescriptionStatus, got '{self.to_status}'"
                        )
            elif self.prescription_id is not None:
                raise ValueError("to_status must be a PrescriptionStatus or string")

        # Full audit-row validation only when this is a complete construction.
        if self.prescription_id is not None:
            if not isinstance(self.prescription_id, UUID):
                raise ValueError("prescription_id must be a UUID")
            for name in ("from_status", "to_status"):
                value = getattr(self, name)
                if not isinstance(value, PrescriptionStatus):
                    if isinstance(value, str):
                        try:
                            setattr(self, name, PrescriptionStatus(value.lower()))
                        except ValueError:
                            raise ValueError(f"{name} must be a valid PrescriptionStatus, got '{value}'")
                    else:
                        raise ValueError(f"{name} must be a PrescriptionStatus or string")
            if self.reason is not None and (not isinstance(self.reason, str) or not self.reason.strip()):
                raise ValueError("reason must be a non-empty string when provided")

    def validate(self) -> "StatusTransition":
        """Validate this as a transition request (FastAPI/dict stack)."""
        errors: dict[str, str] = {}
        if self.to_status not in ("completed", "discontinued"):
            errors["to_status"] = "to_status must be 'completed' or 'discontinued'"
        if self.to_status == "discontinued" and not (self.reason and self.reason.strip()):
            errors["reason"] = "reason is required when discontinuing"
        if errors:
            raise ValidationError(errors)
        return self

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "prescription_id": str(self.prescription_id) if self.prescription_id is not None else None,
            "from_status": self.from_status.value if isinstance(self.from_status, PrescriptionStatus) else self.from_status,
            "to_status": self.to_status.value if isinstance(self.to_status, PrescriptionStatus) else self.to_status,
            "reason": self.reason,
            "transitioned_at": self.transitioned_at.isoformat() if self.transitioned_at else None,
        }


@dataclass
class DoseLog:
    """A single dose adherence event for a prescription."""
    prescription_id: UUID
    taken_at: datetime
    id: UUID = field(default_factory=uuid4)
    status: DoseStatus = DoseStatus.TAKEN

    def __post_init__(self):
        if not isinstance(self.prescription_id, UUID):
            raise ValueError("prescription_id must be a UUID")
        self.taken_at = _parse_tz_datetime(self.taken_at)
        if self.taken_at is None:
            raise ValueError("taken_at is required")
        if not isinstance(self.status, DoseStatus):
            if isinstance(self.status, str):
                try:
                    self.status = DoseStatus(self.status.lower())
                except ValueError:
                    raise ValueError(
                        f"status must be one of {[s.value for s in DoseStatus]}, got '{self.status}'"
                    )
            else:
                raise ValueError("status must be a DoseStatus or string")

    @classmethod
    def from_dict(cls, data: dict) -> "DoseLog":
        if "taken_at" not in data or data["taken_at"] in (None, ""):
            raise ValueError("missing required field: taken_at")
        return cls(
            id=UUID(data["id"]) if isinstance(data.get("id"), str) else data.get("id", uuid4()),
            prescription_id=UUID(data["prescription_id"]) if isinstance(data.get("prescription_id"), str) else data["prescription_id"],
            taken_at=data["taken_at"],
            status=data.get("status", DoseStatus.TAKEN),
        )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "prescription_id": str(self.prescription_id),
            "taken_at": self.taken_at.isoformat() if self.taken_at else None,
            "status": self.status.value if isinstance(self.status, DoseStatus) else self.status,
        }


def is_valid_iso8601_tz(value: str) -> bool:
    try:
        _parse_iso8601_tz(value, "_")
        return True
    except ValidationError:
        return False