"""Pytest configuration and fixtures for medication tracker tests."""

import os
import pytest
from pathlib import Path


@pytest.fixture(scope="session", autouse=True)
def capture_evidence(request):
    """Capture test execution evidence for E2E artifacts."""
    # Only capture when running functional tests via npm test -- --grep
    config = request.config
    keyword_expr = getattr(config.option, 'keyword', '')

    # Check if we're running functional tests
    if 'functional' in keyword_expr.lower() or 'TestFunctional' in keyword_expr:
        evidence_dir = Path(__file__).parent.parent / '.see' / 'e2e-artifacts'
        evidence_dir.mkdir(parents=True, exist_ok=True)

        # The transcript will be written by the test runner
        os.environ['EVIDENCE_DIR'] = str(evidence_dir)


@pytest.fixture
def database():
    """Create an in-memory database for testing."""
    from medication_tracker import get_database

    db = get_database(":memory:")
    db.init_schema()
    yield db
    db.close()


@pytest.fixture
def repository(database):
    """Create a medication repository for testing."""
    from medication_tracker import MedicationRepository

    return MedicationRepository(database)


@pytest.fixture
def dose_service(database):
    """Create a dose service for testing."""
    from medication_tracker import DoseService

    return DoseService(database)
