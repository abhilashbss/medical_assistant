"""Pydantic-style data models and the validation layer.

Validation is deliberately explicit (not relying solely on Pydantic) so
that clear per-field error messages surface before any database write.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


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
    to_status: str
    reason: Optional[str] = None

    def validate(self) -> "StatusTransition":
        errors: dict[str, str] = {}
        if self.to_status not in ("completed", "discontinued"):
            errors["to_status"] = "to_status must be 'completed' or 'discontinued'"
        if self.to_status == "discontinued" and not (self.reason and self.reason.strip()):
            errors["reason"] = "reason is required when discontinuing"
        if errors:
            raise ValidationError(errors)
        return self


def is_valid_iso8601_tz(value: str) -> bool:
    try:
        _parse_iso8601_tz(value, "_")
        return True
    except ValidationError:
        return False