"""Functional tests for the medicine tracker — end-to-end scenarios.

Exercises the full flow against a real SQLite database file on disk, including
simulated app restarts, to satisfy the gate criteria:
  * Medication with name, dosage, frequency, start/end date is added and
    retrieved correctly after app restart
  * Medication list displays entries sorted by most recently added with
    active/completed status filtering working
  * Editing a medication persists changes across sessions and mark-as-taken
    creates timestamped dose records
  * Deleting a medication removes it from the list and validation rejects
    entries missing name or dosage
  * Dosage and frequency fields reject empty or non-string inputs with
    appropriate error messages
"""

from datetime import datetime
from pathlib import Path

import pytest

from medication_tracker.db import Database
from medication_tracker.service import MedicationService, ValidationError
from medication_tracker.persistence import (
    verify_persistence,
    load_and_reconcile,
)

# Repository root — two levels up from tests/functional/test_medicine_tracker.py.
REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_DIR = REPO_ROOT / ".see" / "e2e-artifacts"


@pytest.fixture
def stack(tmp_path):
    """A fresh database + service at a temporary on-disk path."""
    path = str(tmp_path / "functional.db")
    db = Database(path)
    db.reset()
    service = MedicationService(db)
    return db, service, path


def reopen(path):
    """Simulate an app restart by opening a new Database at the same path."""
    return MedicationService(Database(path))


class TestFunctionalAddRetrieve:
    def test_add_and_retrieve_after_restart(self, stack):
        db, service, path = stack
        med = service.create(
            name="Lisinopril", dosage="10mg", frequency="1x daily",
            start_date="2026-01-01", end_date="2026-12-31",
        )
        assert med.id is not None

        restarted = reopen(path)
        fetched = restarted.get(med.id)
        assert fetched is not None
        assert fetched.name == "Lisinopril"
        assert fetched.dosage == "10mg"
        assert fetched.frequency == "1x daily"
        assert fetched.start_date == "2026-01-01"
        assert fetched.end_date == "2026-12-31"


class TestFunctionalListFiltering:
    def test_list_sorted_most_recent_with_filtering(self, stack):
        db, service, path = stack
        a = service.create(name="MedA", dosage="10mg", frequency="1x daily")
        b = service.create(name="MedB", dosage="20mg", frequency="2x daily")
        c = service.create(name="MedC", dosage="30mg", frequency="3x daily", status="completed")

        restarted = reopen(path)
        all_meds = restarted.list()
        assert [m.name for m in all_meds] == ["MedC", "MedB", "MedA"]

        active = restarted.list(status_filter="active")
        assert [m.name for m in active] == ["MedB", "MedA"]

        completed = restarted.list(status_filter="completed")
        assert [m.name for m in completed] == ["MedC"]


class TestFunctionalEditMarkTaken:
    def test_edit_persists_across_sessions_and_mark_taken_records(self, stack):
        db, service, path = stack
        med = service.create(name="Atorvastatin", dosage="20mg", frequency="1x daily")

        # Edit in first session
        service.update(med.id, dosage="40mg", frequency="2x daily")
        # Mark as taken
        when = datetime(2026, 4, 1, 7, 30, 0)
        record = service.mark_as_taken(med.id, when=when)
        assert record.date == "2026-04-01"
        assert record.timestamp == when.isoformat()

        # Restart and verify both persisted
        restarted = reopen(path)
        fetched = restarted.get(med.id)
        assert fetched.dosage == "40mg"
        assert fetched.frequency == "2x daily"
        history = restarted.dose_history(med.id)
        assert len(history) == 1
        assert history[0].date == "2026-04-01"


class TestFunctionalDeleteValidation:
    def test_delete_removes_from_list(self, stack):
        db, service, path = stack
        a = service.create(name="Keep", dosage="10mg", frequency="1x daily")
        b = service.create(name="Drop", dosage="20mg", frequency="2x daily")
        assert service.delete(b.id) is True

        restarted = reopen(path)
        names = [m.name for m in restarted.list()]
        assert names == ["Keep"]

    def test_validation_rejects_missing_name_or_dosage(self, stack):
        db, service, path = stack
        with pytest.raises(ValidationError) as exc:
            service.create(name=None, dosage="10mg", frequency="1x daily")
        assert "name" in str(exc.value).lower()

        with pytest.raises(ValidationError) as exc:
            service.create(name="X", dosage=None, frequency="1x daily")
        assert "dosage" in str(exc.value).lower()

    def test_dosage_frequency_reject_empty_and_nonstring(self, stack):
        db, service, path = stack
        # empty strings
        with pytest.raises(ValidationError):
            service.create(name="X", dosage="", frequency="1x daily")
        with pytest.raises(ValidationError):
            service.create(name="X", dosage="10mg", frequency="")
        # non-string inputs
        with pytest.raises(ValidationError):
            service.create(name="X", dosage=500, frequency="1x daily")
        with pytest.raises(ValidationError):
            service.create(name="X", dosage="10mg", frequency=3)


class TestFunctionalPersistenceGuarantees:
    def test_persistence_verification_after_restart(self, stack):
        db, service, path = stack
        service.create(name="Med1", dosage="10mg", frequency="1x daily")
        service.create(name="Med2", dosage="20mg", frequency="2x daily")

        # Restart and verify integrity
        reopened_db = Database(path)
        report = verify_persistence(reopened_db)
        assert report["total"] == 2
        assert len(report["corrupted"]) == 0

    def test_load_and_reconcile_on_startup(self, stack):
        db, service, path = stack
        # an active med with a past end date — should be auto-completed on load
        service.create(
            name="Expired", dosage="10mg", frequency="1x daily",
            start_date="2020-01-01", end_date="2020-06-01",
        )
        service.create(name="Current", dosage="20mg", frequency="1x daily")

        # Restart with full load+reconcile
        reopened_db = Database(path)
        result = load_and_reconcile(reopened_db, today="2026-10-01")
        assert len(result["auto_completed"]) == 1
        assert result["removed"] == []
        assert result["final"]["total"] == 2

        restarted = reopen(path)
        active = restarted.list(status_filter="active")
        completed = restarted.list(status_filter="completed")
        assert [m.name for m in active] == ["Current"]
        assert [m.name for m in completed] == ["Expired"]


# ---------------------------------------------------------------------------
# Evidence capture — milestone transcript for Build unit #4.
#
# This test exercises the same real service/persistence behaviour the
# functional tests above assert, but additionally records a readable
# console-style transcript of every operation and its response into
# .see/e2e-artifacts/console-transcript.txt. The transcript proves the
# milestone works end-to-end: create -> restart-retrieve -> list+filter ->
# edit -> mark-as-taken -> delete -> validation -> auto-complete past end
# date -> corruption recovery. All assertions below remain real and must
# still fail if the behaviour is broken; the transcript is a side-effect of
# passing them.
# ---------------------------------------------------------------------------


class TestMilestoneEvidenceCapture:
    def test_records_console_transcript_of_milestone_flow(self, tmp_path):
        path = str(tmp_path / "evidence.db")
        db = Database(path)
        db.reset()
        service = MedicationService(db)

        lines: list = []
        sep = "=" * 72

        def log(label: str, payload) -> None:
            if isinstance(payload, str):
                lines.append(f"$ {label}\n{payload}")
            else:
                lines.append(f"$ {label}\n{payload!r}")

        def section(title: str) -> None:
            lines.append("")
            lines.append(sep)
            lines.append(title)
            lines.append(sep)

        # --- Create with full fields -------------------------------------
        section("STEP 1 — create medication (name, dosage, frequency, dates)")
        med = service.create(
            name="Lisinopril", dosage="10mg", frequency="1x daily",
            start_date="2026-01-01", end_date="2026-12-31",
        )
        log("service.create(name='Lisinopril', dosage='10mg', "
            "frequency='1x daily', start_date='2026-01-01', end_date='2026-12-31')",
            med.to_dict())
        assert med.id is not None
        assert med.name == "Lisinopril"

        # --- Persist + restart-retrieve ----------------------------------
        section("STEP 2 — simulated app restart: reopen DB at same path, retrieve")
        restarted = MedicationService(Database(path))
        fetched = restarted.get(med.id)
        log(f"reopened.get(id={med.id})", fetched.to_dict())
        assert fetched is not None
        assert fetched.name == "Lisinopril"
        assert fetched.start_date == "2026-01-01"
        assert fetched.end_date == "2026-12-31"

        # --- Add a second med, list sorted + filtered --------------------
        section("STEP 3 — add second med; list sorted by most-recently-added + filter")
        med2 = service.create(name="Metformin", dosage="500mg", frequency="2x daily",
                              status="completed")
        all_meds = restarted.list()
        log("reopened.list()", [m.to_dict() for m in all_meds])
        log("reopened.list(status_filter='active')",
            [m.to_dict() for m in restarted.list(status_filter="active")])
        log("reopened.list(status_filter='completed')",
            [m.to_dict() for m in restarted.list(status_filter="completed")])
        assert [m.name for m in all_meds] == ["Metformin", "Lisinopril"]
        assert [m.name for m in restarted.list(status_filter="active")] == ["Lisinopril"]
        assert [m.name for m in restarted.list(status_filter="completed")] == ["Metformin"]

        # --- Edit persists across sessions -------------------------------
        section("STEP 4 — edit medication; verify change persists across restart")
        updated = service.update(med.id, dosage="20mg", frequency="2x daily")
        log("service.update(id, dosage='20mg', frequency='2x daily')", updated.to_dict())
        reopened_after_edit = MedicationService(Database(path))
        after = reopened_after_edit.get(med.id)
        log("reopened.get(id) after edit", after.to_dict())
        assert after.dosage == "20mg"
        assert after.frequency == "2x daily"

        # --- Mark-as-taken creates timestamped dose record ---------------
        section("STEP 5 — mark-as-taken creates timestamped dose record")
        when = datetime(2026, 4, 1, 7, 30, 0)
        record = service.mark_as_taken(med.id, when=when)
        log(f"service.mark_as_taken(id={med.id}, when={when.isoformat()})", record.to_dict())
        assert record.date == "2026-04-01"
        assert record.timestamp == when.isoformat()
        # idempotency: same day returns existing record, no duplicate
        again = service.mark_as_taken(med.id, when=datetime(2026, 4, 1, 21, 0, 0))
        log("service.mark_as_taken(same day) -> idempotent", again.to_dict())
        assert again.id == record.id
        history = service.dose_history(med.id)
        log("service.dose_history(id)", [h.to_dict() for h in history])
        assert len(history) == 1

        # --- Delete removes from list ------------------------------------
        section("STEP 6 — delete medication; verify removed from list")
        deleted = service.delete(med2.id)
        log(f"service.delete(id={med2.id})", deleted)
        after_delete = MedicationService(Database(path)).list()
        log("reopened.list() after delete", [m.to_dict() for m in after_delete])
        assert deleted is True
        assert [m.name for m in after_delete] == ["Lisinopril"]

        # --- Validation rejects incomplete entries -----------------------
        section("STEP 7 — validation rejects entries missing name/dosage/frequency")
        for bad in [
            ("name=None", dict(name=None, dosage="10mg", frequency="1x daily")),
            ("dosage=''", dict(name="X", dosage="", frequency="1x daily")),
            ("frequency=3 (non-string)", dict(name="X", dosage="10mg", frequency=3)),
            ("start_date > end_date",
             dict(name="X", dosage="10mg", frequency="1x daily",
                  start_date="2026-06-30", end_date="2026-01-01")),
        ]:
            try:
                service.create(**bad[1])
                log(f"service.create({bad[0]})", "ERROR: no exception raised")
                raise AssertionError(f"expected ValidationError for {bad[0]}")
            except ValidationError as exc:
                log(f"service.create({bad[0]}) -> ValidationError", str(exc))
                assert True

        # --- Edge case: past end date auto-completes on load -------------
        section("STEP 8 — edge case: past end_date auto-completed on load+reconcile")
        expired = service.create(
            name="ExpiredMeds", dosage="5mg", frequency="1x daily",
            start_date="2020-01-01", end_date="2020-06-01",
        )
        result = load_and_reconcile(Database(path), today="2026-10-01")
        log("load_and_reconcile(reopened_db, today='2026-10-01')", result)
        assert len(result["auto_completed"]) == 1
        assert result["auto_completed"][0]["name"] == "ExpiredMeds"
        assert result["removed"] == []

        # --- Edge case: corrupted record detected + recovered ------------
        section("STEP 9 — edge case: corrupted record detected & recovered")
        conn = db.connect()
        now = datetime.utcnow().isoformat()
        conn.execute(
            "INSERT INTO medications (name, dosage, frequency, status, created_at, updated_at) "
            "VALUES ('', '10mg', '1x daily', 'active', ?, ?)",
            (now, now),
        )
        conn.commit()
        conn.close()
        report = verify_persistence(Database(path))
        log("verify_persistence() with injected corruption", report)
        assert len(report["corrupted"]) == 1
        assert "name" in report["corrupted"][0]["problems"]

        # Write transcript
        ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        transcript_path = ARTIFACTS_DIR / "console-transcript.txt"
        transcript_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        assert transcript_path.exists()
        assert transcript_path.stat().st_size > 0