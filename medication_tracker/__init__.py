"""Prescription tracker: validation and data-access layer.

Public surface:
    - ``Prescription`` / ``PrescriptionStatus`` from :mod:`medication_tracker.models`
    - ``validate_prescription`` / ``ValidationError`` from :mod:`medication_tracker.validators`
    - ``PrescriptionRepository`` from :mod:`medication_tracker.repository`
"""

from medication_tracker.errors import ValidationError

from medication_tracker.models import Prescription, PrescriptionStatus

from medication_tracker.repository import PrescriptionRepository, PrescriptionNotFoundError

from medication_tracker.validators import validate_prescription

from .database import Database, get_database

from .models import (
    DoseEvent,
    DoseLog,
    Prescription,
    PrescriptionStatus,
    StatusTransition,
)

from .repository import PrescriptionNotFoundError, PrescriptionRepository

from .prescription_service import PrescriptionService

from .dose_log_repository import PrescriptionDoseLogRepository

from .dose_log_service import DoseLogService



__all__ = [
    "Prescription",
    "PrescriptionStatus",
    "ValidationError",
    "validate_prescription",
    "PrescriptionRepository",
    "PrescriptionNotFoundError",
    "Database",
    "get_database",
    "DoseEvent",
    "DoseLog",
    "StatusTransition",
    "PrescriptionService",
    "PrescriptionDoseLogRepository",
    "DoseLogService",
]
