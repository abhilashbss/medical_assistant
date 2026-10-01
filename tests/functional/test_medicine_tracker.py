"""Functional tests for medicine tracker feature.

This module tests:
- API integration for adding, editing, deleting medications
- Validation of required fields (name, dosage)
- Mark-as-taken action creates timestamped dose records
- Status filtering (active vs completed)
- Data persistence across app restarts
"""

import pytest
import tempfile
import os
from datetime import date
from uuid import uuid4

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from medication_tracker import (
    Database,
    get_database,
    Medication,
    MedicationStatus,
    DoseRecord,
    MedicationRepository,
    create_app,
)


@pytest.fixture
def test_db_path():
    """Create a temporary database file for testing."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    yield path
    # Cleanup
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def app(test_db_path):
    """Create Flask app with test database."""
    return create_app(db_path=test_db_path)


@pytest.fixture
def client(app):
    """Create test client for Flask app."""
    return app.test_client()


@pytest.fixture
def repository(test_db_path):
    """Create a medication repository for testing."""
    db = get_database(test_db_path)
    db.init_schema()
    return MedicationRepository(db)


class TestFunctionalMedicationAPI:
    """Functional tests for medication API endpoints."""

    def test_add_medication_with_all_required_fields(self, client):
        """Adding a medication with all required fields succeeds and appears in list."""
        response = client.post('/medications', json={
            'name': 'Amoxicillin',
            'dosage': '500mg',
            'frequency': 'twice daily'
        })

        assert response.status_code == 201
        data = response.get_json()
        assert data['name'] == 'Amoxicillin'
        assert data['dosage'] == '500mg'
        assert data['frequency'] == 'twice daily'
        assert data['status'] == 'active'
        assert 'id' in data
        assert 'created_at' in data

        # Verify it appears in the list
        list_response = client.get('/medications')
        assert list_response.status_code == 200
        medications = list_response.get_json()
        assert len(medications) == 1
        assert medications[0]['name'] == 'Amoxicillin'

    def test_add_medication_missing_name_rejected(self, client):
        """Medications with missing name are rejected with validation error."""
        response = client.post('/medications', json={
            'dosage': '500mg',
            'frequency': 'twice daily'
        })

        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data

    def test_add_medication_missing_dosage_rejected(self, client):
        """Medications with missing dosage are rejected with validation error."""
        response = client.post('/medications', json={
            'name': 'Amoxicillin',
            'frequency': 'twice daily'
        })

        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data

    def test_add_medication_empty_name_rejected(self, client):
        """Medications with empty name are rejected with validation error."""
        response = client.post('/medications', json={
            'name': '',
            'dosage': '500mg',
            'frequency': 'twice daily'
        })

        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data

    def test_add_medication_empty_dosage_rejected(self, client):
        """Medications with empty dosage are rejected with validation error."""
        response = client.post('/medications', json={
            'name': 'Amoxicillin',
            'dosage': '',
            'frequency': 'twice daily'
        })

        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data

    def test_add_medication_empty_frequency_rejected(self, client):
        """Medications with empty frequency are rejected with validation error."""
        response = client.post('/medications', json={
            'name': 'Amoxicillin',
            'dosage': '500mg',
            'frequency': ''
        })

        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data

    def test_add_medication_with_optional_fields(self, client):
        """Adding a medication with optional fields (start_date, end_date, status) succeeds."""
        response = client.post('/medications', json={
            'name': 'Ibuprofen',
            'dosage': '400mg',
            'frequency': 'every 6 hours',
            'start_date': '2026-01-01',
            'end_date': '2026-01-14',
            'status': 'completed'
        })

        assert response.status_code == 201
        data = response.get_json()
        assert data['start_date'] == '2026-01-01'
        assert data['end_date'] == '2026-01-14'
        assert data['status'] == 'completed'

    def test_edit_medication_updates_fields(self, client, repository):
        """Editing a medication updates all fields and persists changes."""
        # Create initial medication
        medication = Medication(
            name='Original',
            dosage='100mg',
            frequency='daily',
        )
        repository.create(medication)

        # Edit the medication
        response = client.put(f'/medications/{medication.id}', json={
            'name': 'Edited',
            'dosage': '200mg',
            'frequency': 'twice daily',
            'status': 'completed'
        })

        assert response.status_code == 200
        data = response.get_json()
        assert data['name'] == 'Edited'
        assert data['dosage'] == '200mg'
        assert data['frequency'] == 'twice daily'
        assert data['status'] == 'completed'

        # Verify persistence
        retrieved = repository.get_by_id(medication.id)
        assert retrieved.name == 'Edited'
        assert retrieved.dosage == '200mg'

    def test_edit_nonexistent_medication_returns_404(self, client):
        """Editing a non-existent medication returns 404."""
        fake_id = str(uuid4())
        response = client.put(f'/medications/{fake_id}', json={
            'name': 'Edited'
        })

        assert response.status_code == 404

    def test_delete_medication_removes_from_list(self, client, repository):
        """Deleting a medication removes it from the list immediately."""
        # Create medication
        medication = Medication(
            name='ToDelete',
            dosage='50mg',
            frequency='daily',
        )
        repository.create(medication)

        # Delete the medication
        response = client.delete(f'/medications/{medication.id}')
        assert response.status_code == 204

        # Verify it's removed from the list
        list_response = client.get('/medications')
        medications = list_response.get_json()
        assert len(medications) == 0

    def test_delete_nonexistent_medication_returns_404(self, client):
        """Deleting a non-existent medication returns 404."""
        fake_id = str(uuid4())
        response = client.delete(f'/medications/{fake_id}')

        assert response.status_code == 404

    def test_mark_as_taken_creates_dose_record(self, client, repository):
        """Marking as taken records timestamp and updates adherence."""
        # Create medication
        medication = Medication(
            name='Test Med',
            dosage='100mg',
            frequency='daily',
        )
        repository.create(medication)

        # Mark as taken
        response = client.post(f'/medications/{medication.id}/dose', json={})
        assert response.status_code == 201
        data = response.get_json()
        assert data['medication_id'] == str(medication.id)
        assert data['timestamp'] is not None
        assert data['status'] == 'taken'

    def test_mark_as_taken_with_specific_date(self, client, repository):
        """Mark-as-taken can specify a date for the dose."""
        medication = Medication(
            name='Test Med',
            dosage='100mg',
            frequency='daily',
        )
        repository.create(medication)

        response = client.post(f'/medications/{medication.id}/dose', json={
            'date': '2026-09-20'
        })

        assert response.status_code == 201
        data = response.get_json()
        assert data['date'] == '2026-09-20'

    def test_status_filtering_active_medications(self, client, repository):
        """Status filtering correctly returns only active medications."""
        # Create active medications
        active1 = Medication(name='Active 1', dosage='100mg', frequency='daily')
        active2 = Medication(name='Active 2', dosage='200mg', frequency='daily')
        # Create completed medication
        completed = Medication(
            name='Completed',
            dosage='300mg',
            frequency='daily',
            status=MedicationStatus.COMPLETED,
        )

        repository.create(active1)
        repository.create(active2)
        repository.create(completed)

        # Filter by active
        response = client.get('/medications?status=active')
        assert response.status_code == 200
        medications = response.get_json()
        assert len(medications) == 2
        assert all(m['status'] == 'active' for m in medications)

    def test_status_filtering_completed_medications(self, client, repository):
        """Status filtering correctly returns only completed medications."""
        # Create active medication
        active = Medication(name='Active', dosage='100mg', frequency='daily')
        # Create completed medications
        completed1 = Medication(
            name='Completed 1',
            dosage='200mg',
            frequency='daily',
            status=MedicationStatus.COMPLETED,
        )
        completed2 = Medication(
            name='Completed 2',
            dosage='300mg',
            frequency='daily',
            status=MedicationStatus.COMPLETED,
        )

        repository.create(active)
        repository.create(completed1)
        repository.create(completed2)

        # Filter by completed
        response = client.get('/medications?status=completed')
        assert response.status_code == 200
        medications = response.get_json()
        assert len(medications) == 2
        assert all(m['status'] == 'completed' for m in medications)

    def test_status_filter_all_returns_everything(self, client, repository):
        """Status filter 'all' returns both active and completed medications."""
        active = Medication(name='Active', dosage='100mg', frequency='daily')
        completed = Medication(
            name='Completed',
            dosage='200mg',
            frequency='daily',
            status=MedicationStatus.COMPLETED,
        )

        repository.create(active)
        repository.create(completed)

        response = client.get('/medications?status=all')
        assert response.status_code == 200
        medications = response.get_json()
        assert len(medications) == 2

    def test_medication_list_sorted_by_most_recent(self, client, repository):
        """Medication list is sorted by created_at descending (most recent first)."""
        import time

        med1 = Medication(name='First', dosage='100mg', frequency='daily')
        med2 = Medication(name='Second', dosage='200mg', frequency='daily')
        med3 = Medication(name='Third', dosage='300mg', frequency='daily')

        repository.create(med1)
        time.sleep(0.01)
        repository.create(med2)
        time.sleep(0.01)
        repository.create(med3)

        response = client.get('/medications')
        assert response.status_code == 200
        medications = response.get_json()

        assert len(medications) == 3
        assert medications[0]['name'] == 'Third'
        assert medications[1]['name'] == 'Second'
        assert medications[2]['name'] == 'First'

    def test_get_single_medication_by_id(self, client, repository):
        """Getting a single medication by ID returns the correct medication."""
        medication = Medication(
            name='Test Med',
            dosage='100mg',
            frequency='daily',
        )
        repository.create(medication)

        response = client.get(f'/medications/{medication.id}')
        assert response.status_code == 200
        data = response.get_json()
        assert data['name'] == 'Test Med'
        assert data['dosage'] == '100mg'

    def test_get_nonexistent_medication_returns_404(self, client):
        """Getting a non-existent medication returns 404."""
        fake_id = str(uuid4())
        response = client.get(f'/medications/{fake_id}')

        assert response.status_code == 404


class TestDataPersistence:
    """Tests for data persistence across app restarts."""

    def test_data_persists_after_database_reopen(self, test_db_path):
        """Medication data persists correctly after database restart."""
        # Create database and add data
        db1 = get_database(test_db_path)
        db1.init_schema()
        repo1 = MedicationRepository(db1)

        medication = Medication(
            name='Persistent Med',
            dosage='100mg',
            frequency='daily',
        )
        repo1.create(medication)
        original_id = medication.id
        db1.close()

        # Reopen database and verify data
        db2 = get_database(test_db_path)
        db2.init_schema()
        repo2 = MedicationRepository(db2)

        retrieved = repo2.get_by_id(original_id)

        assert retrieved is not None
        assert retrieved.name == 'Persistent Med'
        assert retrieved.dosage == '100mg'

        db2.close()

    def test_crud_operations_persist_across_restarts(self, test_db_path):
        """Create, update, delete operations persist after restart."""
        # Create and update
        db1 = get_database(test_db_path)
        db1.init_schema()
        repo1 = MedicationRepository(db1)

        medication = Medication(
            name='Original',
            dosage='100mg',
            frequency='daily',
        )
        repo1.create(medication)
        medication.name = 'Updated'
        repo1.update(medication)
        db1.close()

        # Verify after restart
        db2 = get_database(test_db_path)
        db2.init_schema()
        repo2 = MedicationRepository(db2)

        retrieved = repo2.get_by_id(medication.id)
        assert retrieved is not None
        assert retrieved.name == 'Updated'

        db2.close()

    def test_deleted_medication_stays_deleted(self, test_db_path):
        """Deleted medication remains deleted after restart."""
        db1 = get_database(test_db_path)
        db1.init_schema()
        repo1 = MedicationRepository(db1)

        medication = Medication(
            name='ToDelete',
            dosage='100mg',
            frequency='daily',
        )
        repo1.create(medication)
        repo1.delete(medication.id)
        db1.close()

        # Verify after restart
        db2 = get_database(test_db_path)
        db2.init_schema()
        repo2 = MedicationRepository(db2)

        retrieved = repo2.get_by_id(medication.id)
        assert retrieved is None

        db2.close()

    def test_dose_records_persist(self, test_db_path):
        """Dose records persist correctly after database restart."""
        db1 = get_database(test_db_path)
        db1.init_schema()
        repo1 = MedicationRepository(db1)

        medication = Medication(
            name='Test Med',
            dosage='100mg',
            frequency='daily',
        )
        repo1.create(medication)

        dose = DoseRecord(
            medication_id=medication.id,
            date=date.today(),
        )
        repo1.create_dose_record(dose)
        db1.close()

        # Reopen and verify
        db2 = get_database(test_db_path)
        db2.init_schema()
        repo2 = MedicationRepository(db2)

        records = repo2.get_dose_records(medication.id)
        assert len(records) == 1
        assert records[0].medication_id == medication.id

        db2.close()


class TestFunctionalMedicationList:
    """Functional tests for medication list UI behavior."""

    def test_empty_list_response(self, client):
        """Empty medication list returns empty array."""
        response = client.get('/medications')
        assert response.status_code == 200
        medications = response.get_json()
        assert medications == []

    def test_list_includes_all_medication_fields(self, client, repository):
        """Medication list includes all required fields."""
        medication = Medication(
            name='Test Med',
            dosage='100mg',
            frequency='daily',
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 14),
        )
        repository.create(medication)

        response = client.get('/medications')
        assert response.status_code == 200
        medications = response.get_json()

        assert len(medications) == 1
        med = medications[0]
        assert 'id' in med
        assert med['name'] == 'Test Med'
        assert med['dosage'] == '100mg'
        assert med['frequency'] == 'daily'
        assert med['start_date'] == '2026-01-01'
        assert med['end_date'] == '2026-01-14'
        assert med['status'] == 'active'
        assert 'created_at' in med
        assert 'updated_at' in med

    def test_health_endpoint(self, client):
        """Health check endpoint returns healthy status."""
        response = client.get('/health')
        assert response.status_code == 200
        data = response.get_json()
        assert data['status'] == 'healthy'
