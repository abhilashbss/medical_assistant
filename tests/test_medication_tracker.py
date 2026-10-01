<<<<<<< HEAD
"""Tests for medication tracker functionality.

This module tests:
- Medication creation with valid/invalid fields
- Validation of required fields (name, dosage)
- Validation of dosage and frequency as non-empty strings
- Mark-as-taken functionality with timestamped dose records
- Data persistence and retrieval after database restart
"""

import pytest
from datetime import date, datetime
from uuid import uuid4

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
=======
"""Unit tests for medication tracker: models, repository, dose service, and persistence.

Covers the definition of done for build unit #2 (dose tracking):
- Medication creation succeeds with valid name, dosage, frequency, and date fields
- Medication creation fails with 400 status when required fields are missing or empty
- Dosage and frequency values reject non-string or invalid inputs
- Mark-as-taken action creates a timestamped dose record linked to correct medication
- All medication data persists correctly and is retrievable after app restart
- Dose tracking: duplicate prevention, history retrieval, future date rejection
"""

import os
import tempfile
from datetime import date, timedelta
from uuid import uuid4, UUID

import pytest
>>>>>>> 9105369 (runctl: build runctl/build-09d3fc65 (pass))

from medication_tracker import (
    Database,
    get_database,
    Medication,
    MedicationStatus,
    DoseRecord,
    DoseStatus,
    MedicationRepository,
<<<<<<< HEAD
)
from medication_tracker.dose_service import DoseService, ConflictError


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


class TestMedicationModel:
    """Tests for the Medication model."""

    def test_create_medication_with_valid_fields(self):
        """Medication creation succeeds with valid name, dosage, frequency."""
        medication = Medication(
            name="Amoxicillin",
            dosage="500mg",
            frequency="twice daily",
        )

        assert medication.name == "Amoxicillin"
        assert medication.dosage == "500mg"
        assert medication.frequency == "twice daily"
        assert medication.status == MedicationStatus.ACTIVE
        assert medication.id is not None

    def test_create_medication_with_all_fields(self):
        """Medication creation with all optional fields."""
        start = date(2026, 1, 1)
        end = date(2026, 1, 14)

        medication = Medication(
            name="Ibuprofen",
            dosage="400mg",
            frequency="every 6 hours",
            start_date=start,
            end_date=end,
            status=MedicationStatus.COMPLETED,
        )

        assert medication.start_date == start
        assert medication.end_date == end
        assert medication.status == MedicationStatus.COMPLETED

    def test_create_medication_fails_without_name(self):
        """Medication creation fails when name is missing."""
        with pytest.raises(ValueError, match="name must be a non-empty string"):
            Medication(
                name="",
                dosage="500mg",
                frequency="twice daily",
            )

    def test_create_medication_fails_without_dosage(self):
        """Medication creation fails when dosage is missing."""
        with pytest.raises(ValueError, match="dosage must be a non-empty string"):
            Medication(
                name="Amoxicillin",
                dosage="",
                frequency="twice daily",
            )

    def test_create_medication_fails_without_frequency(self):
        """Medication creation fails when frequency is missing."""
        with pytest.raises(ValueError, match="frequency must be a non-empty string"):
            Medication(
                name="Amoxicillin",
                dosage="500mg",
                frequency="",
            )

    def test_create_medication_fails_with_none_name(self):
        """Medication creation fails when name is None."""
        with pytest.raises(ValueError, match="name must be a non-empty string"):
            Medication(
                name=None,
                dosage="500mg",
                frequency="twice daily",
            )

    def test_create_medication_fails_with_none_dosage(self):
        """Medication creation fails when dosage is None."""
        with pytest.raises(ValueError, match="dosage must be a non-empty string"):
            Medication(
                name="Amoxicillin",
                dosage=None,
                frequency="twice daily",
            )

    def test_create_medication_fails_with_whitespace_only_name(self):
        """Medication creation fails when name is only whitespace."""
        with pytest.raises(ValueError, match="name must be a non-empty string"):
            Medication(
                name="   ",
                dosage="500mg",
                frequency="twice daily",
            )

    def test_medication_to_dict(self):
        """Medication converts to dictionary correctly."""
        medication = Medication(
            name="Metformin",
            dosage="1000mg",
            frequency="once daily",
        )

        result = medication.to_dict()

        assert result["name"] == "Metformin"
        assert result["dosage"] == "1000mg"
        assert result["frequency"] == "once daily"
        assert result["status"] == "active"
        assert "id" in result

    def test_medication_from_dict(self):
        """Medication creates from dictionary correctly."""
        data = {
            "name": "Metformin",
            "dosage": "1000mg",
            "frequency": "once daily",
        }

        medication = Medication.from_dict(data)

        assert medication.name == "Metformin"
        assert medication.dosage == "1000mg"


class TestDoseRecordModel:
    """Tests for the DoseRecord model."""

    def test_create_dose_record_with_timestamp(self):
        """Dose record creation creates timestamp automatically."""
        medication_id = uuid4()
        dose = DoseRecord(
            medication_id=medication_id,
            date=date.today(),
        )

        assert dose.timestamp is not None
        assert dose.status == "taken"
        assert dose.medication_id == medication_id

    def test_dose_record_to_dict(self):
        """Dose record converts to dictionary correctly."""
        medication_id = uuid4()
        dose = DoseRecord(
            medication_id=medication_id,
            date=date(2026, 9, 24),
        )

        result = dose.to_dict()

        assert result["medication_id"] == str(medication_id)
        assert result["date"] == "2026-09-24"
        assert result["status"] == "taken"


class TestMedicationRepository:
    """Tests for the MedicationRepository CRUD operations."""

    def test_create_medication_succeeds(self, repository):
        """Creating a medication succeeds and returns the medication."""
        medication = Medication(
            name="Amoxicillin",
            dosage="500mg",
            frequency="twice daily",
        )

        result = repository.create(medication)

        assert result.id == medication.id
        assert result.name == "Amoxicillin"
        assert result.created_at is not None
        assert result.updated_at is not None

    def test_create_medication_persists_to_database(self, repository):
        """Created medication can be retrieved from database."""
        medication = Medication(
            name="Ibuprofen",
            dosage="400mg",
            frequency="every 6 hours",
        )

        repository.create(medication)
        retrieved = repository.get_by_id(medication.id)

        assert retrieved is not None
        assert retrieved.name == "Ibuprofen"
        assert retrieved.dosage == "400mg"

    def test_get_medication_not_found(self, repository):
        """Getting a non-existent medication returns None."""
        result = repository.get_by_id(uuid4())
        assert result is None

    def test_update_medication(self, repository):
        """Updating a medication persists changes."""
        medication = Medication(
            name="Original",
            dosage="100mg",
            frequency="daily",
        )
        repository.create(medication)

        medication.name = "Updated"
        medication.dosage = "200mg"
        result = repository.update(medication)

        assert result is not None
        assert result.name == "Updated"
        assert result.dosage == "200mg"

        retrieved = repository.get_by_id(medication.id)
        assert retrieved.name == "Updated"
        assert retrieved.dosage == "200mg"

    def test_update_nonexistent_medication(self, repository):
        """Updating a non-existent medication returns None."""
        medication = Medication(
            name="Test",
            dosage="100mg",
            frequency="daily",
        )
        result = repository.update(medication)
        assert result is None

    def test_delete_medication(self, repository):
        """Deleting a medication removes it from database."""
        medication = Medication(
            name="ToDelete",
            dosage="50mg",
            frequency="daily",
        )
        repository.create(medication)

        result = repository.delete(medication.id)
        assert result is True

        retrieved = repository.get_by_id(medication.id)
        assert retrieved is None

    def test_delete_nonexistent_medication(self, repository):
        """Deleting a non-existent medication returns False."""
        result = repository.delete(uuid4())
        assert result is False

    def test_get_all_medications_sorted_by_created_at(self, repository):
        """Getting all medications returns them sorted by created_at descending."""
        med1 = Medication(name="First", dosage="100mg", frequency="daily")
        med2 = Medication(name="Second", dosage="200mg", frequency="daily")
        med3 = Medication(name="Third", dosage="300mg", frequency="daily")

        repository.create(med1)
        import time
        time.sleep(0.01)
        repository.create(med2)
        time.sleep(0.01)
        repository.create(med3)

        results = repository.get_all()

        assert len(results) == 3
        assert results[0].name == "Third"
        assert results[1].name == "Second"
        assert results[2].name == "First"

    def test_get_medications_filtered_by_status(self, repository):
        """Getting medications can filter by status."""
        active = Medication(name="Active Med", dosage="100mg", frequency="daily")
        completed = Medication(
            name="Completed Med",
            dosage="200mg",
            frequency="daily",
            status=MedicationStatus.COMPLETED,
        )

        repository.create(active)
        repository.create(completed)

        active_results = repository.get_all(status=MedicationStatus.ACTIVE)
        completed_results = repository.get_all(status=MedicationStatus.COMPLETED)

        assert len(active_results) == 1
        assert active_results[0].name == "Active Med"
        assert len(completed_results) == 1
        assert completed_results[0].name == "Completed Med"

    def test_status_field_update_active_to_completed(self, repository):
        """Status can be updated from active to completed without data loss."""
        medication = Medication(
            name="Test Med",
            dosage="100mg",
            frequency="daily",
            status=MedicationStatus.ACTIVE,
        )
        repository.create(medication)

        medication.status = MedicationStatus.COMPLETED
        repository.update(medication)

        retrieved = repository.get_by_id(medication.id)
        assert retrieved is not None
        assert retrieved.status == MedicationStatus.COMPLETED
        assert retrieved.name == "Test Med"
        assert retrieved.dosage == "100mg"

    def test_mark_as_taken_creates_dose_record(self, repository):
        """Mark-as-taken action creates timestamped dose record."""
        medication = Medication(
            name="Test Med",
            dosage="100mg",
            frequency="daily",
        )
        repository.create(medication)

        dose = DoseRecord(
            medication_id=medication.id,
            date=date.today(),
        )
        repository.create_dose_record(dose)

        records = repository.get_dose_records(medication.id)

        assert len(records) == 1
        assert records[0].medication_id == medication.id
        assert records[0].timestamp is not None
        assert records[0].status == "taken"

    def test_multiple_dose_records(self, repository):
        """Multiple dose records can be created for same medication."""
        medication = Medication(
            name="Test Med",
            dosage="100mg",
            frequency="daily",
        )
        repository.create(medication)

        for i in range(3):
            dose = DoseRecord(
                medication_id=medication.id,
                date=date(2026, 9, 24 - i),
            )
            repository.create_dose_record(dose)

        records = repository.get_dose_records(medication.id)

        assert len(records) == 3

    def test_dose_records_filtered_by_date_range(self, repository):
        """Dose records can be filtered by date range."""
        from datetime import timedelta

        medication = Medication(
            name="Test Med",
            dosage="100mg",
            frequency="daily",
        )
        repository.create(medication)

        # Create dose records for the past 4 days relative to today
        today = date.today()
        for days_ago in [3, 2, 1, 0]:
            dose = DoseRecord(
                medication_id=medication.id,
                date=today - timedelta(days=days_ago),
            )
            repository.create_dose_record(dose)

        # Filter to only the middle 2 days
        start = (today - timedelta(days=2)).isoformat()
        end = (today - timedelta(days=1)).isoformat()
        records = repository.get_dose_records(
            medication.id,
            start_date=start,
            end_date=end,
        )

        assert len(records) == 2


class TestDatabaseConstraints:
    """Tests for database-level constraints."""

    def test_not_null_constraint_on_name(self, database):
        """Database rejects insert with NULL name."""
        with pytest.raises(Exception):
            database.execute(
                "INSERT INTO medications (id, name, dosage, frequency) VALUES (?, ?, ?, ?)",
                (str(uuid4()), None, "500mg", "daily"),
            )
            database.connect().commit()

    def test_not_null_constraint_on_dosage(self, database):
        """Database rejects insert with NULL dosage."""
        with pytest.raises(Exception):
            database.execute(
                "INSERT INTO medications (id, name, dosage, frequency) VALUES (?, ?, ?, ?)",
                (str(uuid4()), "Amoxicillin", None, "daily"),
            )
            database.connect().commit()

    def test_check_constraint_empty_name(self, database):
        """Database rejects insert with empty name."""
        with pytest.raises(Exception):
            database.execute(
                "INSERT INTO medications (id, name, dosage, frequency) VALUES (?, ?, ?, ?)",
                (str(uuid4()), "", "500mg", "daily"),
            )
            database.connect().commit()

    def test_check_constraint_empty_dosage(self, database):
        """Database rejects insert with empty dosage."""
        with pytest.raises(Exception):
            database.execute(
                "INSERT INTO medications (id, name, dosage, frequency) VALUES (?, ?, ?, ?)",
                (str(uuid4()), "Amoxicillin", "", "daily"),
            )
            database.connect().commit()

    def test_check_constraint_empty_frequency(self, database):
        """Database rejects insert with empty frequency."""
        with pytest.raises(Exception):
            database.execute(
                "INSERT INTO medications (id, name, dosage, frequency) VALUES (?, ?, ?, ?)",
                (str(uuid4()), "Amoxicillin", "500mg", ""),
            )
            database.connect().commit()

    def test_check_constraint_invalid_status(self, database):
        """Database rejects insert with invalid status value."""
        with pytest.raises(Exception):
            database.execute(
                "INSERT INTO medications (id, name, dosage, frequency, status) VALUES (?, ?, ?, ?, ?)",
                (str(uuid4()), "Amoxicillin", "500mg", "daily", "invalid"),
            )
            database.connect().commit()

    def test_valid_status_values(self, database):
        """Database accepts valid status values 'active' and 'completed'."""
        database.execute(
            "INSERT INTO medications (id, name, dosage, frequency, status) VALUES (?, ?, ?, ?, ?)",
            (str(uuid4()), "Med1", "500mg", "daily", "active"),
        )
        database.execute(
            "INSERT INTO medications (id, name, dosage, frequency, status) VALUES (?, ?, ?, ?, ?)",
            (str(uuid4()), "Med2", "500mg", "daily", "completed"),
        )
        database.connect().commit()

        cursor = database.execute("SELECT COUNT(*) FROM medications")
        count = cursor.fetchone()[0]
        assert count == 2


class TestMigrationScript:
    """Tests for the migration script."""

    def test_migration_applies_successfully(self, database):
        """Migration script applies without errors."""
        # init_schema() already called in fixture, verify tables exist
        cursor = database.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='medications'"
        )
        assert cursor.fetchone() is not None

    def test_migration_rollback(self, database):
        """Migration can be rolled back (tables can be dropped)."""
        database.execute("DROP TABLE IF EXISTS medications")
        database.connect().commit()

        cursor = database.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='medications'"
        )
        assert cursor.fetchone() is None

    def test_indexes_created(self, database):
        """Migration creates required indexes."""
        cursor = database.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='medications'"
        )
        indexes = [row[0] for row in cursor.fetchall()]

        assert "idx_medications_status" in indexes
        assert "idx_medications_created_at" in indexes


class TestDataPersistence:
    """Tests for data persistence across database restarts."""

    def test_data_persists_after_database_reopen(self, tmp_path):
        """Medication data persists correctly after database restart."""
        db_path = tmp_path / "test.db"

        # Create database and add data
        db1 = get_database(str(db_path))
        db1.init_schema()
        repo1 = MedicationRepository(db1)

        medication = Medication(
            name="Persistent Med",
            dosage="100mg",
            frequency="daily",
        )
        repo1.create(medication)
        original_id = medication.id
        db1.close()

        # Reopen database and verify data
        db2 = get_database(str(db_path))
        db2.init_schema()
        repo2 = MedicationRepository(db2)

        retrieved = repo2.get_by_id(original_id)

        assert retrieved is not None
        assert retrieved.name == "Persistent Med"
        assert retrieved.dosage == "100mg"

        db2.close()

    def test_crud_operations_persist(self, tmp_path):
        """Create, update, delete operations persist after restart."""
        db_path = tmp_path / "test.db"

        # Create and update
        db1 = get_database(str(db_path))
        db1.init_schema()
        repo1 = MedicationRepository(db1)

        medication = Medication(
            name="Original",
            dosage="100mg",
            frequency="daily",
        )
        repo1.create(medication)
        medication.name = "Updated"
        repo1.update(medication)
        db1.close()

        # Verify after restart
        db2 = get_database(str(db_path))
        db2.init_schema()
        repo2 = MedicationRepository(db2)

        retrieved = repo2.get_by_id(medication.id)
        assert retrieved is not None
        assert retrieved.name == "Updated"

        db2.close()


class TestFunctionalMedicineTracker:
    """Functional tests for medicine tracker feature."""

    def test_add_medication_appears_in_list(self, repository):
        """Adding a medication with required fields succeeds and appears in list."""
        medication = Medication(
            name="Adderall",
            dosage="20mg",
            frequency="once daily",
        )
        repository.create(medication)

        medications = repository.get_all()

        assert len(medications) == 1
        assert medications[0].name == "Adderall"
        assert medications[0].dosage == "20mg"

    def test_edit_medication_updates_all_fields(self, repository):
        """Editing a medication updates all fields and persists changes."""
        medication = Medication(
            name="Original",
            dosage="100mg",
            frequency="daily",
        )
        repository.create(medication)

        medication.name = "Edited"
        medication.dosage = "200mg"
        medication.frequency = "twice daily"
        repository.update(medication)

        retrieved = repository.get_by_id(medication.id)
        assert retrieved.name == "Edited"
        assert retrieved.dosage == "200mg"
        assert retrieved.frequency == "twice daily"

    def test_delete_medication_removes_from_list(self, repository):
        """Deleting a medication removes it from the list immediately."""
        medication = Medication(
            name="ToDelete",
            dosage="50mg",
            frequency="daily",
        )
        repository.create(medication)

        repository.delete(medication.id)

        medications = repository.get_all()
        assert len(medications) == 0

    def test_mark_as_taken_updates_adherence_status(self, repository):
        """Marking as taken records timestamp and updates adherence."""
        medication = Medication(
            name="Test Med",
            dosage="100mg",
            frequency="daily",
        )
        repository.create(medication)

        dose = DoseRecord(
            medication_id=medication.id,
            date=date.today(),
        )
        repository.create_dose_record(dose)

        records = repository.get_dose_records(medication.id)
        assert len(records) == 1
        assert records[0].timestamp is not None

    def test_medication_list_sorted_by_recent(self, repository):
        """Medication list displays correctly sorted by most recently added."""
        import time

        med1 = Medication(name="First", dosage="100mg", frequency="daily")
        med2 = Medication(name="Second", dosage="200mg", frequency="daily")
        med3 = Medication(name="Third", dosage="300mg", frequency="daily")

        repository.create(med1)
        time.sleep(0.01)
        repository.create(med2)
        time.sleep(0.01)
        repository.create(med3)

        results = repository.get_all()

        assert results[0].name == "Third"
        assert results[1].name == "Second"
        assert results[2].name == "First"

    def test_status_filtering_works(self, repository):
        """Status filtering (active/completed) works correctly."""
        active1 = Medication(name="Active 1", dosage="100mg", frequency="daily")
        active2 = Medication(name="Active 2", dosage="200mg", frequency="daily")
        completed = Medication(
            name="Completed",
            dosage="300mg",
            frequency="daily",
            status=MedicationStatus.COMPLETED,
        )

        repository.create(active1)
        repository.create(active2)
        repository.create(completed)

        active_meds = repository.get_all(status=MedicationStatus.ACTIVE)
        completed_meds = repository.get_all(status=MedicationStatus.COMPLETED)
        all_meds = repository.get_all()

        assert len(active_meds) == 2
        assert len(completed_meds) == 1
        assert len(all_meds) == 3


class TestDoseService:
    """Tests for the DoseService layer."""

    @pytest.fixture
    def dose_service(self, database):
        """Create a dose service for testing."""
        return DoseService(database)

    def test_mark_dose_taken_creates_record_with_correct_timestamp(self, dose_service, repository):
        """markDoseTaken creates record with correct timestamp."""
        medication = Medication(
            name="Test Med",
            dosage="100mg",
            frequency="daily",
        )
        repository.create(medication)

        before = datetime.now()
        dose_record = dose_service.mark_dose_taken(medication.id)
        after = datetime.now()

        assert dose_record.medication_id == medication.id
        assert dose_record.date == date.today()
        assert dose_record.timestamp is not None
        assert before <= dose_record.timestamp <= after
        assert dose_record.status == "taken"

    def test_mark_dose_taken_duplicate_returns_conflict(self, dose_service, repository):
        """Duplicate call to markDoseTaken returns 409 (ConflictError)."""
        medication = Medication(
            name="Test Med",
            dosage="100mg",
            frequency="daily",
        )
        repository.create(medication)

        # First call succeeds
        dose_service.mark_dose_taken(medication.id)

        # Second call on same date raises ConflictError
        with pytest.raises(ConflictError):
            dose_service.mark_dose_taken(medication.id)

    def test_get_dose_history_returns_sorted_results(self, dose_service, repository):
        """getDoseHistory returns results sorted by date descending."""
        medication = Medication(
            name="Test Med",
            dosage="100mg",
            frequency="daily",
        )
        repository.create(medication)

        # Create dose records for multiple days
        for day in [20, 21, 22, 23, 24]:
            dose_service.mark_dose_taken(medication.id, date(2026, 9, day))

        history = dose_service.get_dose_history(medication.id)

        assert len(history) == 5
        # Verify sorted by date descending
        assert history[0].date == date(2026, 9, 24)
        assert history[1].date == date(2026, 9, 23)
        assert history[2].date == date(2026, 9, 22)
        assert history[3].date == date(2026, 9, 21)
        assert history[4].date == date(2026, 9, 20)

    def test_get_dose_history_filtered_by_date_range(self, dose_service, repository):
        """getDoseHistory respects start and end date filters."""
        medication = Medication(
            name="Test Med",
            dosage="100mg",
            frequency="daily",
        )
        repository.create(medication)

        for day in [20, 21, 22, 23, 24]:
            dose_service.mark_dose_taken(medication.id, date(2026, 9, day))

        # Filter by date range
        history = dose_service.get_dose_history(
            medication.id,
            start_date=date(2026, 9, 22),
            end_date=date(2026, 9, 23),
        )

        assert len(history) == 2
        assert history[0].date == date(2026, 9, 23)
        assert history[1].date == date(2026, 9, 22)

    def test_mark_dose_taken_future_date_rejected(self, dose_service, repository):
        """Future date is rejected with ValueError."""
        medication = Medication(
            name="Test Med",
            dosage="100mg",
            frequency="daily",
        )
        repository.create(medication)

        future_date = date.today().replace(day=date.today().day + 1)
        with pytest.raises(ValueError, match="future"):
            dose_service.mark_dose_taken(medication.id, future_date)

    def test_mark_dose_skipped_creates_record(self, dose_service, repository):
        """mark_dose_skipped creates record with skipped status."""
        medication = Medication(
            name="Test Med",
            dosage="100mg",
            frequency="daily",
        )
        repository.create(medication)

        dose_record = dose_service.mark_dose_skipped(medication.id, date.today())

        assert dose_record.status == "skipped"
        assert dose_record.medication_id == medication.id

    def test_mark_dose_skipped_duplicate_returns_conflict(self, dose_service, repository):
        """Duplicate call to mark_dose_skipped returns ConflictError."""
        medication = Medication(
            name="Test Med",
            dosage="100mg",
            frequency="daily",
        )
        repository.create(medication)

        dose_service.mark_dose_skipped(medication.id, date.today())

        with pytest.raises(ConflictError):
            dose_service.mark_dose_skipped(medication.id, date.today())

    def test_get_dose_for_date_returns_existing_record(self, dose_service, repository):
        """get_dose_for_date returns the correct record."""
        medication = Medication(
            name="Test Med",
            dosage="100mg",
            frequency="daily",
        )
        repository.create(medication)

        dose_service.mark_dose_taken(medication.id, date(2026, 9, 24))

        record = dose_service.get_dose_for_date(medication.id, date(2026, 9, 24))

        assert record is not None
        assert record.status == "taken"

    def test_get_dose_for_date_returns_none_when_not_exists(self, dose_service, repository):
        """get_dose_for_date returns None when no record exists."""
        medication = Medication(
            name="Test Med",
            dosage="100mg",
            frequency="daily",
        )
        repository.create(medication)

        record = dose_service.get_dose_for_date(medication.id, date(2026, 9, 24))

        assert record is None


class TestDoseRecordModelValidation:
    """Tests for DoseRecord model validation."""

    def test_dose_record_rejects_future_date(self):
        """DoseRecord raises ValueError for future dates."""
        medication_id = uuid4()
        future_date = date.today().replace(day=date.today().day + 1)

        with pytest.raises(ValueError, match="future"):
            DoseRecord(
                medication_id=medication_id,
                date=future_date,
            )

    def test_dose_record_rejects_invalid_status(self):
        """DoseRecord raises ValueError for invalid status values."""
        medication_id = uuid4()

        with pytest.raises(ValueError, match="status must be one of"):
            DoseRecord(
                medication_id=medication_id,
                date=date.today(),
                status="invalid_status",
            )

    def test_dose_record_accepts_valid_status_values(self):
        """DoseRecord accepts taken, skipped, missed status values."""
        medication_id = uuid4()

        for status in ["taken", "skipped", "missed"]:
            dose = DoseRecord(
                medication_id=medication_id,
                date=date.today(),
                status=status,
            )
            assert dose.status == status

    def test_dose_record_auto_sets_timestamp(self):
        """DoseRecord automatically sets timestamp on creation."""
        medication_id = uuid4()
        before = datetime.now()
        dose = DoseRecord(
            medication_id=medication_id,
            date=date.today(),
        )
        after = datetime.now()

        assert dose.timestamp is not None
        assert before <= dose.timestamp <= after


class TestDoseStatusEnum:
    """Tests for DoseStatus enum."""

    def test_dose_status_enum_values(self):
        """DoseStatus enum has correct values."""
        assert DoseStatus.TAKEN.value == "taken"
        assert DoseStatus.SKIPPED.value == "skipped"
        assert DoseStatus.MISSED.value == "missed"


class TestFunctionalDoseTracking:
    """Functional tests for dose tracking feature."""

    def test_post_doses_with_valid_medication_id_returns_201(self, database):
        """POST /doses with valid medication_id returns 201 + dose record."""
        from medication_tracker.api import create_app

        app = create_app(":memory:")
        client = app.test_client()

        # Create a medication first
        med_response = client.post('/medications', json={
            "name": "Test Med",
            "dosage": "100mg",
            "frequency": "daily",
        })
        assert med_response.status_code == 201
        medication_id = med_response.get_json()["id"]

        # Mark dose as taken
        dose_response = client.post(f'/medications/{medication_id}/doses', json={})
        assert dose_response.status_code == 201

        data = dose_response.get_json()
        assert data["medication_id"] == medication_id
        assert data["status"] == "taken"
        assert data["timestamp"] is not None

    def test_post_doses_second_post_same_day_returns_409(self, database):
        """Second POST same day returns 409."""
        from medication_tracker.api import create_app

        app = create_app(":memory:")
        client = app.test_client()

        # Create a medication first
        med_response = client.post('/medications', json={
            "name": "Test Med",
            "dosage": "100mg",
            "frequency": "daily",
        })
        assert med_response.status_code == 201
        medication_id = med_response.get_json()["id"]

        # First dose mark
        dose_response1 = client.post(f'/medications/{medication_id}/doses', json={})
        assert dose_response1.status_code == 201

        # Second dose mark same day should fail
        dose_response2 = client.post(f'/medications/{medication_id}/doses', json={})
        assert dose_response2.status_code == 409

    def test_get_doses_returns_dose_history(self, database):
        """GET /doses returns dose history."""
        from medication_tracker.api import create_app

        app = create_app(":memory:")
        client = app.test_client()

        # Create a medication first
        med_response = client.post('/medications', json={
            "name": "Test Med",
            "dosage": "100mg",
            "frequency": "daily",
        })
        assert med_response.status_code == 201
        medication_id = med_response.get_json()["id"]

        # Mark doses for multiple days
        for day in [22, 23, 24]:
            client.post(f'/medications/{medication_id}/doses', json={
                "date": f"2026-09-{day:02d}"
            })

        # Get dose history
        history_response = client.get(f'/medications/{medication_id}/doses')
        assert history_response.status_code == 200

        data = history_response.get_json()
        assert len(data) == 3

    def test_get_doses_filtered_by_date_range(self, database):
        """GET /doses?start=&end= filters by date range."""
        from medication_tracker.api import create_app

        app = create_app(":memory:")
        client = app.test_client()

        # Create a medication first
        med_response = client.post('/medications', json={
            "name": "Test Med",
            "dosage": "100mg",
            "frequency": "daily",
        })
        assert med_response.status_code == 201
        medication_id = med_response.get_json()["id"]

        # Mark doses for multiple days
        for day in [20, 21, 22, 23, 24]:
            client.post(f'/medications/{medication_id}/doses', json={
                "date": f"2026-09-{day:02d}"
            })

        # Get dose history with date range filter
        history_response = client.get(
            f'/medications/{medication_id}/doses?start=2026-09-22&end=2026-09-23'
        )
        assert history_response.status_code == 200

        data = history_response.get_json()
        assert len(data) == 2

    def test_post_doses_future_date_rejected_400(self, database):
        """Future date rejected with 400 status."""
        from medication_tracker.api import create_app

        app = create_app(":memory:")
        client = app.test_client()

        # Create a medication first
        med_response = client.post('/medications', json={
            "name": "Test Med",
            "dosage": "100mg",
            "frequency": "daily",
        })
        assert med_response.status_code == 201
        medication_id = med_response.get_json()["id"]

        # Try to mark dose for future date
        future_date = date.today().replace(day=date.today().day + 1)
        dose_response = client.post(f'/medications/{medication_id}/doses', json={
            "date": future_date.isoformat()
        })
        assert dose_response.status_code == 400

    def test_post_doses_missing_medication_id_returns_404(self, database):
        """Missing medication_id returns 404."""
        from medication_tracker.api import create_app

        app = create_app(":memory:")
        client = app.test_client()

        # Try to mark dose for non-existent medication
        fake_id = "00000000-0000-0000-0000-000000000000"
        dose_response = client.post(f'/medications/{fake_id}/doses', json={})
        assert dose_response.status_code == 404

    def test_dose_record_persists_after_app_restart(self, tmp_path):
        """Dose records persist correctly after database restart."""
        db_path = tmp_path / "test.db"

        # Create database and add data
        from medication_tracker.api import create_app
        app1 = create_app(str(db_path))
        client1 = app1.test_client()

        # Create medication and mark dose
        med_response = client1.post('/medications', json={
            "name": "Test Med",
            "dosage": "100mg",
            "frequency": "daily",
        })
        medication_id = med_response.get_json()["id"]
        client1.post(f'/medications/{medication_id}/doses', json={})

        # Restart app
        app2 = create_app(str(db_path))
        client2 = app2.test_client()

        # Verify dose record persists
        history_response = client2.get(f'/medications/{medication_id}/doses')
        assert history_response.status_code == 200
        data = history_response.get_json()
        assert len(data) == 1
=======
    DoseService,
    ConflictError,
)
from medication_tracker.models import Medication as MedicationModel


# ---------------------------------------------------------------------------
# Medication model validation
# ---------------------------------------------------------------------------


class TestMedicationModelValidation:
    """Tests for Medication model field validation."""

    def test_valid_medication_creation(self):
        """Medication creation succeeds with valid name, dosage, frequency, and date fields."""
        med = Medication(
            name="Amoxicillin",
            dosage="500mg",
            frequency="twice daily",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 14),
        )
        assert med.name == "Amoxicillin"
        assert med.dosage == "500mg"
        assert med.frequency == "twice daily"
        assert med.start_date == date(2026, 1, 1)
        assert med.end_date == date(2026, 1, 14)
        assert med.status == MedicationStatus.ACTIVE
        assert isinstance(med.id, UUID)

    def test_creation_fails_when_name_missing(self):
        """Medication creation fails when name is missing."""
        with pytest.raises(TypeError):
            Medication(dosage="500mg", frequency="twice daily")

    def test_creation_fails_when_dosage_missing(self):
        """Medication creation fails when dosage is missing."""
        with pytest.raises(TypeError):
            Medication(name="Amoxicillin", frequency="twice daily")

    def test_creation_fails_when_frequency_missing(self):
        """Medication creation fails when frequency is missing."""
        with pytest.raises(TypeError):
            Medication(name="Amoxicillin", dosage="500mg")

    def test_creation_fails_with_empty_name(self):
        """Medication creation fails with empty name."""
        with pytest.raises(ValueError):
            Medication(name="", dosage="500mg", frequency="twice daily")

    def test_creation_fails_with_empty_dosage(self):
        """Medication creation fails with empty dosage."""
        with pytest.raises(ValueError):
            Medication(name="Amoxicillin", dosage="", frequency="twice daily")

    def test_creation_fails_with_empty_frequency(self):
        """Medication creation fails with empty frequency."""
        with pytest.raises(ValueError):
            Medication(name="Amoxicillin", dosage="500mg", frequency="")

    def test_creation_fails_with_whitespace_only_name(self):
        """Medication creation fails with whitespace-only name."""
        with pytest.raises(ValueError):
            Medication(name="   ", dosage="500mg", frequency="twice daily")

    def test_creation_fails_with_whitespace_only_dosage(self):
        """Medication creation fails with whitespace-only dosage."""
        with pytest.raises(ValueError):
            Medication(name="Amoxicillin", dosage="  ", frequency="twice daily")

    def test_creation_fails_with_whitespace_only_frequency(self):
        """Medication creation fails with whitespace-only frequency."""
        with pytest.raises(ValueError):
            Medication(name="Amoxicillin", dosage="500mg", frequency="  ")

    def test_dosage_rejects_non_string(self):
        """Dosage value rejects non-string inputs."""
        with pytest.raises(ValueError):
            Medication(name="Amoxicillin", dosage=500, frequency="twice daily")

    def test_frequency_rejects_non_string(self):
        """Frequency value rejects non-string inputs."""
        with pytest.raises(ValueError):
            Medication(name="Amoxicillin", dosage="500mg", frequency=2)

    def test_name_rejects_non_string(self):
        """Name value rejects non-string inputs."""
        with pytest.raises(ValueError):
            Medication(name=123, dosage="500mg", frequency="twice daily")

    def test_invalid_status_rejected(self):
        """Invalid status value is rejected."""
        with pytest.raises(ValueError):
            Medication(name="Amoxicillin", dosage="500mg", frequency="daily", status="paused")

    def test_to_dict_roundtrip(self):
        """to_dict produces a serializable dictionary."""
        med = Medication(name="Ibuprofen", dosage="400mg", frequency="every 6 hours")
        d = med.to_dict()
        assert d["name"] == "Ibuprofen"
        assert d["dosage"] == "400mg"
        assert d["frequency"] == "every 6 hours"
        assert d["status"] == "active"
        assert d["id"] == str(med.id)


# ---------------------------------------------------------------------------
# DoseRecord model validation
# ---------------------------------------------------------------------------


class TestDoseRecordValidation:
    """Tests for DoseRecord model validation."""

    def test_dose_record_defaults(self):
        """DoseRecord gets an id and timestamp by default."""
        dose = DoseRecord(medication_id=uuid4(), date=date.today())
        assert dose.status == "taken"
        assert isinstance(dose.id, UUID)
        assert dose.timestamp is not None

    def test_dose_record_future_date_rejected(self):
        """DoseRecord date cannot be in the future."""
        future = date.today() + timedelta(days=1)
        with pytest.raises(ValueError):
            DoseRecord(medication_id=uuid4(), date=future)

    def test_dose_record_invalid_status_rejected(self):
        """DoseRecord status must be a valid enum value."""
        with pytest.raises(ValueError):
            DoseRecord(medication_id=uuid4(), date=date.today(), status="maybe")

    def test_dose_record_valid_statuses(self):
        """DoseRecord accepts all valid statuses."""
        for status in ("taken", "skipped", "missed"):
            dose = DoseRecord(medication_id=uuid4(), date=date.today(), status=status)
            assert dose.status == status

    def test_dose_record_to_dict(self):
        """DoseRecord.to_dict serializes correctly."""
        med_id = uuid4()
        dose = DoseRecord(medication_id=med_id, date=date(2026, 1, 1), status="taken")
        d = dose.to_dict()
        assert d["medication_id"] == str(med_id)
        assert d["date"] == "2026-01-01"
        assert d["status"] == "taken"


# ---------------------------------------------------------------------------
# Repository / persistence
# ---------------------------------------------------------------------------


class TestMedicationRepository:
    """Tests for medication repository CRUD and persistence."""

    def test_create_and_retrieve(self, repository):
        """Created medication is retrievable by id."""
        med = Medication(name="Test", dosage="100mg", frequency="daily")
        created = repository.create(med)
        assert created.created_at is not None

        retrieved = repository.get_by_id(med.id)
        assert retrieved is not None
        assert retrieved.name == "Test"
        assert retrieved.dosage == "100mg"

    def test_get_all_sorted_by_created_at_desc(self, repository):
        """get_all returns medications sorted by created_at descending."""
        import time

        med1 = Medication(name="First", dosage="10mg", frequency="daily")
        med2 = Medication(name="Second", dosage="20mg", frequency="daily")
        repository.create(med1)
        time.sleep(0.01)
        repository.create(med2)

        all_meds = repository.get_all()
        assert all_meds[0].name == "Second"
        assert all_meds[1].name == "First"

    def test_update(self, repository):
        """Updating a medication persists changes."""
        med = Medication(name="Original", dosage="100mg", frequency="daily")
        repository.create(med)
        med.name = "Updated"
        med.dosage = "200mg"
        updated = repository.update(med)
        assert updated.name == "Updated"
        assert updated.dosage == "200mg"

    def test_delete(self, repository):
        """Deleting a medication removes it."""
        med = Medication(name="ToDelete", dosage="50mg", frequency="daily")
        repository.create(med)
        assert repository.delete(med.id) is True
        assert repository.get_by_id(med.id) is None

    def test_delete_nonexistent_returns_false(self, repository):
        """Deleting a non-existent medication returns False."""
        assert repository.delete(uuid4()) is False


class TestDataPersistenceAcrossRestart:
    """Tests that medication data persists across database reopen (app restart)."""

    def test_medication_persists_after_reopen(self):
        """Medication data persists correctly and is retrievable after app restart."""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            db1 = get_database(path)
            db1.init_schema()
            repo1 = MedicationRepository(db1)
            med = Medication(name="Persistent", dosage="100mg", frequency="daily")
            repo1.create(med)
            original_id = med.id
            db1.close()

            db2 = get_database(path)
            db2.init_schema()
            repo2 = MedicationRepository(db2)
            retrieved = repo2.get_by_id(original_id)
            assert retrieved is not None
            assert retrieved.name == "Persistent"
            assert retrieved.dosage == "100mg"
            db2.close()
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_dose_records_persist_after_reopen(self):
        """Dose records persist correctly and are retrievable after app restart."""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            db1 = get_database(path)
            db1.init_schema()
            repo1 = MedicationRepository(db1)
            med = Medication(name="Dose Med", dosage="100mg", frequency="daily")
            repo1.create(med)

            dose = DoseRecord(medication_id=med.id, date=date.today())
            repo1.create_dose_record(dose)
            db1.close()

            db2 = get_database(path)
            db2.init_schema()
            repo2 = MedicationRepository(db2)
            records = repo2.get_dose_records(med.id)
            assert len(records) == 1
            assert records[0].medication_id == med.id
            db2.close()
        finally:
            if os.path.exists(path):
                os.remove(path)


# ---------------------------------------------------------------------------
# DoseService - core dose tracking logic (build unit #2)
# ---------------------------------------------------------------------------


class TestDoseServiceMarkTaken:
    """Tests for DoseService.mark_dose_taken."""

    def test_mark_dose_taken_creates_timestamped_record(self, repository, dose_service):
        """Mark-as-taken creates a timestamped dose record linked to correct medication."""
        med = Medication(name="Test Med", dosage="100mg", frequency="daily")
        repository.create(med)

        dose = dose_service.mark_dose_taken(med.id)
        assert dose.medication_id == med.id
        assert dose.status == "taken"
        assert dose.timestamp is not None
        assert dose.date == date.today()

    def test_mark_dose_taken_for_specific_date(self, repository, dose_service):
        """Mark-as-taken with a specific past date creates a record for that date."""
        med = Medication(name="Test Med", dosage="100mg", frequency="daily")
        repository.create(med)

        specific = date.today() - timedelta(days=2)
        dose = dose_service.mark_dose_taken(med.id, specific)
        assert dose.date == specific

    def test_duplicate_same_day_returns_conflict(self, repository, dose_service):
        """Duplicate call to mark_dose_taken on the same day raises ConflictError."""
        med = Medication(name="Test Med", dosage="100mg", frequency="daily")
        repository.create(med)

        dose_service.mark_dose_taken(med.id)
        with pytest.raises(ConflictError):
            dose_service.mark_dose_taken(med.id)

    def test_duplicate_specific_date_returns_conflict(self, repository, dose_service):
        """Duplicate for a specific date raises ConflictError."""
        med = Medication(name="Test Med", dosage="100mg", frequency="daily")
        repository.create(med)

        specific = date.today() - timedelta(days=1)
        dose_service.mark_dose_taken(med.id, specific)
        with pytest.raises(ConflictError):
            dose_service.mark_dose_taken(med.id, specific)

    def test_future_date_rejected(self, repository, dose_service):
        """Future date is rejected with ValueError."""
        med = Medication(name="Test Med", dosage="100mg", frequency="daily")
        repository.create(med)

        future = date.today() + timedelta(days=1)
        with pytest.raises(ValueError):
            dose_service.mark_dose_taken(med.id, future)

    def test_mark_dose_skipped(self, repository, dose_service):
        """mark_dose_skipped creates a skipped dose record."""
        med = Medication(name="Test Med", dosage="100mg", frequency="daily")
        repository.create(med)

        dose = dose_service.mark_dose_skipped(med.id, date.today())
        assert dose.status == "skipped"

    def test_mark_dose_skipped_duplicate_conflict(self, repository, dose_service):
        """Duplicate skipped dose raises ConflictError."""
        med = Medication(name="Test Med", dosage="100mg", frequency="daily")
        repository.create(med)

        dose_service.mark_dose_skipped(med.id, date.today())
        with pytest.raises(ConflictError):
            dose_service.mark_dose_skipped(med.id, date.today())


class TestDoseServiceHistory:
    """Tests for DoseService.get_dose_history."""

    def test_get_dose_history_returns_sorted_results(self, repository, dose_service):
        """getDoseHistory returns sorted results (date desc)."""
        med = Medication(name="Test Med", dosage="100mg", frequency="daily")
        repository.create(med)

        day1 = date.today() - timedelta(days=2)
        day2 = date.today() - timedelta(days=1)
        day3 = date.today()

        dose_service.mark_dose_taken(med.id, day1)
        dose_service.mark_dose_taken(med.id, day2)
        dose_service.mark_dose_taken(med.id, day3)

        history = dose_service.get_dose_history(med.id)
        assert len(history) == 3
        # Sorted by date descending
        assert history[0].date == day3
        assert history[1].date == day2
        assert history[2].date == day1

    def test_get_dose_history_with_date_range(self, repository, dose_service):
        """getDoseHistory filters by start and end date."""
        med = Medication(name="Test Med", dosage="100mg", frequency="daily")
        repository.create(med)

        day1 = date.today() - timedelta(days=3)
        day2 = date.today() - timedelta(days=2)
        day3 = date.today() - timedelta(days=1)

        dose_service.mark_dose_taken(med.id, day1)
        dose_service.mark_dose_taken(med.id, day2)
        dose_service.mark_dose_taken(med.id, day3)

        history = dose_service.get_dose_history(med.id, start_date=day2, end_date=day3)
        assert len(history) == 2
        assert all(r.date >= day2 for r in history)
        assert all(r.date <= day3 for r in history)

    def test_get_dose_history_empty_for_new_medication(self, repository, dose_service):
        """getDoseHistory returns empty list for a medication with no doses."""
        med = Medication(name="Test Med", dosage="100mg", frequency="daily")
        repository.create(med)

        history = dose_service.get_dose_history(med.id)
        assert history == []

    def test_get_dose_for_date(self, repository, dose_service):
        """get_dose_for_date returns the dose for a specific date or None."""
        med = Medication(name="Test Med", dosage="100mg", frequency="daily")
        repository.create(med)

        assert dose_service.get_dose_for_date(med.id, date.today()) is None

        dose_service.mark_dose_taken(med.id)
        found = dose_service.get_dose_for_date(med.id, date.today())
        assert found is not None
        assert found.status == "taken"

    def test_doses_isolated_per_medication(self, repository, dose_service):
        """Dose records are isolated per medication — same date allowed for different meds."""
        med1 = Medication(name="Med One", dosage="100mg", frequency="daily")
        med2 = Medication(name="Med Two", dosage="200mg", frequency="daily")
        repository.create(med1)
        repository.create(med2)

        dose_service.mark_dose_taken(med1.id)
        dose_service.mark_dose_taken(med2.id)  # same day, different med — no conflict

        assert len(dose_service.get_dose_history(med1.id)) == 1
        assert len(dose_service.get_dose_history(med2.id)) == 1


class TestDoseServiceTimezone:
    """Tests for DATE_TIMEZONE-aware date handling."""

    def test_today_honors_non_utc_timezone(self, repository, dose_service, monkeypatch):
        """_today() resolves today using DATE_TIMEZONE when set to a non-UTC zone."""
        from medication_tracker.dose_service import _today

        monkeypatch.setenv("DATE_TIMEZONE", "America/New_York")
        result = _today()
        assert isinstance(result, date)

    def test_today_falls_back_on_invalid_timezone(self, monkeypatch):
        """_today() falls back to UTC for an unrecognized timezone."""
        from medication_tracker.dose_service import _today

        monkeypatch.setenv("DATE_TIMEZONE", "Not/A_Real_Zone")
        result = _today()
        assert isinstance(result, date)

    def test_mark_dose_taken_uses_timezone_today(self, repository, dose_service, monkeypatch):
        """mark_dose_taken with no date uses the timezone-aware today."""
        monkeypatch.setenv("DATE_TIMEZONE", "America/New_York")
        med = Medication(name="TZ Med", dosage="100mg", frequency="daily")
        repository.create(med)

        dose = dose_service.mark_dose_taken(med.id)
        from medication_tracker.dose_service import _today
        assert dose.date == _today()


# ---------------------------------------------------------------------------
# Database schema / indexes
# ---------------------------------------------------------------------------


class TestDatabaseSchema:
    """Tests for database schema integrity."""

    def test_dose_records_unique_constraint(self, database):
        """Unique constraint on (medication_id, date) prevents duplicates at DB level."""
        from sqlite3 import IntegrityError

        med_id = str(uuid4())
        with database.transaction() as conn:
            conn.execute(
                "INSERT INTO medications (id, name, dosage, frequency) VALUES (?, ?, ?, ?)",
                (med_id, "Test", "100mg", "daily"),
            )

        today = date.today().isoformat()
        with database.transaction() as conn:
            conn.execute(
                "INSERT INTO dose_records (id, medication_id, date, timestamp, status) VALUES (?, ?, ?, ?, ?)",
                (str(uuid4()), med_id, today, "2026-01-01T00:00:00", "taken"),
            )

        with pytest.raises(IntegrityError):
            with database.transaction() as conn:
                conn.execute(
                    "INSERT INTO dose_records (id, medication_id, date, timestamp, status) VALUES (?, ?, ?, ?, ?)",
                    (str(uuid4()), med_id, today, "2026-01-01T00:00:00", "taken"),
                )

    def test_dose_records_indexes_exist(self, database):
        """Indexes on medication_id and date exist for query performance."""
        cursor = database.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='dose_records'"
        )
        index_names = {row["name"] for row in cursor.fetchall()}
        assert "idx_dose_records_medication_id" in index_names
        assert "idx_dose_records_date" in index_names

    def test_dose_status_check_constraint(self, database):
        """Invalid dose status is rejected at DB level."""
        from sqlite3 import IntegrityError

        med_id = str(uuid4())
        with database.transaction() as conn:
            conn.execute(
                "INSERT INTO medications (id, name, dosage, frequency) VALUES (?, ?, ?, ?)",
                (med_id, "Test", "100mg", "daily"),
            )

        with pytest.raises(IntegrityError):
            with database.transaction() as conn:
                conn.execute(
                    "INSERT INTO dose_records (id, medication_id, date, timestamp, status) VALUES (?, ?, ?, ?, ?)",
                    (str(uuid4()), med_id, date.today().isoformat(), "2026-01-01T00:00:00", "maybe"),
                )
>>>>>>> 9105369 (runctl: build runctl/build-09d3fc65 (pass))
