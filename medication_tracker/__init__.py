"""Medicine tracker package.

Tracks prescribed medications: CRUD operations, timestamped dose records,
list views with status filtering, and data persistence verification with
edge-case handling for past end dates and overlapping schedules.
"""

from medication_tracker.db import Database, get_db
from medication_tracker.models import Medication, DoseRecord
from medication_tracker.service import MedicationService, ValidationError
from medication_tracker.persistence import verify_persistence, recover_corrupted

__all__ = [
    "Database",
    "get_db",
    "Medication",
    "DoseRecord",
    "MedicationService",
    "ValidationError",
    "verify_persistence",
    "recover_corrupted",
]