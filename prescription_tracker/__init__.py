"""Prescription Tracker - Track patient prescriptions with lifecycle management.

Exposes both the Flask service stack (models, database, repository, service,
Flask API) and the FastAPI stack (Pydantic-style create models, validation
layer, SQLite repository) so callers can reach either layer.
"""

from .models import (
    Prescription,
    PrescriptionStatus,
    StatusTransition,
    DoseLog,
    DoseStatus,
    PrescriptionCreate,
    DoseLogCreate,
    ValidationError,
)
from .database import Database, get_database
from .repository import PrescriptionRepository
from .service import PrescriptionService, ConflictError
from .api import create_app

__all__ = [
    "Prescription",
    "PrescriptionStatus",
    "StatusTransition",
    "DoseLog",
    "DoseStatus",
    "PrescriptionCreate",
    "DoseLogCreate",
    "ValidationError",
    "Database",
    "get_database",
    "PrescriptionRepository",
    "PrescriptionService",
    "ConflictError",
    "create_app",
]