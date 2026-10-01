"""Pytest configuration and shared fixtures."""

import pytest

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
    db = get_database(":memory:")
    db.init_schema()
    yield db
    db.close()


@pytest.fixture
def repository(database):
    return PrescriptionRepository(database)


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