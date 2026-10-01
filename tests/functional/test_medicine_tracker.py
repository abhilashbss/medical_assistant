"""Functional tests for medicine tracker feature.

This module tests:
- API integration for adding, editing, deleting medications
- Validation of required fields (name, dosage)
- Mark-as-taken action creates timestamped dose records
- Status filtering (active vs completed)
- Data persistence across app restarts
<<<<<<< HEAD
"""

=======

A console transcript of real HTTP request/response pairs is captured into
.see/e2e-artifacts/console-transcript.txt to provide milestone-level evidence
that the medication list UI's backend contract works end-to-end.
"""

import json
>>>>>>> 47172f7 (runctl: build runctl/build-5c677d80 (pass))
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


<<<<<<< HEAD
=======
# --- Transcript capture infrastructure ---------------------------------------

EVIDENCE_DIR = Path(__file__).parent.parent.parent / '.see' / 'e2e-artifacts'
_TRANSCRIPT_LINES: list = []


def _record_exchange(method, path, status_code, body=None, response_body=None):
    """Record a single HTTP request/response pair into the transcript."""
    line = f"\n{method} {path}\n  -> HTTP {status_code}"
    if body is not None:
        line += f"\n  request body: {json.dumps(body)}"
    if response_body is not None:
        if isinstance(response_body, (dict, list)):
            line += f"\n  response body: {json.dumps(response_body)}"
        else:
            line += f"\n  response body: {response_body}"
    _TRANSCRIPT_LINES.append(line)


class _TranscriptClient:
    """Wrapper around the Flask test client that logs each request/response."""

    def __init__(self, client):
        self._client = client

    def _log(self, method, path, response, body=None):
        try:
            resp_body = response.get_json()
        except Exception:
            resp_body = response.get_data(as_text=True)
        _record_exchange(method, path, response.status_code, body=body,
                         response_body=resp_body)
        return response

    def get(self, path, **kwargs):
        response = self._client.get(path, **kwargs)
        return self._log('GET', path, response)

    def post(self, path, json=None, **kwargs):
        response = self._client.post(path, json=json, **kwargs)
        return self._log('POST', path, response, body=json)

    def put(self, path, json=None, **kwargs):
        response = self._client.put(path, json=json, **kwargs)
        return self._log('PUT', path, response, body=json)

    def delete(self, path, **kwargs):
        response = self._client.delete(path, **kwargs)
        return self._log('DELETE', path, response)

    def __getattr__(self, name):
        # Delegate any other accessors (e.g. .get_data) to the wrapped client.
        return getattr(self._client, name)


>>>>>>> 47172f7 (runctl: build runctl/build-5c677d80 (pass))
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
<<<<<<< HEAD
    """Create test client for Flask app."""
=======
    """Create test client for Flask app, wrapped to capture a transcript."""
    return _TranscriptClient(app.test_client())


@pytest.fixture
def raw_client(app):
    """Unwrapped test client for tests that need direct access."""
>>>>>>> 47172f7 (runctl: build runctl/build-5c677d80 (pass))
    return app.test_client()


@pytest.fixture
def repository(test_db_path):
    """Create a medication repository for testing."""
    db = get_database(test_db_path)
    db.init_schema()
    return MedicationRepository(db)


<<<<<<< HEAD
=======
@pytest.fixture(autouse=True)
def _transcript_section(request):
    """Mark each test's transcript entries with a section header."""
    _TRANSCRIPT_LINES.append(f"\n\n=== {request.node.nodeid} ===")
    yield
    _TRANSCRIPT_LINES.append(f"\n--- end {request.node.nodeid} ---")


def _write_transcript():
    """Flush the captured transcript to the evidence directory."""
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    header = (
        "=== MEDICATION TRACKER — MILESTONE EVIDENCE CONSOLE TRANSCRIPT ===\n"
        f"Date: {date.today().isoformat()}\n"
        "Gate command: pytest tests/functional/test_medicine_tracker.py -v --cov\n"
        "Evidence type: readable console transcript of real HTTP request/response pairs\n"
        "Captured from: Flask test client exercising the medication list UI backend contract\n"
        "\nBelow is every HTTP exchange the functional gate performed against the app:\n"
    )
    (EVIDENCE_DIR / 'console-transcript.txt').write_text(
        header + "\n".join(_TRANSCRIPT_LINES) + "\n"
    )


@pytest.fixture(scope='session', autouse=True)
def _flush_transcript(request):
    """Write the transcript to disk once the full session completes."""
    yield
    _write_transcript()


>>>>>>> 47172f7 (runctl: build runctl/build-5c677d80 (pass))
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
<<<<<<< HEAD
        response = client.post(f'/medications/{medication.id}/dose', json={})
=======
        response = client.post(f'/medications/{medication.id}/doses', json={})
>>>>>>> 47172f7 (runctl: build runctl/build-5c677d80 (pass))
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

<<<<<<< HEAD
        response = client.post(f'/medications/{medication.id}/dose', json={
=======
        response = client.post(f'/medications/{medication.id}/doses', json={
>>>>>>> 47172f7 (runctl: build runctl/build-5c677d80 (pass))
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
<<<<<<< HEAD
=======


class TestMedicationListUIIntegration:
    """Functional tests for the medication list UI and its API integration.

    These tests exercise the contract the component-based frontend relies on:
    static asset delivery, filter re-querying, edit form pre-population via
    GET-by-id, delete confirmation flow, and optimistic-update rollback support.
    """

    def test_index_page_serves_component_html(self, client):
        """The index page loads and references the component JS/CSS bundles."""
        response = client.get('/')
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert 'js/app.js' in html
        assert 'js/medication-list.js' in html
        assert 'js/medication-form.js' in html
        assert 'js/delete-dialog.js' in html
        assert 'css/styles.css' in html
        # Filter toggle buttons present for All/Active/Completed.
        assert 'data-filter="all"' in html
        assert 'data-filter="active"' in html
        assert 'data-filter="completed"' in html

    def test_static_component_assets_are_served(self, client):
        """Each frontend component file is retrievable via its static URL."""
        for asset in ('js/api.js', 'js/toast.js', 'js/medication-form.js',
                      'js/delete-dialog.js', 'js/medication-list.js',
                      'js/app.js', 'css/styles.css'):
            response = client.get(f'/{asset}')
            assert response.status_code == 200, f"{asset} returned {response.status_code}"
            assert len(response.get_data()) > 0, f"{asset} is empty"

    def test_filter_requery_returns_only_matching_status(self, client, repository):
        """Switching the filter re-queries the API and returns only matching medications."""
        active = Medication(name='Active Med', dosage='100mg', frequency='daily')
        completed = Medication(
            name='Completed Med', dosage='200mg', frequency='daily',
            status=MedicationStatus.COMPLETED,
        )
        repository.create(active)
        repository.create(completed)

        # All filter
        all_resp = client.get('/medications?status=all')
        assert all_resp.status_code == 200
        assert len(all_resp.get_json()) == 2

        # Active filter
        active_resp = client.get('/medications?status=active')
        assert active_resp.status_code == 200
        active_meds = active_resp.get_json()
        assert len(active_meds) == 1
        assert active_meds[0]['name'] == 'Active Med'
        assert all(m['status'] == 'active' for m in active_meds)

        # Completed filter
        completed_resp = client.get('/medications?status=completed')
        assert completed_resp.status_code == 200
        completed_meds = completed_resp.get_json()
        assert len(completed_meds) == 1
        assert completed_meds[0]['name'] == 'Completed Med'
        assert all(m['status'] == 'completed' for m in completed_meds)

    def test_edit_form_prepopulation_via_get_by_id(self, client, repository):
        """Edit action fetches the medication by ID to pre-populate the form."""
        medication = Medication(
            name='Original',
            dosage='100mg',
            frequency='daily',
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 14),
            status=MedicationStatus.ACTIVE,
        )
        repository.create(medication)

        response = client.get(f'/medications/{medication.id}')
        assert response.status_code == 200
        data = response.get_json()
        # Every field the form pre-populates must be present and correct.
        assert data['id'] == str(medication.id)
        assert data['name'] == 'Original'
        assert data['dosage'] == '100mg'
        assert data['frequency'] == 'daily'
        assert data['start_date'] == '2026-01-01'
        assert data['end_date'] == '2026-01-14'
        assert data['status'] == 'active'

    def test_edit_save_persists_via_put(self, client, repository):
        """Submitting the edit form calls PUT and changes persist."""
        medication = Medication(
            name='Original', dosage='100mg', frequency='daily',
        )
        repository.create(medication)

        response = client.put(f'/medications/{medication.id}', json={
            'name': 'Edited Name',
            'dosage': '250mg',
            'frequency': 'three times daily',
            'status': 'completed',
        })
        assert response.status_code == 200
        updated = response.get_json()
        assert updated['name'] == 'Edited Name'
        assert updated['dosage'] == '250mg'
        assert updated['frequency'] == 'three times daily'
        assert updated['status'] == 'completed'

        # Persistence verified via fresh repository read.
        retrieved = repository.get_by_id(medication.id)
        assert retrieved.name == 'Edited Name'
        assert retrieved.dosage == '250mg'
        assert retrieved.status == MedicationStatus.COMPLETED

    def test_delete_confirmation_flow_removes_medication(self, client, repository):
        """Delete confirmation calls DELETE and removes the medication from the list."""
        medication = Medication(
            name='ToDelete', dosage='50mg', frequency='daily',
        )
        repository.create(medication)

        delete_resp = client.delete(f'/medications/{medication.id}')
        assert delete_resp.status_code == 204

        # The medication is no longer in the list.
        list_resp = client.get('/medications')
        assert list_resp.status_code == 200
        medications = list_resp.get_json()
        assert len(medications) == 0

        # And a direct GET returns 404.
        get_resp = client.get(f'/medications/{medication.id}')
        assert get_resp.status_code == 404

    def test_full_list_filter_edit_delete_cycle(self, client, repository):
        """Full cycle: add (via repo), list, filter, edit, delete — UI flow contract."""
        med1 = Medication(name='Med One', dosage='100mg', frequency='daily')
        med2 = Medication(name='Med Two', dosage='200mg', frequency='daily',
                          status=MedicationStatus.COMPLETED)
        repository.create(med1)
        repository.create(med2)

        # List all (sorted most-recent first)
        all_resp = client.get('/medications')
        all_meds = all_resp.get_json()
        assert len(all_meds) == 2

        # Filter active shows only med1
        active_resp = client.get('/medications?status=active')
        assert len(active_resp.get_json()) == 1
        assert active_resp.get_json()[0]['name'] == 'Med One'

        # Edit med1 to completed via PUT (simulating edit form submit)
        edit_resp = client.put(f'/medications/{med1.id}', json={'status': 'completed'})
        assert edit_resp.status_code == 200
        assert edit_resp.get_json()['status'] == 'completed'

        # Now active filter is empty, completed has 2
        assert len(client.get('/medications?status=active').get_json()) == 0
        assert len(client.get('/medications?status=completed').get_json()) == 2

        # Delete med2
        del_resp = client.delete(f'/medications/{med2.id}')
        assert del_resp.status_code == 204

        # All filter now has 1 (med1, which is completed)
        remaining = client.get('/medications').get_json()
        assert len(remaining) == 1
        assert remaining[0]['name'] == 'Med One'

    def test_invalid_filter_value_returns_400(self, client):
        """An invalid status filter returns a 400 error (UI shows error toast)."""
        response = client.get('/medications?status=invalid')
        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data

    def test_empty_state_api_contract(self, client):
        """Empty active filter returns an empty array (UI shows empty state CTA)."""
        response = client.get('/medications?status=active')
        assert response.status_code == 200
        assert response.get_json() == []
>>>>>>> 47172f7 (runctl: build runctl/build-5c677d80 (pass))
