"""Tests for medication API endpoints."""

import pytest
from datetime import date, timedelta
from uuid import uuid4, UUID

from api.routes.medications import (
    MedicationAPI,
    MedicationCreate,
    MedicationUpdate,
    ErrorResponse,
)
from medication_tracker import get_database, MedicationRepository
from medication_tracker.models import Medication, MedicationStatus


@pytest.fixture
def database():
    """Create an in-memory database for testing."""
    db = get_database(":memory:")
    db.init_schema()
    yield db
    db.close()


@pytest.fixture
def repository(database):
    """Create a medication repository for testing."""
    return MedicationRepository(database)


@pytest.fixture
def api(repository):
    """Create a MedicationAPI instance for testing."""
    return MedicationAPI(repository)


class TestMedicationCreateValidation:
    """Tests for MedicationCreate request validation."""

    def test_valid_medication_create(self):
        """MedicationCreate accepts valid data."""
        data = MedicationCreate(
            name="Amoxicillin",
            dosage="500mg",
            frequency="twice daily",
        )
        assert data.name == "Amoxicillin"
        assert data.dosage == "500mg"
        assert data.frequency == "twice daily"
        assert data.status == "active"

    def test_medication_create_with_all_fields(self):
        """MedicationCreate accepts all optional fields."""
        data = MedicationCreate(
            name="Ibuprofen",
            dosage="400mg",
            frequency="every 6 hours",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 14),
            status="completed",
        )
        assert data.name == "Ibuprofen"
        assert data.status == "completed"

    def test_medication_create_fails_without_name(self):
        """MedicationCreate rejects empty name."""
        with pytest.raises(Exception) as exc_info:
            MedicationCreate(
                name="",
                dosage="500mg",
                frequency="twice daily",
            )
        # Pydantic raises validation error for empty strings with min_length=1
        assert "name" in str(exc_info.value)

    def test_medication_create_fails_without_dosage(self):
        """MedicationCreate rejects empty dosage."""
        with pytest.raises(Exception) as exc_info:
            MedicationCreate(
                name="Amoxicillin",
                dosage="",
                frequency="twice daily",
            )
        # Pydantic raises validation error for empty strings with min_length=1
        assert "dosage" in str(exc_info.value)

    def test_medication_create_fails_without_frequency(self):
        """MedicationCreate rejects empty frequency."""
        with pytest.raises(Exception) as exc_info:
            MedicationCreate(
                name="Amoxicillin",
                dosage="500mg",
                frequency="",
            )
        # Pydantic raises validation error for empty strings with min_length=1
        assert "frequency" in str(exc_info.value)

    def test_medication_create_fails_with_whitespace_name(self):
        """MedicationCreate rejects whitespace-only name."""
        with pytest.raises(Exception) as exc_info:
            MedicationCreate(
                name="   ",
                dosage="500mg",
                frequency="twice daily",
            )
        assert "name must be a non-empty string" in str(exc_info.value)

    def test_medication_create_fails_with_invalid_status(self):
        """MedicationCreate rejects invalid status values."""
        with pytest.raises(Exception) as exc_info:
            MedicationCreate(
                name="Amoxicillin",
                dosage="500mg",
                frequency="twice daily",
                status="invalid",
            )
        assert "status must be 'active' or 'completed'" in str(exc_info.value)

    def test_medication_create_strips_whitespace(self):
        """MedicationCreate strips whitespace from fields."""
        data = MedicationCreate(
            name="  Amoxicillin  ",
            dosage="  500mg  ",
            frequency="  twice daily  ",
        )
        assert data.name == "Amoxicillin"
        assert data.dosage == "500mg"
        assert data.frequency == "twice daily"


class TestMedicationUpdateValidation:
    """Tests for MedicationUpdate request validation."""

    def test_medication_update_with_valid_data(self):
        """MedicationUpdate accepts valid partial data."""
        data = MedicationUpdate(name="Updated Name")
        assert data.name == "Updated Name"
        assert data.dosage is None

    def test_medication_update_rejects_empty_name(self):
        """MedicationUpdate rejects empty name."""
        with pytest.raises(Exception) as exc_info:
            MedicationUpdate(name="")
        # Pydantic raises validation error for empty strings with min_length=1
        assert "name" in str(exc_info.value)

    def test_medication_update_rejects_empty_dosage(self):
        """MedicationUpdate rejects empty dosage."""
        with pytest.raises(Exception) as exc_info:
            MedicationUpdate(dosage="")
        # Pydantic raises validation error for empty strings with min_length=1
        assert "dosage" in str(exc_info.value)

    def test_medication_update_rejects_empty_frequency(self):
        """MedicationUpdate rejects empty frequency."""
        with pytest.raises(Exception) as exc_info:
            MedicationUpdate(frequency="")
        # Pydantic raises validation error for empty strings with min_length=1
        assert "frequency" in str(exc_info.value)

    def test_medication_update_rejects_invalid_status(self):
        """MedicationUpdate rejects invalid status."""
        with pytest.raises(Exception) as exc_info:
            MedicationUpdate(status="invalid")
        assert "status must be 'active' or 'completed'" in str(exc_info.value)

    def test_medication_update_accepts_valid_status(self):
        """MedicationUpdate accepts valid status values."""
        data_active = MedicationUpdate(status="active")
        data_completed = MedicationUpdate(status="completed")
        assert data_active.status == "active"
        assert data_completed.status == "completed"


class TestMedicationAPICreate:
    """Tests for the create endpoint."""

    def test_create_medication_returns_201(self, api):
        """Creating a medication returns 201 status code."""
        data = MedicationCreate(
            name="Amoxicillin",
            dosage="500mg",
            frequency="twice daily",
        )
        response, status_code = api.create(data)
        assert status_code == 201
        assert response.name == "Amoxicillin"
        assert response.dosage == "500mg"

    def test_create_medication_persists_data(self, api, repository):
        """Created medication can be retrieved from database."""
        data = MedicationCreate(
            name="Test Med",
            dosage="100mg",
            frequency="daily",
        )
        response, _ = api.create(data)

        retrieved = repository.get_by_id(UUID(response.id))
        assert retrieved is not None
        assert retrieved.name == "Test Med"

    def test_create_medication_sets_default_status(self, api):
        """Created medication defaults to 'active' status."""
        data = MedicationCreate(
            name="Test Med",
            dosage="100mg",
            frequency="daily",
        )
        response, _ = api.create(data)
        assert response.status == "active"


class TestMedicationAPIGetAll:
    """Tests for the get all endpoint."""

    def test_get_all_returns_200(self, api):
        """Getting all medications returns 200 status code."""
        response, status_code = api.get_all()
        assert status_code == 200
        assert isinstance(response, list)

    def test_get_all_returns_sorted_list(self, api):
        """Medications are sorted by created_at descending."""
        import time

        api.create(MedicationCreate(name="First", dosage="100mg", frequency="daily"))
        time.sleep(0.01)
        api.create(MedicationCreate(name="Second", dosage="200mg", frequency="daily"))
        time.sleep(0.01)
        api.create(MedicationCreate(name="Third", dosage="300mg", frequency="daily"))

        response, _ = api.get_all()

        assert len(response) == 3
        assert response[0].name == "Third"
        assert response[1].name == "Second"
        assert response[2].name == "First"

    def test_get_all_filters_by_status(self, api):
        """Can filter medications by status."""
        api.create(MedicationCreate(name="Active Med", dosage="100mg", frequency="daily"))
        api.create(
            MedicationCreate(
                name="Completed Med",
                dosage="200mg",
                frequency="daily",
                status="completed",
            )
        )

        active_response, _ = api.get_all(status="active")
        completed_response, _ = api.get_all(status="completed")

        assert len(active_response) == 1
        assert active_response[0].name == "Active Med"
        assert len(completed_response) == 1
        assert completed_response[0].name == "Completed Med"


class TestMedicationAPIGetById:
    """Tests for the get by ID endpoint."""

    def test_get_by_id_returns_200(self, api):
        """Getting a medication by ID returns 200."""
        data = MedicationCreate(name="Test Med", dosage="100mg", frequency="daily")
        created, _ = api.create(data)

        response, status_code = api.get_by_id(created.id)
        assert status_code == 200
        assert response.name == "Test Med"

    def test_get_by_id_returns_404_for_nonexistent(self, api):
        """Getting a non-existent medication raises ValueError (404)."""
        with pytest.raises(ValueError) as exc_info:
            api.get_by_id(str(uuid4()))
        assert "not found" in str(exc_info.value).lower()

    def test_get_by_id_rejects_invalid_uuid(self, api):
        """Invalid UUID format raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            api.get_by_id("invalid-uuid")
        assert "Invalid medication ID format" in str(exc_info.value)


class TestMedicationAPIUpdate:
    """Tests for the update endpoint."""

    def test_update_returns_200(self, api):
        """Updating a medication returns 200."""
        data = MedicationCreate(name="Original", dosage="100mg", frequency="daily")
        created, _ = api.create(data)

        update_data = MedicationUpdate(name="Updated")
        response, status_code = api.update(created.id, update_data)

        assert status_code == 200
        assert response.name == "Updated"

    def test_update_persists_changes(self, api, repository):
        """Updated medication persists to database."""
        data = MedicationCreate(name="Original", dosage="100mg", frequency="daily")
        created, _ = api.create(data)

        update_data = MedicationUpdate(name="Updated", dosage="200mg")
        api.update(created.id, update_data)

        retrieved = repository.get_by_id(UUID(created.id))
        assert retrieved.name == "Updated"
        assert retrieved.dosage == "200mg"

    def test_update_returns_404_for_nonexistent(self, api):
        """Updating a non-existent medication raises ValueError (404)."""
        update_data = MedicationUpdate(name="Updated")
        with pytest.raises(ValueError) as exc_info:
            api.update(str(uuid4()), update_data)
        assert "not found" in str(exc_info.value).lower()

    def test_update_status_active_to_completed(self, api):
        """Can update status from active to completed."""
        data = MedicationCreate(name="Test Med", dosage="100mg", frequency="daily")
        created, _ = api.create(data)
        assert created.status == "active"

        update_data = MedicationUpdate(status="completed")
        response, _ = api.update(created.id, update_data)
        assert response.status == "completed"

        retrieved, _ = api.get_by_id(created.id)
        assert retrieved.status == "completed"


class TestMedicationAPIDelete:
    """Tests for the delete endpoint."""

    def test_delete_returns_204(self, api):
        """Deleting a medication returns 204."""
        data = MedicationCreate(name="ToDelete", dosage="100mg", frequency="daily")
        created, _ = api.create(data)

        _, status_code = api.delete(created.id)
        assert status_code == 204

    def test_delete_removes_from_database(self, api, repository):
        """Deleted medication cannot be retrieved."""
        data = MedicationCreate(name="ToDelete", dosage="100mg", frequency="daily")
        created, _ = api.create(data)

        api.delete(created.id)
        retrieved = repository.get_by_id(UUID(created.id))
        assert retrieved is None

    def test_delete_returns_404_for_nonexistent(self, api):
        """Deleting a non-existent medication raises ValueError (404)."""
        with pytest.raises(ValueError) as exc_info:
            api.delete(str(uuid4()))
        assert "not found" in str(exc_info.value).lower()


class TestMedicationAPIErrorHandling:
    """Tests for error handling in API endpoints."""

    def test_create_with_validation_error(self, api):
        """Create endpoint handles validation errors."""
        # Pydantic validation happens at construction time, so we test with invalid data
        # that passes construction but fails model validation
        with pytest.raises(Exception) as exc_info:
            # This will fail pydantic validation at construction
            MedicationCreate(name="", dosage="100mg", frequency="daily")
        # Pydantic raises ValidationError for empty strings
        assert "name" in str(exc_info.value)

    def test_update_with_invalid_uuid(self, api):
        """Update endpoint handles invalid UUID format."""
        update_data = MedicationUpdate(name="Updated")
        with pytest.raises(ValueError) as exc_info:
            api.update("not-a-uuid", update_data)
        assert "Invalid medication ID format" in str(exc_info.value)

    def test_delete_with_invalid_uuid(self, api):
        """Delete endpoint handles invalid UUID format."""
        with pytest.raises(ValueError) as exc_info:
            api.delete("not-a-uuid")
        assert "Invalid medication ID format" in str(exc_info.value)

    def test_get_with_invalid_uuid(self, api):
        """Get endpoint handles invalid UUID format."""
        with pytest.raises(ValueError) as exc_info:
            api.get_by_id("not-a-uuid")
        assert "Invalid medication ID format" in str(exc_info.value)
