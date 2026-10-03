"""Functional gate test: prescription CRUD, lifecycle, immutability, and integrity.

Success criteria:
- Create prescription persists all fields and is retrievable by patient ID with
  correct dosage structure and references.
- Status transitions (active -> discontinued/completed) insert timestamped audit
  rows and reject invalid transitions.
- Discontinuation without a reason field is rejected with a validation error.
- Fetching patient prescription history returns all entries sorted by start_date
  descending including discontinued and completed.
- Concurrent active prescription for the same medicine and patient is rejected by
  the partial unique index.
- Validation rejects entries missing required fields or with end_date preceding
  start_date.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pytest

from prescription_tracker.db import init_db, seed_reference_data
from prescription_tracker.models import (
    PrescriptionCreate,
    StatusTransition,
    ValidationError,
)
from prescription_tracker.repository import NotFoundError, PrescriptionRepository

PATIENT = "patient-func"
DOCTOR = "doctor-func"


def _iso(dt: datetime) -> str:
    return dt.isoformat()


@pytest.fixture
def repo():
    conn = init_db()
    seed_reference_data(conn, PATIENT, DOCTOR)
    return PrescriptionRepository(conn)


def _make(medicine="Amoxicillin", start=None, end=None, patient=PATIENT) -> PrescriptionCreate:
    return PrescriptionCreate(
        patient_id=patient,
        doctor_id=DOCTOR,
        medicine_name=medicine,
        dosage_amount=250.0,
        dosage_unit="mg",
        frequency="2x/day",
        start_date=start or _iso(datetime(2026, 3, 1, tzinfo=timezone.utc)),
        end_date=end,
    )


class TestCreateAndRetrieve:
    def test_create_persists_all_fields(self, repo):
        rx = repo.create_prescription(_make(medicine="Ibuprofen"))
        fetched = repo.get_prescription(rx["id"])
        assert fetched["patient_id"] == PATIENT
        assert fetched["doctor_id"] == DOCTOR
        assert fetched["medicine_name"] == "Ibuprofen"
        assert fetched["dosage_amount"] == 250.0
        assert fetched["dosage_unit"] == "mg"
        assert fetched["frequency"] == "2x/day"
        assert fetched["status"] == "active"
        assert fetched["start_date"] == _iso(datetime(2026, 3, 1, tzinfo=timezone.utc))

    def test_retrieve_by_patient(self, repo):
        rx = repo.create_prescription(_make(medicine="Ciprofloxacin"))
        result = repo.list_by_patient(PATIENT)
        assert any(r["id"] == rx["id"] for r in result["active"])

    def test_get_nonexistent_raises(self, repo):
        with pytest.raises(NotFoundError):
            repo.get_prescription("does-not-exist")


class TestStatusTransitions:
    def test_complete_inserts_audit_row(self, repo):
        rx = repo.create_prescription(_make())
        completed = repo.complete(rx["id"])
        assert completed["status"] == "completed"
        transitions = repo.conn.execute(
            "SELECT * FROM status_transitions WHERE prescription_id = ?",
            (rx["id"],),
        ).fetchall()
        assert len(transitions) == 1
        assert transitions[0]["from_status"] == "active"
        assert transitions[0]["to_status"] == "completed"
        assert transitions[0]["transitioned_at"] is not None

    def test_discontinue_inserts_audit_row_with_reason(self, repo):
        rx = repo.create_prescription(_make())
        discontinued = repo.discontinue(rx["id"], "side effects")
        assert discontinued["status"] == "discontinued"
        row = repo.conn.execute(
            "SELECT * FROM status_transitions WHERE prescription_id = ?",
            (rx["id"],),
        ).fetchone()
        assert row["reason"] == "side effects"

    def test_discontinue_without_reason_rejected(self, repo):
        rx = repo.create_prescription(_make())
        with pytest.raises(ValidationError) as exc:
            repo.discontinue(rx["id"], "")
        assert "reason" in exc.value.errors
        # Status unchanged.
        assert repo.get_prescription(rx["id"])["status"] == "active"

    def test_invalid_transition_from_completed(self, repo):
        rx = repo.create_prescription(_make())
        repo.complete(rx["id"])
        with pytest.raises(ValidationError):
            repo.discontinue(rx["id"], "late reason")

    def test_transition_from_discontinued_rejected(self, repo):
        rx = repo.create_prescription(_make())
        repo.discontinue(rx["id"], "done")
        with pytest.raises(ValidationError):
            repo.complete(rx["id"])


class TestHistorySorting:
    def test_history_sorted_start_date_desc(self, repo):
        repo.create_prescription(
            _make(medicine="A", start=_iso(datetime(2026, 1, 1, tzinfo=timezone.utc)))
        )
        repo.create_prescription(
            _make(medicine="B", start=_iso(datetime(2026, 5, 1, tzinfo=timezone.utc)))
        )
        rx_c = repo.create_prescription(
            _make(medicine="C", start=_iso(datetime(2026, 3, 1, tzinfo=timezone.utc)))
        )
        repo.discontinue(rx_c["id"], "test")
        history = repo.list_history_by_patient(PATIENT)
        dates = [h["start_date"] for h in history]
        assert dates == sorted(dates, reverse=True)
        # Includes discontinued entries.
        assert any(h["medicine_name"] == "C" and h["status"] == "discontinued" for h in history)


class TestDuplicateActivePrevention:
    def test_concurrent_active_same_medicine_rejected(self, repo):
        repo.create_prescription(_make(medicine="Atorvastatin"))
        with pytest.raises(sqlite3.IntegrityError):
            repo.create_prescription(_make(medicine="Atorvastatin"))

    def test_historical_duplicate_allowed(self, repo):
        rx = repo.create_prescription(_make(medicine="Atorvastatin"))
        repo.complete(rx["id"])
        # A new active prescription for the same medicine is fine now.
        rx2 = repo.create_prescription(_make(medicine="Atorvastatin"))
        assert rx2["status"] == "active"


class TestValidationFailures:
    def test_missing_fields_rejected(self, repo):
        data = _make()
        data.medicine_name = ""
        with pytest.raises(ValidationError):
            repo.create_prescription(data)

    def test_end_before_start_rejected(self, repo):
        data = _make(
            start=_iso(datetime(2026, 6, 1, tzinfo=timezone.utc)),
            end=_iso(datetime(2026, 5, 1, tzinfo=timezone.utc)),
        )
        with pytest.raises(ValidationError):
            repo.create_prescription(data)


class TestForeignKeyEnforcement:
    def test_fk_violation_patient(self, repo):
        data = PrescriptionCreate(
            patient_id="nonexistent-patient",
            doctor_id=DOCTOR,
            medicine_name="Test",
            dosage_amount=100.0,
            dosage_unit="mg",
            frequency="1x/day",
            start_date=_iso(datetime(2026, 1, 1, tzinfo=timezone.utc)),
        )
        with pytest.raises(sqlite3.IntegrityError):
            repo.create_prescription(data)

    def test_fk_violation_doctor(self, repo):
        data = PrescriptionCreate(
            patient_id=PATIENT,
            doctor_id="nonexistent-doctor",
            medicine_name="Test",
            dosage_amount=100.0,
            dosage_unit="mg",
            frequency="1x/day",
            start_date=_iso(datetime(2026, 1, 1, tzinfo=timezone.utc)),
        )
        with pytest.raises(sqlite3.IntegrityError):
            repo.create_prescription(data)


# ---------------------------------------------------------------------------
# Evidence capture: records a console transcript of real HTTP requests and
# responses into .see/e2e-artifacts/console-transcript.txt. This test makes
# the same assertions as the rest of the suite — it fails when behaviour is
# broken — but additionally writes a readable transcript as a side effect.
# ---------------------------------------------------------------------------
class TestEvidenceCapture:
    def test_console_transcript_of_full_lifecycle(self, tmp_path, monkeypatch):
        import json
        from pathlib import Path

        from tests.asgi_client import ASGIClient

        from prescription_tracker.app import app
        from prescription_tracker.db import init_db
        from prescription_tracker.repository import PrescriptionRepository

        conn = init_db()
        monkeypatch.setattr("prescription_tracker.app._conn", conn)
        monkeypatch.setattr("prescription_tracker.app._repo", PrescriptionRepository(conn))
        client = ASGIClient(app)

        artifacts = Path(__file__).resolve().parents[2] / ".see" / "e2e-artifacts"
        artifacts.mkdir(parents=True, exist_ok=True)
        transcript = artifacts / "console-transcript.txt"

        lines: list[str] = []
        patient = "patient-evidence"
        base_ts = "2026-01-01T08:00:00+00:00"

        def _log(section: str, method: str, path: str, status: int, body: object) -> None:
            lines.append(f"--- {section} ---")
            lines.append(f"$ {method} {path}")
            lines.append(f"< HTTP {status}")
            payload = body if isinstance(body, str) else json.dumps(body, indent=2, sort_keys=True)
            lines.append(f"< {payload}")
            lines.append("")

        # 1. Create a prescription.
        r = client.post(
            f"/patients/{patient}/prescriptions",
            json={
                "doctor_id": DOCTOR,
                "medicine_name": "Amoxicillin",
                "dosage_amount": 500.0,
                "dosage_unit": "mg",
                "frequency": "3x/day",
                "start_date": base_ts,
            },
        )
        _log("CREATE prescription", "POST", f"/patients/{patient}/prescriptions",
             r.status_code, r.json())
        assert r.status_code == 200
        rx_id = r.json()["id"]

        # 2. Retrieve it by ID.
        r = client.get(f"/prescriptions/{rx_id}")
        _log("RETRIEVE by id", "GET", f"/prescriptions/{rx_id}",
             r.status_code, r.json())
        assert r.status_code == 200
        assert r.json()["medicine_name"] == "Amoxicillin"

        # 3. List by patient (active separated from historical).
        r = client.get(f"/patients/{patient}/prescriptions")
        _log("LIST by patient", "GET", f"/patients/{patient}/prescriptions",
             r.status_code, r.json())
        assert r.status_code == 200
        assert len(r.json()["active"]) == 1

        # 4. Add a dose log.
        r = client.post(
            f"/prescriptions/{rx_id}/dose-logs",
            json={"event": "taken", "timestamp": "2026-01-01T08:00:00+00:00"},
        )
        _log("DOSE LOG append", "POST", f"/prescriptions/{rx_id}/dose-logs",
             r.status_code, r.json())
        assert r.status_code == 200

        # 5. Discontinue with a reason.
        r = client.patch(
            f"/prescriptions/{rx_id}/discontinue",
            json={"reason": "course finished"},
        )
        _log("DISCONTINUE", "PATCH", f"/prescriptions/{rx_id}/discontinue",
             r.status_code, r.json())
        assert r.status_code == 200
        assert r.json()["status"] == "discontinued"

        # 6. Fetch history (includes discontinued).
        r = client.get(f"/patients/{patient}/prescriptions")
        _log("HISTORY after discontinue", "GET", f"/patients/{patient}/prescriptions",
             r.status_code, r.json())
        assert r.status_code == 200
        assert any(p["status"] == "discontinued" for p in r.json()["historical"])

        # 7. Duplicate active for same medicine is rejected.
        r = client.post(
            f"/patients/{patient}/prescriptions",
            json={
                "doctor_id": DOCTOR,
                "medicine_name": "Amoxicillin",
                "dosage_amount": 250.0,
                "dosage_unit": "mg",
                "frequency": "2x/day",
                "start_date": "2026-02-01T08:00:00+00:00",
            },
        )
        # The previous one is discontinued, so a new active one is allowed —
        # instead test the partial index by creating a second active directly.
        # Grab the new id then attempt a concurrent duplicate.
        assert r.status_code == 200
        rx2_id = r.json()["id"]
        r_dup = client.post(
            f"/patients/{patient}/prescriptions",
            json={
                "doctor_id": DOCTOR,
                "medicine_name": "Amoxicillin",
                "dosage_amount": 250.0,
                "dosage_unit": "mg",
                "frequency": "2x/day",
                "start_date": "2026-02-02T08:00:00+00:00",
            },
        )
        _log("DUPLICATE active rejected", "POST", f"/patients/{patient}/prescriptions",
             r_dup.status_code, r_dup.json())
        assert r_dup.status_code == 409  # IntegrityError surfaces as 409 Conflict

        # 8. Discontinue without a reason is rejected.
        r = client.patch(f"/prescriptions/{rx2_id}/discontinue", json={"reason": ""})
        _log("DISCONTINUE without reason rejected", "PATCH",
             f"/prescriptions/{rx2_id}/discontinue", r.status_code, r.json())
        assert r.status_code == 422

        transcript.write_text("\n".join(lines))