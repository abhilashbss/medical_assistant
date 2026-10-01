"""Unit tests for the medication tracker persistence layer and edge cases.

Covers (per gate criteria):
  * Medication entity creation with required fields persists to database
  * Validation rejects incomplete entries missing required fields
  * Mark-as-taken creates timestamped dose record with correct current-day timestamp
  * Edit and delete operations correctly modify/remove entries
  * Medication list retrieval returns correct data sorted by most recently added
    with status filtering
Plus edge cases: past end dates, overlapping schedules, invalid date ranges,
data integrity verification, and persistence across simulated restarts.
"""

import os
import tempfile
from datetime import datetime, timedelta

import pytest

from medication_tracker.db import Database
from medication_tracker.service import MedicationService, ValidationError
from medication_tracker.models import Medication
from medication_tracker.persistence import (
    verify_persistence,
    recover_corrupted,
    auto_complete_past_end_dates,
    load_and_reconcile,
)


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "test_medications.db")
    database = Database(path)
    database.reset()
    yield database


@pytest.fixture
def service(db):
    return MedicationService(db)


# --- Creation & persistence ---------------------------------------------

class TestCreation:
    def test_create_with_required_fields_persists(self, service, db):
        med = service.create(name="Amoxicillin", dosage="500mg", frequency="3x daily")
        assert med.id is not None
        assert med.name == "Amoxicillin"
        assert med.dosage == "500mg"
        assert med.frequency == "3x daily"
        assert med.status == "active"

        # Persisted to disk: re-open a fresh Database (simulates restart)
        reopened = Database(db.path)
        fetched = MedicationService(reopened).get(med.id)
        assert fetched is not None
        assert fetched.name == "Amoxicillin"
        assert fetched.dosage == "500mg"

    def test_create_with_dates_persists(self, service):
        med = service.create(
            name="Metformin", dosage="850mg", frequency="2x daily",
            start_date="2026-01-01", end_date="2026-06-30",
        )
        assert med.start_date == "2026-01-01"
        assert med.end_date == "2026-06-30"


# --- Validation ---------------------------------------------------------

class TestValidation:
    @pytest.mark.parametrize("name,dosage,frequency", [
        (None, "500mg", "3x daily"),
        ("", "500mg", "3x daily"),
        ("   ", "500mg", "3x daily"),
        ("Amox", None, "3x daily"),
        ("Amox", "", "3x daily"),
        ("Amox", "500mg", None),
        ("Amox", "500mg", ""),
        (123, "500mg", "3x daily"),   # non-string name
        ("Amox", 500, "3x daily"),    # non-string dosage
    ])
    def test_rejects_incomplete_entries(self, service, name, dosage, frequency):
        with pytest.raises(ValidationError):
            service.create(name=name, dosage=dosage, frequency=frequency)

    def test_rejects_invalid_status(self, service):
        with pytest.raises(ValidationError):
            service.create(name="X", dosage="10mg", frequency="1x daily", status="bogus")

    def test_rejects_invalid_date_format(self, service):
        with pytest.raises(ValidationError):
            service.create(name="X", dosage="10mg", frequency="1x daily", start_date="01/15/2026")

    def test_rejects_start_after_end(self, service):
        with pytest.raises(ValidationError):
            service.create(
                name="X", dosage="10mg", frequency="1x daily",
                start_date="2026-06-30", end_date="2026-01-01",
            )

    def test_update_validation_rejects_missing_fields(self, service):
        med = service.create(name="X", dosage="10mg", frequency="1x daily")
        with pytest.raises(ValidationError):
            service.update(med.id, name="")
        with pytest.raises(ValidationError):
            service.update(med.id, dosage="")


# --- Mark as taken ------------------------------------------------------

class TestDoseTracking:
    def test_mark_as_taken_creates_timestamped_record(self, service):
        med = service.create(name="Amox", dosage="500mg", frequency="3x daily")
        now = datetime(2026, 3, 15, 9, 30, 0)
        record = service.mark_as_taken(med.id, when=now)
        assert record.medication_id == med.id
        assert record.date == "2026-03-15"
        assert record.timestamp == now.isoformat()
        assert record.status == "taken"

    def test_mark_as_taken_current_day_by_default(self, service):
        med = service.create(name="Amox", dosage="500mg", frequency="3x daily")
        record = service.mark_as_taken(med.id)
        today = datetime.utcnow().strftime("%Y-%m-%d")
        assert record.date == today

    def test_mark_as_taken_idempotent_per_day(self, service):
        med = service.create(name="Amox", dosage="500mg", frequency="3x daily")
        t1 = datetime(2026, 3, 15, 9, 0, 0)
        t2 = datetime(2026, 3, 15, 21, 0, 0)
        first = service.mark_as_taken(med.id, when=t1)
        second = service.mark_as_taken(med.id, when=t2)
        assert first.id == second.id, "second call same day should return existing record"
        history = service.dose_history(med.id)
        assert len(history) == 1

    def test_dose_history_filtered_by_date_range(self, service):
        med = service.create(name="Amox", dosage="500mg", frequency="3x daily")
        service.mark_as_taken(med.id, when=datetime(2026, 3, 10))
        service.mark_as_taken(med.id, when=datetime(2026, 3, 15))
        service.mark_as_taken(med.id, when=datetime(2026, 3, 20))
        history = service.dose_history(med.id, start_date="2026-03-12", end_date="2026-03-18")
        assert len(history) == 1
        assert history[0].date == "2026-03-15"

    def test_mark_as_taken_persists_across_restart(self, service, db):
        med = service.create(name="Amox", dosage="500mg", frequency="3x daily")
        service.mark_as_taken(med.id, when=datetime(2026, 3, 15, 8, 0))
        reopened = Database(db.path)
        new_service = MedicationService(reopened)
        history = new_service.dose_history(med.id)
        assert len(history) == 1
        assert history[0].date == "2026-03-15"


# --- Edit & delete ------------------------------------------------------

class TestEditDelete:
    def test_edit_persists_changes(self, service, db):
        med = service.create(name="Amox", dosage="250mg", frequency="2x daily")
        updated = service.update(med.id, dosage="500mg", frequency="3x daily")
        assert updated.dosage == "500mg"
        assert updated.frequency == "3x daily"

        reopened = Database(db.path)
        fetched = MedicationService(reopened).get(med.id)
        assert fetched.dosage == "500mg"
        assert fetched.frequency == "3x daily"

    def test_edit_persists_across_sessions(self, service, db):
        med = service.create(name="Amox", dosage="250mg", frequency="2x daily")
        service.update(med.id, name="Amoxicillin")
        reopened = Database(db.path)
        fetched = MedicationService(reopened).get(med.id)
        assert fetched.name == "Amoxicillin"

    def test_delete_removes_entry(self, service):
        med = service.create(name="Amox", dosage="250mg", frequency="2x daily")
        assert service.delete(med.id) is True
        assert service.get(med.id) is None

    def test_delete_missing_returns_false(self, service):
        assert service.delete(99999) is False


# --- List retrieval & sorting -------------------------------------------

class TestListRetrieval:
    def test_sorted_by_most_recently_added(self, service):
        first = service.create(name="A", dosage="10mg", frequency="1x daily")
        second = service.create(name="B", dosage="20mg", frequency="1x daily")
        third = service.create(name="C", dosage="30mg", frequency="1x daily")
        meds = service.list()
        assert [m.name for m in meds] == ["C", "B", "A"]

    def test_status_filter_active(self, service):
        a = service.create(name="A", dosage="10mg", frequency="1x daily")
        b = service.create(name="B", dosage="20mg", frequency="1x daily")
        service.set_status(b.id, "completed")
        active = service.list(status_filter="active")
        assert [m.name for m in active] == ["A"]
        completed = service.list(status_filter="completed")
        assert [m.name for m in completed] == ["B"]

    def test_status_filter_all(self, service):
        service.create(name="A", dosage="10mg", frequency="1x daily")
        service.create(name="B", dosage="20mg", frequency="1x daily", status="completed")
        all_meds = service.list(status_filter="all")
        assert len(all_meds) == 2


# --- Persistence verification (Build unit #4) ---------------------------

class TestPersistenceVerification:
    def test_verify_persistence_returns_all_rows(self, service, db):
        service.create(name="A", dosage="10mg", frequency="1x daily")
        service.create(name="B", dosage="20mg", frequency="2x daily")
        report = verify_persistence(db)
        assert report["total"] == 2
        assert len(report["intact"]) == 2
        assert report["corrupted"] == []

    def test_verify_persistence_detects_corruption(self, db):
        # Insert a row with an empty-string required field directly to simulate
        # corruption that bypassed application-layer validation.
        conn = db.connect()
        now = datetime.utcnow().isoformat()
        conn.execute(
            "INSERT INTO medications (name, dosage, frequency, status, created_at, updated_at) "
            "VALUES ('', '10mg', '1x daily', 'active', ?, ?)",
            (now, now),
        )
        conn.commit()
        conn.close()
        report = verify_persistence(db)
        assert report["total"] == 1
        assert len(report["corrupted"]) == 1
        assert "name" in report["corrupted"][0]["problems"]

    def test_verify_persistence_detects_invalid_status_and_date_range(self, db):
        conn = db.connect()
        now = datetime.utcnow().isoformat()
        conn.execute(
            "INSERT INTO medications (name, dosage, frequency, start_date, end_date, status, created_at, updated_at) "
            "VALUES ('X', '10mg', '1x daily', '2026-06-30', '2026-01-01', 'bogus', ?, ?)",
            (now, now),
        )
        conn.commit()
        conn.close()
        report = verify_persistence(db)
        assert report["total"] == 1
        problems = report["corrupted"][0]["problems"]
        assert "status" in problems
        assert "date_range" in problems

    def test_recover_corrupted_removes_bad_records(self, db):
        conn = db.connect()
        now = datetime.utcnow().isoformat()
        conn.execute(
            "INSERT INTO medications (name, dosage, frequency, status, created_at, updated_at) "
            "VALUES ('', '10mg', '1x daily', 'active', ?, ?)",
            (now, now),
        )
        conn.commit()
        conn.close()
        removed = recover_corrupted(db)
        assert removed == [1]
        report = verify_persistence(db)
        assert report["total"] == 0

    def test_recover_keeps_valid_records(self, service, db):
        service.create(name="A", dosage="10mg", frequency="1x daily")
        removed = recover_corrupted(db)
        assert removed == []
        assert len(verify_persistence(db)["intact"]) == 1


# --- Edge cases ---------------------------------------------------------

class TestEdgeCases:
    def test_past_end_date_auto_completes(self, service):
        med = service.create(
            name="Old", dosage="10mg", frequency="1x daily",
            start_date="2020-01-01", end_date="2020-02-01",
        )
        changed = auto_complete_past_end_dates(service, today="2026-10-01")
        assert len(changed) == 1
        assert changed[0].status == "completed"
        assert service.get(med.id).status == "completed"

    def test_future_end_date_not_auto_completed(self, service):
        med = service.create(
            name="Current", dosage="10mg", frequency="1x daily",
            start_date="2026-09-01", end_date="2026-12-01",
        )
        changed = auto_complete_past_end_dates(service, today="2026-10-01")
        assert changed == []
        assert service.get(med.id).status == "active"

    def test_no_end_date_not_auto_completed(self, service):
        med = service.create(name="Ongoing", dosage="10mg", frequency="1x daily")
        changed = auto_complete_past_end_dates(service, today="2026-10-01")
        assert changed == []

    def test_already_completed_not_re_changed(self, service):
        med = service.create(
            name="Done", dosage="10mg", frequency="1x daily",
            start_date="2020-01-01", end_date="2020-02-01", status="completed",
        )
        changed = auto_complete_past_end_dates(service, today="2026-10-01")
        assert changed == []
        assert service.get(med.id).status == "completed"

    def test_overlapping_schedules_display_without_duplication(self, service):
        """Two medications with overlapping date ranges each appear once,
        sorted by most recently added (chronological insertion order)."""
        a = service.create(
            name="MedA", dosage="10mg", frequency="1x daily",
            start_date="2026-01-01", end_date="2026-06-30",
        )
        b = service.create(
            name="MedB", dosage="20mg", frequency="2x daily",
            start_date="2026-03-01", end_date="2026-09-30",
        )
        meds = service.list()
        assert len(meds) == 2
        assert [m.name for m in meds] == ["MedB", "MedA"]  # newest first
        ids = [m.id for m in meds]
        assert len(ids) == len(set(ids)), "no duplication"

    def test_load_and_reconcile_full_flow(self, db):
        service = MedicationService(db)
        service.create(name="Good", dosage="10mg", frequency="1x daily")
        service.create(
            name="OldMed", dosage="5mg", frequency="1x daily",
            start_date="2020-01-01", end_date="2020-02-01",
        )
        # inject corruption (empty-string name bypasses NOT NULL but fails integrity check)
        conn = db.connect()
        now = datetime.utcnow().isoformat()
        conn.execute(
            "INSERT INTO medications (name, dosage, frequency, status, created_at, updated_at) "
            "VALUES ('', '10mg', '1x daily', 'active', ?, ?)",
            (now, now),
        )
        conn.commit()
        conn.close()

        result = load_and_reconcile(db, today="2026-10-01")
        assert len(result["removed"]) == 1
        assert len(result["auto_completed"]) == 1
        final = result["final"]
        assert final["total"] == 2
        assert all(r["status"] in ("active", "completed") for r in final["intact"])


# --- Persistence across restart -----------------------------------------

class TestRestarts:
    def test_data_survives_restart(self, service, db):
        m1 = service.create(name="A", dosage="10mg", frequency="1x daily")
        m2 = service.create(name="B", dosage="20mg", frequency="2x daily")
        service.mark_as_taken(m1.id, when=datetime(2026, 5, 1, 8, 0))

        # Simulate restart: brand new Database + Service at same path
        reopened_db = Database(db.path)
        reopened_service = MedicationService(reopened_db)
        meds = reopened_service.list()
        assert {m.name for m in meds} == {"A", "B"}
        history = reopened_service.dose_history(m1.id)
        assert len(history) == 1
        assert history[0].date == "2026-05-01"

    def test_restart_preserves_status_filtering(self, service, db):
        a = service.create(name="A", dosage="10mg", frequency="1x daily")
        b = service.create(name="B", dosage="20mg", frequency="2x daily", status="completed")
        reopened_db = Database(db.path)
        reopened_service = MedicationService(reopened_db)
        assert len(reopened_service.list(status_filter="active")) == 1
        assert len(reopened_service.list(status_filter="completed")) == 1