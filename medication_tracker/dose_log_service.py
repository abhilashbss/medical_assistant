"""Dose log service: adherence logging business logic."""

from datetime import datetime, timezone
from typing import List, Optional

from .dose_log_repository import PrescriptionDoseLogRepository
from .models import DoseEvent, DoseLog
from .prescription_service import PrescriptionService


class DoseLogService:
    """Service for appending and retrieving dose adherence logs.

    Logs may only be appended to prescriptions that exist and are active.
    Discontinued or completed prescriptions cannot receive new dose events.
    """

    def __init__(
        self,
        dose_log_repository: PrescriptionDoseLogRepository,
        prescription_service: PrescriptionService,
    ):
        self.repository = dose_log_repository
        self.prescription_service = prescription_service

    def append_dose_log(
        self,
        prescription_id: str,
        event: str,
        timestamp: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> DoseLog:
        """Append a dose log event to an active prescription.

        Args:
            prescription_id: Target prescription.
            event: 'taken' or 'skipped'.
            timestamp: Optional ISO 8601 timestamp; defaults to now (UTC).
            notes: Optional free-text notes.

        Raises:
            ValueError: For unknown event, nonexistent prescription, or a
                discontinued/completed prescription.
        """
        # Validate event
        try:
            dose_event = DoseEvent(event)
        except ValueError as exc:
            raise ValueError(
                f"event must be 'taken' or 'skipped', got '{event}'"
            ) from exc

        # Validate timestamp (if provided) is ISO 8601 with timezone
        if timestamp is None:
            timestamp = datetime.now(timezone.utc).isoformat()
        else:
            self._validate_timestamp(timestamp)

        # Prescription must exist and be active
        prescription = self.prescription_service.get_prescription(prescription_id)
        if prescription.status.value != "active":
            raise ValueError(
                f"Cannot append dose logs to a prescription with status "
                f"'{prescription.status.value}'"
            )

        log = DoseLog(
            prescription_id=prescription_id,
            event=dose_event,
            timestamp=timestamp,
            notes=notes,
        )
        return self.repository.append(log)

    def get_adherence_history(
        self,
        prescription_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[DoseLog]:
        """Return dose adherence history for a prescription ordered by time."""
        # Validate the prescription exists (404 if not)
        self.prescription_service.get_prescription(prescription_id)
        return self.repository.get_history(
            prescription_id, start_date=start_date, end_date=end_date
        )

    @staticmethod
    def _validate_timestamp(timestamp: str) -> None:
        """Reject non-ISO-8601 or naive (no timezone) timestamps."""
        if not isinstance(timestamp, str) or not timestamp.strip():
            raise ValueError("timestamp must be a non-empty ISO 8601 string")
        # Normalize a trailing 'Z' (UTC) to '+00:00' so fromisoformat accepts
        # it on Python versions that don't handle 'Z' natively.
        normalized = timestamp
        if normalized.rstrip().endswith("Z"):
            normalized = normalized.rstrip()[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise ValueError(
                f"timestamp must be a valid ISO 8601 datetime: {timestamp}"
            ) from exc
        if parsed.tzinfo is None:
            raise ValueError(
                f"timestamp must include timezone information: {timestamp}"
            )