"""Prescription validation.

``validate_prescription`` inspects a raw dict (as would arrive from an API
boundary) and rejects it with a single :class:`ValidationError` listing every
problem found. Accepted datetime format is ISO 8601 **with a timezone offset**;
naive datetimes (no ``tzinfo``) are rejected per the hard constraint that all
date/time fields carry timezone information.
"""

from datetime import datetime, timezone
from typing import Any, List, Tuple

from medication_tracker.errors import ValidationError
from medication_tracker.models import Prescription, PrescriptionStatus

REQUIRED_FIELDS = (
    "patient_id",
    "doctor_id",
    "medicine_name",
    "dosage_amount",
    "dosage_unit",
    "frequency",
    "start_date",
)


def _parse_iso8601(value: str) -> datetime:
    """Parse an ISO 8601 string, accepting a trailing ``Z`` as UTC.

    Raises ``ValueError`` if the string is not valid ISO 8601. The caller is
    responsible for checking that the resulting datetime is timezone-aware.
    """
    if not isinstance(value, str):
        raise ValueError("not a string")
    text = value.strip()
    if not text:
        raise ValueError("empty string")
    # Python < 3.11 ``fromisoformat`` does not accept a trailing 'Z'.
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


def _is_timezone_aware(dt: datetime) -> bool:
    return dt.tzinfo is not None and dt.utcoffset() is not None


def validate_prescription(data: Any) -> Prescription:
    """Validate ``data`` and return a :class:`Prescription`.

    Parameters
    ----------
    data : dict
        Raw prescription fields. Expected keys: ``id`` (optional; generated if
        absent), ``patient_id``, ``doctor_id``, ``medicine_name``,
        ``dosage_amount`` (positive number), ``dosage_unit`` (non-empty str),
        ``frequency`` (non-empty str), ``start_date`` (ISO 8601 with timezone),
        ``end_date`` (optional ISO 8601 with timezone), ``status`` (optional,
        one of active/completed/discontinued, default active).

    Returns
    -------
    Prescription
        A validated prescription instance.

    Raises
    ------
    ValidationError
        Carrying a list of ``(field, message)`` tuples for every problem:
        missing required fields, non-ISO-8601 datetimes, naive datetimes
        without a timezone, ``end_date`` preceding ``start_date``, non-positive
        ``dosage_amount``, empty ``dosage_unit`` / ``medicine_name`` /
        ``frequency``, and unknown ``status``.
    """
    errors: List[Tuple[str, str]] = []

    if not isinstance(data, dict):
        raise ValidationError([("_", "expected a mapping of prescription fields")])

    def add(field: str, message: str) -> None:
        errors.append((field, message))

    # (a) Missing required fields.
    for field_name in REQUIRED_FIELDS:
        if field_name not in data or data[field_name] is None:
            add(field_name, "is required")

    # Non-empty string fields (only check when present to avoid duplicate errors).
    for field_name in ("medicine_name", "dosage_unit", "frequency"):
        value = data.get(field_name)
        if value is not None and not isinstance(value, str):
            add(field_name, "must be a string")
        elif isinstance(value, str) and value.strip() == "":
            add(field_name, "must not be empty")

    # patient_id / doctor_id must be non-empty strings when present.
    for field_name in ("patient_id", "doctor_id"):
        value = data.get(field_name)
        if value is not None and not isinstance(value, str):
            add(field_name, "must be a string")
        elif isinstance(value, str) and value.strip() == "":
            add(field_name, "must not be empty")

    # (d) dosage_amount must be a positive number.
    amount = data.get("dosage_amount")
    if amount is not None:
        if isinstance(amount, bool) or not isinstance(amount, (int, float)):
            add("dosage_amount", "must be a number")
        elif amount <= 0:
            add("dosage_amount", "must be greater than zero")

    # (b) Datetime validation: ISO 8601 with timezone.
    start_dt: Any = None
    start_raw = data.get("start_date")
    if start_raw is not None:
        try:
            start_dt = _parse_iso8601(start_raw)
        except (ValueError, TypeError):
            add("start_date", "must be an ISO 8601 datetime string")
        else:
            if not _is_timezone_aware(start_dt):
                add("start_date", "must include a timezone offset (naive datetimes are not allowed)")

    end_raw = data.get("end_date")
    end_dt: Any = None
    if end_raw is not None:
        try:
            end_dt = _parse_iso8601(end_raw)
        except (ValueError, TypeError):
            add("end_date", "must be an ISO 8601 datetime string")
        else:
            if not _is_timezone_aware(end_dt):
                add("end_date", "must include a timezone offset (naive datetimes are not allowed)")

    # (c) end_date must not precede start_date (only compare when both are
    # timezone-aware, since naive datetimes are already flagged above).
    if (
        start_dt is not None
        and end_dt is not None
        and _is_timezone_aware(start_dt)
        and _is_timezone_aware(end_dt)
    ):
        if end_dt < start_dt:
            add("end_date", "must not precede start_date")

    # status validation when provided.
    status = data.get("status", PrescriptionStatus.ACTIVE)
    if status is None:
        status = PrescriptionStatus.ACTIVE
    if not isinstance(status, PrescriptionStatus):
        if status not in PrescriptionStatus._value2member_map_:
            add("status", "must be one of: active, completed, discontinued")
        else:
            status = PrescriptionStatus(status)

    if errors:
        raise ValidationError(errors)

    return Prescription(
        id=data.get("id"),
        patient_id=data["patient_id"],
        doctor_id=data["doctor_id"],
        medicine_name=data["medicine_name"],
        dosage_amount=float(data["dosage_amount"]),
        dosage_unit=data["dosage_unit"],
        frequency=data["frequency"],
        start_date=data["start_date"],
        end_date=data.get("end_date"),
        status=status,
    )