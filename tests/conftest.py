"""Pytest configuration and fixtures for prescription tracker tests."""

import pytest

from uuid import uuid4

from medication_tracker import (
    DoseLogService,
    PrescriptionDoseLogRepository,
    PrescriptionRepository,
    PrescriptionService,
    get_database,
)



@pytest.fixture
def database():
    """Create an in-memory database with the schema initialized."""
    from prescription_tracker.database import Database, get_database

    db = get_database(":memory:") if 'get_database' in globals() or 'get_database' in locals() else Database(":memory:")
    db.init_schema()
    yield db
    db.close()

@pytest.fixture
def repository(database):
    """Create a PrescriptionRepository backed by the in-memory database."""
    from prescription_tracker.repository import PrescriptionRepository

    return PrescriptionRepository(database)

@pytest.fixture
def service(database):
    """Create a PrescriptionService backed by the in-memory database."""
    from prescription_tracker.service import PrescriptionService

    return PrescriptionService(database)

@pytest.fixture
def patient_id():
    """A stable patient UUID for tests."""
    return uuid4()

@pytest.fixture
def doctor_id():
    """A stable doctor UUID for tests."""
    return uuid4()

@pytest.fixture
def valid_rx_data(patient_id, doctor_id):
    """Minimal valid prescription request payload."""
    return {
        "patient_id": str(patient_id),
        "doctor_id": str(doctor_id),
        "medicine_name": "Amoxicillin",
        "dosage_amount": "500",
        "dosage_unit": "mg",
        "frequency": "three times daily",
        "start_date": "2026-01-01T08:00:00+00:00",
    }

@pytest.fixture
def valid_prescription(patient_id, doctor_id):
    """A Prescription model instance ready to persist."""
    from prescription_tracker.models import Prescription

    return Prescription(
        patient_id=patient_id,
        doctor_id=doctor_id,
        medicine_name="Amoxicillin",
        dosage_amount="500",
        dosage_unit="mg",
        frequency="three times daily",
        start_date="2026-01-01T08:00:00+00:00",
    )

@pytest.fixture
def dose_log_repository(database):
    return PrescriptionDoseLogRepository(database)

@pytest.fixture
def prescription_service(repository):
    return PrescriptionService(repository)

@pytest.fixture
def dose_log_service(dose_log_repository, prescription_service):
    return DoseLogService(dose_log_repository, prescription_service)

def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()

@pytest.fixture
def valid_prescription_data():
    """Return a dict of valid prescription fields for create_prescription."""
    return {
        "patient_id": "patient-1",
        "doctor_id": "doctor-1",
        "medicine_name": "Amoxicillin",
        "dosage_amount": 500.0,
        "dosage_unit": "mg",
        "frequency": "three times daily",
        "start_date": _now_iso(),
        "end_date": None,
        "status": "active",
    }

@pytest.fixture
def active_prescription(prescription_service, valid_prescription_data):
    """Create and return an active prescription."""
    return prescription_service.create_prescription(valid_prescription_data)
