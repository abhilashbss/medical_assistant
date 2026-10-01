"""Functional tests for medicine tracker feature.

<<<<<<< HEAD
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
=======
Covers the definition of done across the full Flask API:
- Adding a medication with name, dosage, frequency, start/end date creates a record that persists after app restart
- Medication list displays all entries sorted by most recently added, with active/completed status filtering
- Editing an existing medication updates all fields and changes persist across sessions
- Mark-as-taken action creates a timestamped dose record for the current day
- Deleting a medication removes it from the active list and database
- Validation rejects incomplete entries (missing name/dosage) and non-string dosage/frequency inputs
"""

import os
import sys
import tempfile
from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from medication_tracker import (
>>>>>>> 9105369 (runctl: build runctl/build-09d3fc65 (pass))
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
<<<<<<< HEAD
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    yield path
    # Cleanup
=======
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
>>>>>>> 9105369 (runctl: build runctl/build-09d3fc65 (pass))
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
<<<<<<< HEAD
    """Create a medication repository for testing."""
=======
    """Create a medication repository sharing the test database."""
>>>>>>> 9105369 (runctl: build runctl/build-09d3fc65 (pass))
    db = get_database(test_db_path)
    db.init_schema()
    return MedicationRepository(db)


<<<<<<< HEAD
=======
# ---------------------------------------------------------------------------
# Medication CRUD
# ---------------------------------------------------------------------------


>>>>>>> 9105369 (runctl: build runctl/build-09d3fc65 (pass))
class TestFunctionalMedicationAPI:
    """Functional tests for medication API endpoints."""

    def test_add_medication_with_all_required_fields(self, client):
        """Adding a medication with all required fields succeeds and appears in list."""
<<<<<<< HEAD
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

=======
        response = client.post("/medications", json={
            "name": "Amoxicillin",
            "dosage": "500mg",
            "frequency": "twice daily",
        })
        assert response.status_code == 201
        data = response.get_json()
        assert data["name"] == "Amoxicillin"
        assert data["dosage"] == "500mg"
        assert data["frequency"] == "twice daily"
        assert data["status"] == "active"
        assert "id" in data
        assert "created_at" in data

        list_response = client.get("/medications")
        assert list_response.status_code == 200
        medications = list_response.get_json()
        assert len(medications) == 1
        assert medications[0]["name"] == "Amoxicillin"

    def test_add_medication_with_optional_fields(self, client):
        """Adding a medication with optional fields succeeds."""
        response = client.post("/medications", json={
            "name": "Ibuprofen",
            "dosage": "400mg",
            "frequency": "every 6 hours",
            "start_date": "2026-01-01",
            "end_date": "2026-01-14",
            "status": "completed",
        })
        assert response.status_code == 201
        data = response.get_json()
        assert data["start_date"] == "2026-01-01"
        assert data["end_date"] == "2026-01-14"
        assert data["status"] == "completed"

    def test_add_medication_missing_name_rejected(self, client):
        """Medications with missing name are rejected with 400."""
        response = client.post("/medications", json={
            "dosage": "500mg",
            "frequency": "twice daily",
        })
        assert response.status_code == 400
        assert "error" in response.get_json()

    def test_add_medication_missing_dosage_rejected(self, client):
        """Medications with missing dosage are rejected with 400."""
        response = client.post("/medications", json={
            "name": "Amoxicillin",
            "frequency": "twice daily",
        })
        assert response.status_code == 400
        assert "error" in response.get_json()

    def test_add_medication_missing_frequency_rejected(self, client):
        """Medications with missing frequency are rejected with 400."""
        response = client.post("/medications", json={
            "name": "Amoxicillin",
            "dosage": "500mg",
        })
        assert response.status_code == 400
        assert "error" in response.get_json()

    def test_add_medication_empty_name_rejected(self, client):
        """Medications with empty name are rejected with 400."""
        response = client.post("/medications", json={
            "name": "",
            "dosage": "500mg",
            "frequency": "twice daily",
        })
        assert response.status_code == 400
        assert "error" in response.get_json()

    def test_add_medication_empty_dosage_rejected(self, client):
        """Medications with empty dosage are rejected with 400."""
        response = client.post("/medications", json={
            "name": "Amoxicillin",
            "dosage": "",
            "frequency": "twice daily",
        })
        assert response.status_code == 400
        assert "error" in response.get_json()

    def test_add_medication_empty_frequency_rejected(self, client):
        """Medications with empty frequency are rejected with 400."""
        response = client.post("/medications", json={
            "name": "Amoxicillin",
            "dosage": "500mg",
            "frequency": "",
        })
        assert response.status_code == 400
        assert "error" in response.get_json()

    def test_edit_medication_updates_fields(self, client, repository):
        """Editing a medication updates all fields and persists changes."""
        med = Medication(name="Original", dosage="100mg", frequency="daily")
        repository.create(med)

        response = client.put(f"/medications/{med.id}", json={
            "name": "Edited",
            "dosage": "200mg",
            "frequency": "twice daily",
            "status": "completed",
        })
        assert response.status_code == 200
        data = response.get_json()
        assert data["name"] == "Edited"
        assert data["dosage"] == "200mg"
        assert data["status"] == "completed"

        retrieved = repository.get_by_id(med.id)
        assert retrieved.name == "Edited"
        assert retrieved.dosage == "200mg"

    def test_edit_nonexistent_medication_returns_404(self, client):
        """Editing a non-existent medication returns 404."""
        response = client.put(f"/medications/{uuid4()}", json={"name": "Edited"})
        assert response.status_code == 404

    def test_delete_medication_removes_from_list(self, client, repository):
        """Deleting a medication removes it from the list."""
        med = Medication(name="ToDelete", dosage="50mg", frequency="daily")
        repository.create(med)

        response = client.delete(f"/medications/{med.id}")
        assert response.status_code == 204

        list_response = client.get("/medications")
        assert len(list_response.get_json()) == 0

    def test_delete_nonexistent_medication_returns_404(self, client):
        """Deleting a non-existent medication returns 404."""
        response = client.delete(f"/medications/{uuid4()}")
        assert response.status_code == 404

    def test_get_single_medication_by_id(self, client, repository):
        """Getting a single medication by ID returns the correct medication."""
        med = Medication(name="Test Med", dosage="100mg", frequency="daily")
        repository.create(med)

        response = client.get(f"/medications/{med.id}")
        assert response.status_code == 200
        data = response.get_json()
        assert data["name"] == "Test Med"

    def test_get_nonexistent_medication_returns_404(self, client):
        """Getting a non-existent medication returns 404."""
        response = client.get(f"/medications/{uuid4()}")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Status filtering and sorting
# ---------------------------------------------------------------------------


class TestFunctionalStatusFiltering:
    """Functional tests for status filtering and sorting."""

    def test_status_filter_active(self, client, repository):
        """Status filter returns only active medications."""
        active1 = Medication(name="Active 1", dosage="100mg", frequency="daily")
        active2 = Medication(name="Active 2", dosage="200mg", frequency="daily")
        completed = Medication(
            name="Completed", dosage="300mg", frequency="daily",
            status=MedicationStatus.COMPLETED,
        )
>>>>>>> 9105369 (runctl: build runctl/build-09d3fc65 (pass))
        repository.create(active1)
        repository.create(active2)
        repository.create(completed)

<<<<<<< HEAD
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

=======
        response = client.get("/medications?status=active")
        assert response.status_code == 200
        medications = response.get_json()
        assert len(medications) == 2
        assert all(m["status"] == "active" for m in medications)

    def test_status_filter_completed(self, client, repository):
        """Status filter returns only completed medications."""
        active = Medication(name="Active", dosage="100mg", frequency="daily")
        completed1 = Medication(
            name="Completed 1", dosage="200mg", frequency="daily",
            status=MedicationStatus.COMPLETED,
        )
        completed2 = Medication(
            name="Completed 2", dosage="300mg", frequency="daily",
            status=MedicationStatus.COMPLETED,
        )
>>>>>>> 9105369 (runctl: build runctl/build-09d3fc65 (pass))
        repository.create(active)
        repository.create(completed1)
        repository.create(completed2)

<<<<<<< HEAD
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
=======
        response = client.get("/medications?status=completed")
        assert response.status_code == 200
        medications = response.get_json()
        assert len(medications) == 2
        assert all(m["status"] == "completed" for m in medications)

    def test_status_filter_all(self, client, repository):
        """Status filter 'all' returns both active and completed."""
        active = Medication(name="Active", dosage="100mg", frequency="daily")
        completed = Medication(
            name="Completed", dosage="200mg", frequency="daily",
            status=MedicationStatus.COMPLETED,
        )
        repository.create(active)
        repository.create(completed)

        response = client.get("/medications?status=all")
        assert response.status_code == 200
        assert len(response.get_json()) == 2
>>>>>>> 9105369 (runctl: build runctl/build-09d3fc65 (pass))

    def test_medication_list_sorted_by_most_recent(self, client, repository):
        """Medication list is sorted by created_at descending (most recent first)."""
        import time

<<<<<<< HEAD
        med1 = Medication(name='First', dosage='100mg', frequency='daily')
        med2 = Medication(name='Second', dosage='200mg', frequency='daily')
        med3 = Medication(name='Third', dosage='300mg', frequency='daily')

=======
        med1 = Medication(name="First", dosage="100mg", frequency="daily")
        med2 = Medication(name="Second", dosage="200mg", frequency="daily")
        med3 = Medication(name="Third", dosage="300mg", frequency="daily")
>>>>>>> 9105369 (runctl: build runctl/build-09d3fc65 (pass))
        repository.create(med1)
        time.sleep(0.01)
        repository.create(med2)
        time.sleep(0.01)
        repository.create(med3)

<<<<<<< HEAD
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

=======
        response = client.get("/medications")
        medications = response.get_json()
        assert len(medications) == 3
        assert medications[0]["name"] == "Third"
        assert medications[1]["name"] == "Second"
        assert medications[2]["name"] == "First"

    def test_empty_list_response(self, client):
        """Empty medication list returns empty array."""
        response = client.get("/medications")
        assert response.status_code == 200
        assert response.get_json() == []


# ---------------------------------------------------------------------------
# Dose tracking via API (build unit #2 core scope)
# ---------------------------------------------------------------------------


class TestFunctionalDoseTracking:
    """Functional tests for dose tracking endpoints."""

    def test_mark_as_taken_creates_timestamped_dose_record(self, client, repository):
        """Mark-as-taken action creates a timestamped dose record for the current day."""
        med = Medication(name="Test Med", dosage="100mg", frequency="daily")
        repository.create(med)

        response = client.post(f"/medications/{med.id}/doses", json={})
        assert response.status_code == 201
        data = response.get_json()
        assert data["medication_id"] == str(med.id)
        assert data["timestamp"] is not None
        assert data["status"] == "taken"
        assert data["date"] == date.today().isoformat()

    def test_mark_as_taken_dose_alias_path(self, client, repository):
        """Mark-as-taken also works via the /dose alias path."""
        med = Medication(name="Test Med", dosage="100mg", frequency="daily")
        repository.create(med)

        response = client.post(f"/medications/{med.id}/dose", json={})
        assert response.status_code == 201
        assert response.get_json()["status"] == "taken"

    def test_mark_as_taken_with_specific_date(self, client, repository):
        """Mark-as-taken can specify a date for the dose."""
        med = Medication(name="Test Med", dosage="100mg", frequency="daily")
        repository.create(med)

        response = client.post(f"/medications/{med.id}/doses", json={
            "date": "2026-09-20",
        })
        assert response.status_code == 201
        data = response.get_json()
        assert data["date"] == "2026-09-20"

    def test_second_mark_same_day_returns_409(self, client, repository):
        """Second POST for the same day returns 409 (idempotency)."""
        med = Medication(name="Test Med", dosage="100mg", frequency="daily")
        repository.create(med)

        first = client.post(f"/medications/{med.id}/doses", json={})
        assert first.status_code == 201

        second = client.post(f"/medications/{med.id}/doses", json={})
        assert second.status_code == 409
        assert "error" in second.get_json()

    def test_mark_as_taken_future_date_returns_400(self, client, repository):
        """Future date is rejected with 400."""
        med = Medication(name="Test Med", dosage="100mg", frequency="daily")
        repository.create(med)

        future = (date.today() + __import__("datetime").timedelta(days=1)).isoformat()
        response = client.post(f"/medications/{med.id}/doses", json={"date": future})
        assert response.status_code == 400
        assert "error" in response.get_json()

    def test_mark_as_taken_missing_medication_returns_404(self, client):
        """Mark-as-taken for a non-existent medication returns 404."""
        response = client.post(f"/medications/{uuid4()}/doses", json={})
        assert response.status_code == 404

    def test_mark_as_taken_invalid_uuid_returns_400(self, client):
        """Mark-as-taken with an invalid UUID returns 400."""
        response = client.post("/medications/not-a-uuid/doses", json={})
        assert response.status_code == 400

    def test_get_dose_history(self, client, repository):
        """GET /doses returns dose history for a medication."""
        med = Medication(name="Test Med", dosage="100mg", frequency="daily")
        repository.create(med)

        client.post(f"/medications/{med.id}/doses", json={})

        response = client.get(f"/medications/{med.id}/doses")
        assert response.status_code == 200
        records = response.get_json()
        assert len(records) == 1
        assert records[0]["medication_id"] == str(med.id)

    def test_get_dose_history_with_date_range(self, client, repository):
        """GET /doses with start/end query params filters by date range."""
        med = Medication(name="Test Med", dosage="100mg", frequency="daily")
        repository.create(med)

        client.post(f"/medications/{med.id}/doses", json={"date": "2026-09-10"})
        client.post(f"/medications/{med.id}/doses", json={"date": "2026-09-15"})
        client.post(f"/medications/{med.id}/doses", json={"date": "2026-09-20"})

        response = client.get(
            f"/medications/{med.id}/doses?start=2026-09-12&end=2026-09-18"
        )
        assert response.status_code == 200
        records = response.get_json()
        assert len(records) == 1
        assert records[0]["date"] == "2026-09-15"

    def test_get_dose_history_empty(self, client, repository):
        """GET /doses returns empty list for a medication with no doses."""
        med = Medication(name="Test Med", dosage="100mg", frequency="daily")
        repository.create(med)

        response = client.get(f"/medications/{med.id}/doses")
        assert response.status_code == 200
        assert response.get_json() == []

    def test_mark_as_taken_skipped_status(self, client, repository):
        """Mark-as-taken with status 'skipped' creates a skipped dose record."""
        med = Medication(name="Test Med", dosage="100mg", frequency="daily")
        repository.create(med)

        response = client.post(f"/medications/{med.id}/doses", json={"status": "skipped"})
        assert response.status_code == 201
        data = response.get_json()
        assert data["status"] == "skipped"

    def test_mark_as_taken_invalid_date_format_returns_400(self, client, repository):
        """Mark-as-taken with a malformed date returns 400."""
        med = Medication(name="Test Med", dosage="100mg", frequency="daily")
        repository.create(med)

        response = client.post(f"/medications/{med.id}/doses", json={"date": "not-a-date"})
        assert response.status_code == 400
        assert "error" in response.get_json()

    def test_get_dose_history_invalid_start_returns_400(self, client, repository):
        """GET /doses with a malformed start date returns 400."""
        med = Medication(name="Test Med", dosage="100mg", frequency="daily")
        repository.create(med)

        response = client.get(f"/medications/{med.id}/doses?start=not-a-date")
        assert response.status_code == 400
        assert "error" in response.get_json()

    def test_get_dose_history_invalid_end_returns_400(self, client, repository):
        """GET /doses with a malformed end date returns 400."""
        med = Medication(name="Test Med", dosage="100mg", frequency="daily")
        repository.create(med)

        response = client.get(f"/medications/{med.id}/doses?end=not-a-date")
        assert response.status_code == 400
        assert "error" in response.get_json()

    def test_get_dose_history_alias_path(self, client, repository):
        """GET /dose alias path returns dose history."""
        med = Medication(name="Test Med", dosage="100mg", frequency="daily")
        repository.create(med)

        client.post(f"/medications/{med.id}/doses", json={})

        response = client.get(f"/medications/{med.id}/dose")
        assert response.status_code == 200
        assert len(response.get_json()) == 1


# ---------------------------------------------------------------------------
# Data persistence across app restart
# ---------------------------------------------------------------------------

>>>>>>> 9105369 (runctl: build runctl/build-09d3fc65 (pass))

class TestDataPersistence:
    """Tests for data persistence across app restarts."""

<<<<<<< HEAD
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

=======
    def test_medication_persists_after_restart(self, test_db_path):
        """Medication data persists correctly after app restart."""
        db1 = get_database(test_db_path)
        db1.init_schema()
        repo1 = MedicationRepository(db1)
        med = Medication(name="Persistent Med", dosage="100mg", frequency="daily")
        repo1.create(med)
        original_id = med.id
        db1.close()

        db2 = get_database(test_db_path)
        db2.init_schema()
        repo2 = MedicationRepository(db2)
        retrieved = repo2.get_by_id(original_id)
        assert retrieved is not None
        assert retrieved.name == "Persistent Med"
>>>>>>> 9105369 (runctl: build runctl/build-09d3fc65 (pass))
        db2.close()

    def test_crud_operations_persist_across_restarts(self, test_db_path):
        """Create, update, delete operations persist after restart."""
<<<<<<< HEAD
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

=======
        db1 = get_database(test_db_path)
        db1.init_schema()
        repo1 = MedicationRepository(db1)
        med = Medication(name="Original", dosage="100mg", frequency="daily")
        repo1.create(med)
        med.name = "Updated"
        repo1.update(med)
        db1.close()

        db2 = get_database(test_db_path)
        db2.init_schema()
        repo2 = MedicationRepository(db2)
        retrieved = repo2.get_by_id(med.id)
        assert retrieved.name == "Updated"
>>>>>>> 9105369 (runctl: build runctl/build-09d3fc65 (pass))
        db2.close()

    def test_deleted_medication_stays_deleted(self, test_db_path):
        """Deleted medication remains deleted after restart."""
        db1 = get_database(test_db_path)
        db1.init_schema()
        repo1 = MedicationRepository(db1)
<<<<<<< HEAD

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
=======
        med = Medication(name="ToDelete", dosage="100mg", frequency="daily")
        repo1.create(med)
        repo1.delete(med.id)
        db1.close()

        db2 = get_database(test_db_path)
        db2.init_schema()
        repo2 = MedicationRepository(db2)
        assert repo2.get_by_id(med.id) is None
        db2.close()

    def test_dose_records_persist_after_restart(self, test_db_path):
>>>>>>> 9105369 (runctl: build runctl/build-09d3fc65 (pass))
        """Dose records persist correctly after database restart."""
        db1 = get_database(test_db_path)
        db1.init_schema()
        repo1 = MedicationRepository(db1)
<<<<<<< HEAD

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
=======
        med = Medication(name="Test Med", dosage="100mg", frequency="daily")
        repo1.create(med)
        dose = DoseRecord(medication_id=med.id, date=date.today())
        repo1.create_dose_record(dose)
        db1.close()

        db2 = get_database(test_db_path)
        db2.init_schema()
        repo2 = MedicationRepository(db2)
        records = repo2.get_dose_records(med.id)
        assert len(records) == 1
        assert records[0].medication_id == med.id
        db2.close()


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------


class TestFunctionalMisc:
    """Misc functional tests."""

    def test_health_endpoint(self, client):
        """Health check endpoint returns healthy status."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.get_json()["status"] == "healthy"

    def test_list_includes_all_medication_fields(self, client, repository):
        """Medication list includes all required fields."""
        med = Medication(
            name="Test Med", dosage="100mg", frequency="daily",
            start_date=date(2026, 1, 1), end_date=date(2026, 1, 14),
        )
        repository.create(med)

        response = client.get("/medications")
        medications = response.get_json()
        assert len(medications) == 1
        m = medications[0]
        assert m["name"] == "Test Med"
        assert m["dosage"] == "100mg"
        assert m["frequency"] == "daily"
        assert m["start_date"] == "2026-01-01"
        assert m["end_date"] == "2026-01-14"
        assert m["status"] == "active"
        assert "created_at" in m
        assert "updated_at" in m


# ---------------------------------------------------------------------------
# Milestone evidence capture — build unit #2 (dose tracking)
# ---------------------------------------------------------------------------


class TestDoseTrackingEvidence:
    """Captures a readable console transcript of real API requests and
    responses proving the dose-tracking milestone works end to end.

    The assertions inside are strict — the test fails if any behaviour
    breaks — but it also writes the HTTP transcript to
    .see/e2e-artifacts/console-transcript.txt so the milestone is
    documented with observable evidence rather than just a pass/fail bit.
    """

    @pytest.fixture(autouse=True)
    def _transcript_path(self):
        artifacts_dir = Path(__file__).parent.parent.parent / ".see" / "e2e-artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        self._transcript_file = artifacts_dir / "console-transcript.txt"
        yield

    def _log(self, lines):
        with open(self._transcript_file, "a", encoding="utf-8") as fh:
            fh.writelines(line + "\n" for line in lines)

    def test_dose_tracking_milestone_transcript(self, client, repository):
        """Exercise the full dose-tracking flow and capture an HTTP transcript."""
        from datetime import timedelta

        # Reset transcript for a clean run.
        self._transcript_file.write_text("", encoding="utf-8")
        today = date.today()
        yesterday = today - timedelta(days=1)
        two_days_ago = today - timedelta(days=2)
        tomorrow = today + timedelta(days=1)

        self._log([
            "=" * 72,
            "MEDICINE TRACKER — DOSE TRACKING MILESTONE TRANSCRIPT",
            f"Generated: {today.isoformat()} (pytest functional gate)",
            "=" * 72,
            "",
            "This transcript records real HTTP requests against the Flask test",
            "client proving: mark-as-taken, idempotency (409), dose history with",
            "date-range filtering, future-date rejection (400), and per-medication",
            "dose isolation.",
            "",
        ])

        # --- Step 1: Create a medication to track doses for ---
        self._log(["STEP 1 — POST /medications (create medication)"])
        create_resp = client.post("/medications", json={
            "name": "Metformin",
            "dosage": "500mg",
            "frequency": "twice daily",
            "start_date": two_days_ago.isoformat(),
            "end_date": today.isoformat(),
        })
        assert create_resp.status_code == 201, f"expected 201, got {create_resp.status_code}"
        med_data = create_resp.get_json()
        med_id = med_data["id"]
        self._log([
            f"  Request: POST /medications",
            f"    Body: {{'name': 'Metformin', 'dosage': '500mg', 'frequency': 'twice daily',",
            f"           'start_date': '{two_days_ago.isoformat()}', 'end_date': '{today.isoformat()}'}}",
            f"  Response: {create_resp.status_code} Created",
            f"    {{'id': '{med_id}', 'name': 'Metformin', 'dosage': '500mg',",
            f"     'frequency': 'twice daily', 'status': 'active'}}",
            "",
        ])

        # --- Step 2: Mark a dose as taken for two days ago ---
        self._log(["STEP 2 — POST /medications/<id>/doses (mark taken, past date)"])
        resp2 = client.post(f"/medications/{med_id}/doses", json={
            "date": two_days_ago.isoformat(),
        })
        assert resp2.status_code == 201
        dose2 = resp2.get_json()
        assert dose2["medication_id"] == med_id
        assert dose2["status"] == "taken"
        assert dose2["date"] == two_days_ago.isoformat()
        assert dose2["timestamp"] is not None
        self._log([
            f"  Request: POST /medications/{med_id}/doses",
            f"    Body: {{'date': '{two_days_ago.isoformat()}'}}",
            f"  Response: {resp2.status_code} Created",
            f"    {{'id': '{dose2['id']}', 'medication_id': '{med_id}',",
            f"     'date': '{dose2['date']}', 'timestamp': '{dose2['timestamp']}',",
            f"     'status': 'taken'}}",
            "",
        ])

        # --- Step 3: Mark a dose as taken for yesterday ---
        self._log(["STEP 3 — POST /medications/<id>/doses (mark taken, yesterday)"])
        resp3 = client.post(f"/medications/{med_id}/doses", json={
            "date": yesterday.isoformat(),
        })
        assert resp3.status_code == 201
        dose3 = resp3.get_json()
        assert dose3["date"] == yesterday.isoformat()
        self._log([
            f"  Request: POST /medications/{med_id}/doses",
            f"    Body: {{'date': '{yesterday.isoformat()}'}}",
            f"  Response: {resp3.status_code} Created",
            f"    {{'id': '{dose3['id']}', 'medication_id': '{med_id}',",
            f"     'date': '{dose3['date']}', 'timestamp': '{dose3['timestamp']}',",
            f"     'status': 'taken'}}",
            "",
        ])

        # --- Step 4: Mark a dose as taken for today (default date) ---
        self._log(["STEP 4 — POST /medications/<id>/doses (mark taken, today, no date)"])
        resp4 = client.post(f"/medications/{med_id}/doses", json={})
        assert resp4.status_code == 201
        dose4 = resp4.get_json()
        assert dose4["date"] == today.isoformat()
        self._log([
            f"  Request: POST /medications/{med_id}/doses",
            f"    Body: {{}}  (date defaults to today)",
            f"  Response: {resp4.status_code} Created",
            f"    {{'id': '{dose4['id']}', 'medication_id': '{med_id}',",
            f"     'date': '{dose4['date']}', 'timestamp': '{dose4['timestamp']}',",
            f"     'status': 'taken'}}",
            "",
        ])

        # --- Step 5: Duplicate mark for today — expect 409 ---
        self._log(["STEP 5 — POST /medications/<id>/doses (duplicate, expect 409)"])
        resp5 = client.post(f"/medications/{med_id}/doses", json={})
        assert resp5.status_code == 409
        assert "error" in resp5.get_json()
        self._log([
            f"  Request: POST /medications/{med_id}/doses",
            f"    Body: {{}}  (already taken today)",
            f"  Response: {resp5.status_code} Conflict",
            f"    {{'error': '{resp5.get_json()['error']}'}}",
            f"  => Idempotency enforced: second mark-as-taken for the same date",
            f"     is rejected with 409, proving the unique (medication_id, date)",
            f"     constraint works.",
            "",
        ])

        # --- Step 6: Future date — expect 400 ---
        self._log(["STEP 6 — POST /medications/<id>/doses (future date, expect 400)"])
        resp6 = client.post(f"/medications/{med_id}/doses", json={
            "date": tomorrow.isoformat(),
        })
        assert resp6.status_code == 400
        assert "error" in resp6.get_json()
        self._log([
            f"  Request: POST /medications/{med_id}/doses",
            f"    Body: {{'date': '{tomorrow.isoformat()}'}}  (future date)",
            f"  Response: {resp6.status_code} Bad Request",
            f"    {{'error': '{resp6.get_json()['error']}'}}",
            f"  => Future dates are rejected, proving dose validation.",
            "",
        ])

        # --- Step 7: GET dose history (full) ---
        self._log(["STEP 7 — GET /medications/<id>/doses (full history)"])
        resp7 = client.get(f"/medications/{med_id}/doses")
        assert resp7.status_code == 200
        history = resp7.get_json()
        assert len(history) == 3
        assert history[0]["date"] == today.isoformat()
        assert history[1]["date"] == yesterday.isoformat()
        assert history[2]["date"] == two_days_ago.isoformat()
        self._log([
            f"  Request: GET /medications/{med_id}/doses",
            f"  Response: {resp7.status_code} OK",
            f"    [",
        ])
        for record in history:
            self._log([
                f"      {{'id': '{record['id']}', 'date': '{record['date']}',",
                f"       'timestamp': '{record['timestamp']}', 'status': '{record['status']}'}}",
            ])
        self._log([
            f"    ]",
            f"  => 3 doses returned, sorted by date descending.",
            "",
        ])

        # --- Step 8: GET dose history with date-range filter ---
        self._log(["STEP 8 — GET /medications/<id>/doses?start=&end= (date range filter)"])
        resp8 = client.get(
            f"/medications/{med_id}/doses?start={yesterday.isoformat()}&end={today.isoformat()}"
        )
        assert resp8.status_code == 200
        filtered = resp8.get_json()
        assert len(filtered) == 2
        assert all(yesterday.isoformat() <= r["date"] <= today.isoformat() for r in filtered)
        self._log([
            f"  Request: GET /medications/{med_id}/doses?start={yesterday.isoformat()}&end={today.isoformat()}",
            f"  Response: {resp8.status_code} OK",
            f"    [",
        ])
        for record in filtered:
            self._log([
                f"      {{'id': '{record['id']}', 'date': '{record['date']}',",
                f"       'timestamp': '{record['timestamp']}', 'status': '{record['status']}'}}",
            ])
        self._log([
            f"    ]",
            f"  => 2 doses in range [yesterday, today]; the two_days_ago dose is excluded.",
            "",
        ])

        # --- Step 9: Per-medication dose isolation ---
        self._log(["STEP 9 — Per-medication dose isolation (second medication, same day)"])
        med2_resp = client.post("/medications", json={
            "name": "Atorvastatin", "dosage": "20mg", "frequency": "daily",
        })
        assert med2_resp.status_code == 201
        med2_id = med2_resp.get_json()["id"]
        iso_resp = client.post(f"/medications/{med2_id}/doses", json={})
        assert iso_resp.status_code == 201
        assert iso_resp.get_json()["date"] == today.isoformat()
        self._log([
            f"  Created medication 2: {med2_id} (Atorvastatin 20mg)",
            f"  POST /medications/{med2_id}/doses -> {iso_resp.status_code} Created",
            f"    {{'date': '{iso_resp.get_json()['date']}', 'status': 'taken'}}",
            f"  => Same-day dose allowed for a DIFFERENT medication — the unique",
            f"     constraint is scoped to (medication_id, date), not date alone.",
            "",
        ])

        self._log([
            "=" * 72,
            "MILESTONE VERIFIED: dose tracking creates timestamped records,",
            "enforces idempotency (409), supports date-range history queries,",
            "rejects future dates (400), and isolates doses per medication.",
            "=" * 72,
        ])
>>>>>>> 9105369 (runctl: build runctl/build-09d3fc65 (pass))
