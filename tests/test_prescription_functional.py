"""Functional tests for the prescription tracker HTTP API.

These tests spin up the FastAPI app with TestClient against a per-test
temporary on-disk SQLite database (via MEDICATION_TRACKER_DB) so that
foreign-key enforcement, CHECK constraints and the partial unique index
all exercise the real schema. They cover the full create -> retrieve ->
discontinue -> history flow plus validation and the 500ms SLO.
"""

from __future__ import annotations

import json

import os

import time

import uuid

from pathlib import Path

from typing import Iterator, List

import pytest

from fastapi.testclient import TestClient

import sqlite3

from medication_tracker.errors import ValidationError

from medication_tracker.models import PrescriptionStatus

from medication_tracker.repository import PrescriptionRepository, init_schema

from medication_tracker.validators import validate_prescription

from datetime import datetime

from uuid import uuid4

import concurrent.futures

from prescription_tracker.models import Prescription, PrescriptionStatus

from prescription_tracker.service import ConflictError, PrescriptionService



REPO_ROOT = Path(__file__).resolve().parent.parent

ARTIFACTS_DIR = REPO_ROOT / ".see" / "e2e-artifacts"

TRANSCRIPT_PATH = ARTIFACTS_DIR / "console-transcript.txt"

@pytest.fixture(autouse=True)
def _ensure_artifacts_dir() -> Iterator[None]:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    yield

@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "functional.db"

@pytest.fixture(autouse=True)
def env(db_path: Path, monkeypatch) -> Iterator[None]:
    monkeypatch.setenv("MEDICATION_TRACKER_DB", str(db_path))
    yield

@pytest.fixture
def client(db_path: Path, monkeypatch, app) -> Iterator[TestClient]:
    # The FastAPI TestClient (and its httpx dependency) belongs to the HTTP
    # build unit; skip the HTTP tests when it is unavailable rather than
    # crashing collection. Repository-layer tests do not use this fixture.
    if TestClient is None:
        pytest.skip(f"FastAPI TestClient unavailable: {_TESTCLIENT_IMPORT_ERROR}")
    
    # Import after the env var has been set so the app picks up the per-test db.
    monkeypatch.setenv("MEDICATION_TRACKER_DB", str(db_path))
    
    # Use the provided app fixture if available, otherwise create it
    if app:
        with TestClient(app) as c:
            yield c
    else:
        from medication_tracker.app import create_app
        with TestClient(create_app()) as c:
            yield c

class Transcript:
    """Append-only record of HTTP exchanges for the console transcript."""

    def __init__(self) -> None:
        self._lines: List[str] = []

    def log(self, method: str, path: str, status: int, body) -> None:
        self._lines.append(f"$ {method} {path}")
        if body is not None:
            self._lines.append(f"  request body: {json.dumps(body)}")
        self._lines.append(f"  -> {status}")
        self._lines.append("")

    def write(self, path: Path) -> None:
        path.write_text("\n".join(self._lines) + "\n", encoding="utf-8")

def _valid_payload(doctor_id: str | None = None, **overrides):
    base = {
        "doctor_id": doctor_id or str(uuid.uuid4()),
        "doctor_name": "Dr. House",
        "medicine_name": "Amoxicillin",
        "dosage_amount": 500.0,
        "dosage_unit": "mg",
        "frequency": "3x daily",
        "start_date": "2026-01-01T00:00:00+00:00",
        "end_date": None,
    }
    base.update(overrides)
    return base

def test_create_and_retrieve_prescription(client):
    pid = str(uuid.uuid4())
    payload = _valid_payload()
    r = client.post(f"/patients/{pid}/prescriptions", json=payload)
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["patient_id"] == pid
    assert created["medicine_name"] == "Amoxicillin"
    assert created["dosage_amount"] == 500.0
    assert created["dosage_unit"] == "mg"
    assert created["frequency"] == "3x daily"
    assert created["status"] == "active"
    assert created["start_date"] == payload["start_date"]
    rx_id = created["id"]

    r2 = client.get(f"/prescriptions/{rx_id}")
    assert r2.status_code == 200
    fetched = r2.json()
    assert fetched["id"] == rx_id
    assert fetched["patient_id"] == pid
    assert fetched["status"] == "active"

def test_retrieve_unknown_prescription_returns_404(client):
    r = client.get(f"/prescriptions/{uuid.uuid4()}")
    assert r.status_code == 404

def test_missing_required_field_rejected(client):
    pid = str(uuid.uuid4())
    payload = _valid_payload()
    del payload["medicine_name"]
    r = client.post(f"/patients/{pid}/prescriptions", json=payload)
    assert r.status_code == 400, r.text
    # No row should have been persisted for this patient.
    r2 = client.get(f"/patients/{pid}/prescriptions")
    assert r2.json() == []

def test_end_date_before_start_date_rejected(client):
    pid = str(uuid.uuid4())
    payload = _valid_payload(
        start_date="2026-02-01T00:00:00+00:00",
        end_date="2026-01-01T00:00:00+00:00",
    )
    r = client.post(f"/patients/{pid}/prescriptions", json=payload)
    assert r.status_code == 400, r.text
    r2 = client.get(f"/patients/{pid}/prescriptions")
    assert r2.json() == []

def test_negative_dosage_rejected(client):
    pid = str(uuid.uuid4())
    payload = _valid_payload(dosage_amount=-10.0)
    r = client.post(f"/patients/{pid}/prescriptions", json=payload)
    assert r.status_code in (400, 422), r.text
    assert client.get(f"/patients/{pid}/prescriptions").json() == []

def test_naive_datetime_rejected(client):
    pid = str(uuid.uuid4())
    payload = _valid_payload(start_date="2026-01-01T00:00:00")  # no tz
    r = client.post(f"/patients/{pid}/prescriptions", json=payload)
    assert r.status_code == 400, r.text

def test_second_active_same_medicine_rejected(client):
    pid = str(uuid.uuid4())
    doctor = str(uuid.uuid4())
    r1 = client.post(
        f"/patients/{pid}/prescriptions", json=_valid_payload(doctor, medicine_name="Metformin")
    )
    assert r1.status_code == 201, r1.text
    r2 = client.post(
        f"/patients/{pid}/prescriptions",
        json=_valid_payload(doctor, medicine_name="Metformin",
                            start_date="2026-02-01T00:00:00+00:00"),
    )
    assert r2.status_code == 409, r2.text
    history = client.get(f"/patients/{pid}/prescriptions").json()
    assert len(history) == 1

def test_second_active_after_discontinuation_succeeds(client):
    pid = str(uuid.uuid4())
    doctor = str(uuid.uuid4())
    r1 = client.post(
        f"/patients/{pid}/prescriptions",
        json=_valid_payload(doctor, medicine_name="Metformin",
                            start_date="2026-01-01T00:00:00+00:00"),
    )
    assert r1.status_code == 201
    rx_id = r1.json()["id"]

    # Discontinue with a reason.
    r_disc = client.patch(
        f"/prescriptions/{rx_id}/discontinue", json={"reason": "Adverse reaction"}
    )
    assert r_disc.status_code == 200, r_disc.text
    assert r_disc.json()["status"] == "discontinued"
    assert r_disc.json()["discontinue_reason"] == "Adverse reaction"

    # Now a new active prescription for the same medicine is allowed.
    r2 = client.post(
        f"/patients/{pid}/prescriptions",
        json=_valid_payload(doctor, medicine_name="Metformin",
                            start_date="2026-03-01T00:00:00+00:00"),
    )
    assert r2.status_code == 201, r2.text
    history = client.get(f"/patients/{pid}/prescriptions").json()
    assert len(history) == 2
    # The discontinued row must still be present in history with its status
    # preserved (immutability — discontinuation is an audit transition, not a
    # deletion), and history stays sorted by start_date descending.
    by_id = {h["id"]: h for h in history}
    assert rx_id in by_id, "discontinued prescription must remain in history"
    assert by_id[rx_id]["status"] == "discontinued"
    assert by_id[rx_id]["discontinue_reason"] == "Adverse reaction"
    starts = [h["start_date"] for h in history]
    assert starts == sorted(starts, reverse=True), (
        f"history not sorted by start_date DESC after discontinue: {starts}"
    )

def test_discontinue_without_reason_rejected(client):
    pid = str(uuid.uuid4())
    doctor = str(uuid.uuid4())
    rx_id = client.post(
        f"/patients/{pid}/prescriptions", json=_valid_payload(doctor)
    ).json()["id"]

    # Empty reason body -> 400/422.
    r = client.patch(f"/prescriptions/{rx_id}/discontinue", json={"reason": ""})
    assert r.status_code in (400, 422), r.text

    # Missing reason key entirely.
    r2 = client.patch(f"/prescriptions/{rx_id}/discontinue", json={})
    assert r2.status_code in (400, 422), r2.text

    # Row must still be active and have no reason.
    fetched = client.get(f"/prescriptions/{rx_id}").json()
    assert fetched["status"] == "active"
    assert fetched["discontinue_reason"] is None

def test_discontinue_with_reason_preserves_history(client):
    pid = str(uuid.uuid4())
    doctor = str(uuid.uuid4())
    rx_id = client.post(
        f"/patients/{pid}/prescriptions", json=_valid_payload(doctor)
    ).json()["id"]
    created = client.get(f"/prescriptions/{rx_id}").json()
    original_updated_at = created["updated_at"]

    r = client.patch(
        f"/prescriptions/{rx_id}/discontinue", json={"reason": "Course finished early"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "discontinued"
    assert body["discontinue_reason"] == "Course finished early"
    # Timestamp advanced.
    assert body["updated_at"] >= original_updated_at
    # The row still exists (not deleted) and is retrievable by id.
    again = client.get(f"/prescriptions/{rx_id}").json()
    assert again["status"] == "discontinued"
    assert again["id"] == rx_id

def test_complete_prescription(client):
    pid = str(uuid.uuid4())
    doctor = str(uuid.uuid4())
    rx_id = client.post(
        f"/patients/{pid}/prescriptions", json=_valid_payload(doctor)
    ).json()["id"]
    r = client.patch(f"/prescriptions/{rx_id}/complete")
    assert r.status_code == 200
    assert r.json()["status"] == "completed"

def test_history_sorted_by_start_date_desc_with_all_statuses(client):
    pid = str(uuid.uuid4())
    doctor = str(uuid.uuid4())

    # Create three prescriptions with distinct start dates and statuses.
    r_old = client.post(
        f"/patients/{pid}/prescriptions",
        json=_valid_payload(doctor, medicine_name="MedA",
                            start_date="2025-01-01T00:00:00+00:00"),
    )
    assert r_old.status_code == 201
    client.patch(f"/prescriptions/{r_old.json()['id']}/complete")

    r_mid = client.post(
        f"/patients/{pid}/prescriptions",
        json=_valid_payload(doctor, medicine_name="MedB",
                            start_date="2025-06-01T00:00:00+00:00"),
    )
    assert r_mid.status_code == 201
    client.patch(
        f"/prescriptions/{r_mid.json()['id']}/discontinue",
        json={"reason": "switched therapy"},
    )

    r_new = client.post(
        f"/patients/{pid}/prescriptions",
        json=_valid_payload(doctor, medicine_name="MedC",
                            start_date="2026-01-01T00:00:00+00:00"),
    )
    assert r_new.status_code == 201  # active

    history = client.get(f"/patients/{pid}/prescriptions").json()
    assert len(history) == 3
    starts = [h["start_date"] for h in history]
    assert starts == sorted(starts, reverse=True)
    statuses = {h["status"] for h in history}
    assert statuses == {"active", "completed", "discontinued"}

@pytest.mark.parametrize(
    "method,path_builder",
    [
        ("GET", lambda pid: f"/patients/{pid}/prescriptions"),
    ],
)
def test_single_patient_endpoints_under_500ms(client, method, path_builder):
    pid = str(uuid.uuid4())
    doctor = str(uuid.uuid4())
    # Seed a handful of rows so the query isn't trivially empty.
    for i, med in enumerate(["M1", "M2", "M3"]):
        client.post(
            f"/patients/{pid}/prescriptions",
            json=_valid_payload(doctor, medicine_name=med,
                                start_date=f"2026-0{i+1}-01T00:00:00+00:00"),
        )
    path = path_builder(pid)
    start = time.perf_counter()
    r = client.request(method, path)
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert r.status_code == 200, r.text
    assert elapsed_ms < 500, f"{method} {path} took {elapsed_ms:.1f}ms"

def test_evidence_transcript(client):
    t = Transcript()
    pid = str(uuid.uuid4())
    doctor = str(uuid.uuid4())

    # 1. Create a valid prescription.
    payload = _valid_payload(doctor, medicine_name="Amoxicillin",
                             start_date="2026-01-01T00:00:00+00:00")
    r = client.post(f"/patients/{pid}/prescriptions", json=payload)
    t.log("POST", f"/patients/{pid}/prescriptions", r.status_code, payload)
    assert r.status_code == 201, r.text
    created = r.json()
    rx_id = created["id"]
    assert created["status"] == "active"
    assert created["patient_id"] == pid

    # 2. Retrieve it by id.
    r = client.get(f"/prescriptions/{rx_id}")
    t.log("GET", f"/prescriptions/{rx_id}", r.status_code, None)
    assert r.status_code == 200
    assert r.json()["id"] == rx_id

    # 3. Validation rejection: missing required field -> 400, nothing persisted.
    bad = _valid_payload(doctor, medicine_name="Ibuprofen")
    del bad["dosage_unit"]
    r = client.post(f"/patients/{pid}/prescriptions", json=bad)
    t.log("POST", f"/patients/{pid}/prescriptions (missing dosage_unit)",
          r.status_code, bad)
    assert r.status_code == 400, r.text
    assert client.get(f"/patients/{pid}/prescriptions").json() == [created] or len(
        client.get(f"/patients/{pid}/prescriptions").json()
    ) == 1

    # 4. Validation rejection: end_date before start_date -> 400.
    bad_dates = _valid_payload(doctor, medicine_name="Naproxen",
                               start_date="2026-02-01T00:00:00+00:00",
                               end_date="2026-01-01T00:00:00+00:00")
    r = client.post(f"/patients/{pid}/prescriptions", json=bad_dates)
    t.log("POST", f"/patients/{pid}/prescriptions (end<start)",
          r.status_code, bad_dates)
    assert r.status_code == 400, r.text

    # 5. One active prescription per medicine: a second active Amoxicillin -> 409.
    dup = _valid_payload(doctor, medicine_name="Amoxicillin",
                         start_date="2026-03-01T00:00:00+00:00")
    r = client.post(f"/patients/{pid}/prescriptions", json=dup)
    t.log("POST", f"/patients/{pid}/prescriptions (duplicate active)",
          r.status_code, dup)
    assert r.status_code == 409, r.text

    # 6. Discontinue without a reason -> 400/422, row stays active.
    r = client.patch(f"/prescriptions/{rx_id}/discontinue", json={"reason": ""})
    t.log("PATCH", f"/prescriptions/{rx_id}/discontinue (empty reason)",
          r.status_code, {"reason": ""})
    assert r.status_code in (400, 422), r.text
    assert client.get(f"/prescriptions/{rx_id}").json()["status"] == "active"

    # 7. Discontinue WITH a reason -> 200, status + timestamp advance, history preserved.
    before = client.get(f"/prescriptions/{rx_id}").json()
    r = client.patch(f"/prescriptions/{rx_id}/discontinue",
                     json={"reason": "Adverse reaction"})
    t.log("PATCH", f"/prescriptions/{rx_id}/discontinue",
          r.status_code, {"reason": "Adverse reaction"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "discontinued"
    assert body["discontinue_reason"] == "Adverse reaction"
    assert body["updated_at"] >= before["updated_at"]
    # Row is not deleted — still retrievable by id.
    again = client.get(f"/prescriptions/{rx_id}")
    t.log("GET", f"/prescriptions/{rx_id} (after discontinue)",
          again.status_code, None)
    assert again.status_code == 200
    assert again.json()["status"] == "discontinued"

    # 8. Re-prescribe the same medicine after discontinuation -> 201 (allowed).
    r2 = client.post(
        f"/patients/{pid}/prescriptions",
        json=_valid_payload(doctor, medicine_name="Amoxicillin",
                            start_date="2026-04-01T00:00:00+00:00"),
    )
    t.log("POST", f"/patients/{pid}/prescriptions (re-prescribe after discontinue)",
          r2.status_code, _valid_payload(doctor, medicine_name="Amoxicillin",
                                         start_date="2026-04-01T00:00:00+00:00"))
    assert r2.status_code == 201, r2.text
    rx2_id = r2.json()["id"]

    # 9. Complete the new active prescription -> 200.
    r = client.patch(f"/prescriptions/{rx2_id}/complete")
    t.log("PATCH", f"/prescriptions/{rx2_id}/complete", r.status_code, None)
    assert r.status_code == 200
    assert r.json()["status"] == "completed"

    # 10. History sorted by start_date DESC with all three statuses present.
    r = client.get(f"/patients/{pid}/prescriptions")
    t.log("GET", f"/patients/{pid}/prescriptions (history)", r.status_code, None)
    assert r.status_code == 200
    history = r.json()
    assert len(history) == 2
    starts = [h["start_date"] for h in history]
    assert starts == sorted(starts, reverse=True)
    statuses = {h["status"] for h in history}
    assert statuses == {"discontinued", "completed"}

    # 11. 500ms SLO on the history read.
    start = time.perf_counter()
    r = client.get(f"/patients/{pid}/prescriptions")
    elapsed_ms = (time.perf_counter() - start) * 1000
    t.log("GET", f"/patients/{pid}/prescriptions (SLO timing)", r.status_code, None)
    assert r.status_code == 200
    assert elapsed_ms < 500, f"history took {elapsed_ms:.1f}ms"

    t.write(TRANSCRIPT_PATH)
    assert TRANSCRIPT_PATH.exists() and TRANSCRIPT_PATH.stat().st_size > 0

def test_persists_across_requests_without_env_var(tmp_path, monkeypatch):
    monkeypatch.delenv("MEDICATION_TRACKER_DB", raising=False)
    # Redirect the package's default on-disk location into tmp_path so the
    # test does not write a real db file into the installed package dir.
    # Patch on the app module because app.py imports `database_file` by name,
    # so monkeypatching medication_tracker.db.database_file would not reach it.
    import medication_tracker.app as appmod

    monkeypatch.setattr(
        appmod, "database_file", lambda: tmp_path / "default.db"
    )

    from medication_tracker.app import create_app

    with TestClient(create_app()) as c:
        pid = str(uuid.uuid4())
        doctor = str(uuid.uuid4())
        r = c.post(
            f"/patients/{pid}/prescriptions",
            json=_valid_payload(doctor, medicine_name="Amoxicillin"),
        )
        assert r.status_code == 201, r.text
        rx_id = r.json()["id"]

        # A *separate* request must see the row created above. This is the
        # assertion that fails when each request gets its own :memory: db.
        r2 = c.get(f"/prescriptions/{rx_id}")
        assert r2.status_code == 200, r2.text
        assert r2.json()["id"] == rx_id

        history = c.get(f"/patients/{pid}/prescriptions").json()
        assert len(history) == 1
        assert history[0]["id"] == rx_id

_TESTCLIENT_IMPORT_ERROR: Exception | None = None

try:  # pragma: no cover - exercised only in environments with httpx
    from fastapi.testclient import TestClient  # type: ignore[import-not-found]
except Exception as exc:  # pragma: no cover
    _TESTCLIENT_IMPORT_ERROR = exc
    TestClient = None  # type: ignore[assignment,misc]

REPOSITORY_TRANSCRIPT_PATH = ARTIFACTS_DIR / "repository-transcript.txt"

PATIENT_ID = "11111111-1111-1111-1111-111111111111"

DOCTOR_ID = "22222222-2222-2222-2222-222222222222"

@pytest.fixture(scope="session", autouse=True)
def _transcript_recorder():
    """Open a readable transcript of the real repository operations exercised here.

    Each test appends labelled lines (operation + outcome) to
    ``.see/e2e-artifacts/repository-transcript.txt`` so the milestone's
    behaviour is captured as a human-readable console transcript, not just
    pass/fail. A separate file from the HTTP transcript so both records
    survive the gate run.
    """
    os.makedirs(_ARTIFACTS_STR, exist_ok=True)
    with open(_REPOSITORY_TRANSCRIPT_STR, "w") as fh:
        fh.write("Prescription tracker — repository functional gate console transcript\n")
        fh.write("=" * 60 + "\n\n")
    yield

_ARTIFACTS_STR = os.path.join(os.path.dirname(__file__), "..", ".see", "e2e-artifacts")

_REPOSITORY_TRANSCRIPT_STR = os.path.join(_ARTIFACTS_STR, "repository-transcript.txt")

def _log(line: str) -> None:
    """Append one section line to the repository console transcript artifact."""
    with open(_REPOSITORY_TRANSCRIPT_STR, "a") as fh:
        fh.write(line.rstrip("\n") + "\n")

@pytest.fixture
def repo():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON;")
    init_schema(conn)
    r = PrescriptionRepository(conn)
    r.add_patient(PATIENT_ID)
    r.add_doctor(DOCTOR_ID)
    return r

def rx_data(**overrides):
    base = {
        "patient_id": PATIENT_ID,
        "doctor_id": DOCTOR_ID,
        "medicine_name": "Amoxicillin",
        "dosage_amount": 500,
        "dosage_unit": "mg",
        "frequency": "twice daily",
        "start_date": "2026-01-01T08:00:00+00:00",
    }
    base.update(overrides)
    return base

def _create(repo, **overrides):
    rx = validate_prescription(rx_data(**overrides))
    return repo.create(rx)

class TestEndToEndLifecycle:
    def test_create_retrieve_transition_deactivate_without_data_loss(self, repo):
        rx = _create(repo)
        fetched = repo.get_by_id(rx.id)
        _log(f"[create] POST prescription -> id={rx.id} medicine={rx.medicine_name} "
             f"dosage={rx.dosage_amount}{rx.dosage_unit} status={rx.status.value}")
        _log(f"[retrieve] GET by id -> medicine={fetched.medicine_name} "
             f"dosage={fetched.dosage_amount}{fetched.dosage_unit} status={fetched.status.value}")
        assert fetched.medicine_name == "Amoxicillin"
        assert fetched.dosage_amount == 500.0
        assert fetched.dosage_unit == "mg"
        assert fetched.status == PrescriptionStatus.ACTIVE

        # Transition active -> completed.
        completed = repo.complete(rx.id)
        _log(f"[transition] complete({rx.id}) -> status={completed.status.value} "
             f"medicine={completed.medicine_name} (no data loss)")
        assert completed.status == PrescriptionStatus.COMPLETED
        assert completed.medicine_name == "Amoxicillin"
        assert completed.dosage_amount == 500.0  # no data loss

        # Create a second active prescription then deactivate (discontinue) it.
        rx2 = _create(repo, medicine_name="Metformin", start_date="2026-02-01T08:00:00+00:00")
        discontinued = repo.discontinue(rx2.id, "patient switched therapy")
        _log(f"[transition] discontinue({rx2.id}, reason='patient switched therapy') "
             f"-> status={discontinued.status.value} medicine={discontinued.medicine_name}")
        assert discontinued.status == PrescriptionStatus.DISCONTINUED
        # Original fields preserved after discontinue.
        assert discontinued.medicine_name == "Metformin"
        assert discontinued.patient_id == PATIENT_ID

class TestDoseAdherence:
    def test_dose_events_recorded_with_timestamps(self, repo):
        rx = _create(repo)
        repo.log_dose(rx.id, "taken", "2026-01-01T08:00:00+00:00")
        repo.log_dose(rx.id, "skipped", "2026-01-01T20:00:00+00:00")
        history = repo.list_dose_logs(rx.id)
        _log(f"[dose-log] log_dose taken@08:00, skipped@20:00 -> {len(history)} events")
        for h in history:
            _log(f"  - {h['event']} @ {h['logged_at']}")
        assert len(history) == 2
        assert history[0]["event"] == "taken"
        assert history[1]["event"] == "skipped"
        # Sorted by logged_at ascending.
        assert history[0]["logged_at"] <= history[1]["logged_at"]

    def test_dose_log_rejects_unknown_event(self, repo):
        rx = _create(repo)
        with pytest.raises(ValueError):
            repo.log_dose(rx.id, "maybe", "2026-01-01T08:00:00+00:00")
        _log("[dose-log] log_dose(event='maybe') -> rejected ValueError (unknown event)")

    def test_dose_log_rejects_discontinued_prescription(self, repo):
        rx = _create(repo)
        repo.discontinue(rx.id, "adverse reaction")
        with pytest.raises(ValueError):
            repo.log_dose(rx.id, "taken", "2026-01-02T08:00:00+00:00")
        _log("[dose-log] log_dose against discontinued prescription -> rejected ValueError")

class TestBoundaryValidation:
    def test_rejects_incomplete_prescription(self, repo):
        with pytest.raises(ValidationError):
            repo.create_prescription(rx_data(medicine_name=None))
        _log("[validation] create_prescription(missing medicine_name) -> rejected ValidationError")

    def test_rejects_malformed_datetime(self, repo):
        with pytest.raises(ValidationError):
            repo.create_prescription(rx_data(start_date="not-a-date"))
        _log("[validation] create_prescription(start_date='not-a-date') -> rejected ValidationError")

    def test_rejects_end_before_start(self, repo):
        with pytest.raises(ValidationError):
            repo.create_prescription(
                rx_data(
                    start_date="2026-02-01T08:00:00+00:00",
                    end_date="2026-01-01T08:00:00+00:00",
                )
            )
        _log("[validation] create_prescription(end_date < start_date) -> rejected ValidationError")

    def test_rejects_naive_datetime(self, repo):
        with pytest.raises(ValidationError):
            repo.create_prescription(rx_data(start_date="2026-01-01T08:00:00"))
        _log("[validation] create_prescription(naive datetime, no tz) -> rejected ValidationError")

class TestDiscontinuePreservesHistory:
    def test_discontinue_requires_reason_and_preserves_record(self, repo):
        rx = _create(repo)
        with pytest.raises(ValueError):
            repo.discontinue(rx.id, "")
        _log("[discontinue] discontinue(reason='') -> rejected ValueError (reason required)")
        discontinued = repo.discontinue(rx.id, "side effects")
        assert discontinued.status == PrescriptionStatus.DISCONTINUED

        transitions = repo.list_transitions(rx.id)
        assert len(transitions) == 1
        assert transitions[0]["reason"] == "side effects"
        assert "T" in transitions[0]["transitioned_at"]
        _log(f"[discontinue] discontinue(reason='side effects') -> status={discontinued.status.value}, "
             f"transition recorded @ {transitions[0]['transitioned_at']}")

        # Historical record still present and intact.
        fetched = repo.get_by_id(rx.id)
        assert fetched is not None
        assert fetched.medicine_name == "Amoxicillin"
        _log(f"[discontinue] historical record preserved: medicine={fetched.medicine_name} "
             f"status={fetched.status.value}")

class TestConcurrentActiveUniqueness:
    def test_two_concurrent_active_rejected(self, repo):
        _create(repo, start_date="2026-01-01T08:00:00+00:00")
        with pytest.raises(sqlite3.IntegrityError):
            _create(repo, start_date="2026-01-05T08:00:00+00:00")
        _log("[uniqueness] second concurrent active Amoxicillin -> rejected sqlite3.IntegrityError")

    def test_completed_then_represcribed_allowed(self, repo):
        first = _create(repo, start_date="2025-01-01T08:00:00+00:00")
        repo.complete(first.id)
        second = _create(repo, start_date="2026-01-01T08:00:00+00:00")
        assert repo.get_by_id(second.id) is not None
        _log(f"[uniqueness] after completing first, re-prescribe allowed -> new id={second.id}")

class TestHistoryCompleteness:
    def test_history_includes_all_statuses_sorted_desc(self, repo):
        oldest = _create(repo, medicine_name="DrugA", start_date="2024-01-01T08:00:00+00:00")
        repo.complete(oldest.id)

        middle = _create(repo, medicine_name="DrugB", start_date="2025-01-01T08:00:00+00:00")
        repo.discontinue(middle.id, "ineffective")

        newest = _create(repo, medicine_name="DrugC", start_date="2026-01-01T08:00:00+00:00")

        history = repo.list_by_patient(PATIENT_ID)
        statuses = {h.status for h in history}
        assert PrescriptionStatus.COMPLETED in statuses
        assert PrescriptionStatus.DISCONTINUED in statuses
        assert PrescriptionStatus.ACTIVE in statuses
        assert len(history) == 3
        # Sorted by start_date descending.
        dates = [h.start_date for h in history]
        assert dates == sorted(dates, reverse=True)
        assert history[0].medicine_name == "DrugC"
        _log(f"[history] list_by_patient -> {len(history)} entries sorted by start_date DESC:")
        for h in history:
            _log(f"  - {h.medicine_name} start={h.start_date} status={h.status.value}")

class TestPerformance:
    def test_single_patient_operations_under_500ms(self, repo):
        start = time.perf_counter()
        rx = _create(repo, medicine_name="PerfDrug")
        repo.get_by_id(rx.id)
        repo.list_by_patient(PATIENT_ID)
        repo.complete(rx.id)
        repo.list_dose_logs(rx.id)
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 500, f"operations took {elapsed_ms:.1f}ms"
        _log(f"[perf] create+get+list+complete+list_dose_logs -> {elapsed_ms:.2f}ms (< 500ms)")

def test_http_persists_across_requests_without_env_var(tmp_path, monkeypatch):
    if TestClient is None:
        pytest.skip(f"FastAPI TestClient unavailable: {_TESTCLIENT_IMPORT_ERROR}")
    monkeypatch.delenv("MEDICATION_TRACKER_DB", raising=False)
    # Redirect the package's default on-disk location into tmp_path so the
    # test does not write a real db file into the installed package dir.
    # Patch on the app module because app.py imports `database_file` by name.
    import medication_tracker.app as appmod

    monkeypatch.setattr(appmod, "database_file", lambda: tmp_path / "default.db")

    from medication_tracker.app import create_app

    with TestClient(create_app()) as c:
        pid = str(uuid.uuid4())
        r = c.post(
            f"/patients/{pid}/prescriptions",
            json=_valid_payload(medicine_name="Amoxicillin"),
        )
        assert r.status_code == 201, r.text
        rx_id = r.json()["id"]

        # A *separate* request must see the row created above. This is the
        # assertion that fails (404 / empty history) when each request gets
        # its own :memory: db.
        r2 = c.get(f"/prescriptions/{rx_id}")
        assert r2.status_code == 200, r2.text
        assert r2.json()["id"] == rx_id

        history = c.get(f"/patients/{pid}/prescriptions").json()
        assert len(history) == 1
        assert history[0]["id"] == rx_id

@pytest.fixture
def app(tmp_path):
    from prescription_tracker.api import create_app

    db_path = str(tmp_path / "test.db")
    application = create_app(db_path=db_path)
    return application

@pytest.fixture
def api_service(app):
    """Reach the service wired into the Flask app for cross-checking."""
    # The service is created inside create_app; re-create on the same in-memory
    # DB is not possible, so expose via the app's service by constructing one
    # that shares the app's database connection through the test client only.
    # For direct data-layer assertions we use the standalone service fixture.
    from prescription_tracker.database import Database
    from prescription_tracker.service import PrescriptionService

    db = Database(":memory:")
    db.init_schema()
    service = PrescriptionService(db)
    service._database = db
    return service

def _payload(patient_id, doctor_id, **overrides):
    base = {
        "patient_id": str(patient_id),
        "doctor_id": str(doctor_id),
        "medicine_name": "Amoxicillin",
        "dosage_amount": "500",
        "dosage_unit": "mg",
        "frequency": "three times daily",
        "start_date": "2026-01-01T08:00:00+00:00",
    }
    base.update(overrides)
    return base

class TestCreateAndRetrieve:
    def test_create_with_all_required_fields_persists_and_is_retrievable(self, service, patient_id, doctor_id):
        rx = Prescription(
            patient_id=patient_id,
            doctor_id=doctor_id,
            medicine_name="Amoxicillin",
            dosage_amount="500",
            dosage_unit="mg",
            frequency="three times daily",
            start_date="2026-01-01T08:00:00+00:00",
        )
        created = service.create_prescription(rx)
        assert created.id is not None

        fetched = service.get_prescription(created.id)
        assert fetched is not None
        assert fetched.patient_id == patient_id
        assert fetched.doctor_id == doctor_id
        assert fetched.medicine_name == "Amoxicillin"
        assert fetched.dosage_amount == "500"
        assert fetched.dosage_unit == "mg"
        assert fetched.frequency == "three times daily"
        assert fetched.status == PrescriptionStatus.ACTIVE

    def test_create_via_api_with_numeric_dosage_returns_201(self, client, patient_id, doctor_id):
        payload = _payload(patient_id, doctor_id, dosage_amount=500)
        response = client.post("/prescriptions", json=payload)
        assert response.status_code == 201
        assert response.get_json()["dosage_amount"] == "500"

    def test_get_missing_prescription_returns_404(self, client):
        response = client.get(f"/prescriptions/{uuid4()}")
        assert response.status_code == 404

class TestValidationRejections:
    @pytest.mark.parametrize("missing_field", [
        "patient_id",
        "doctor_id",
        "medicine_name",
        "dosage_amount",
        "dosage_unit",
        "frequency",
        "start_date",
    ])
    def test_missing_required_field_rejected(self, client, patient_id, doctor_id, missing_field):
        payload = _payload(patient_id, doctor_id)
        del payload[missing_field]
        response = client.post("/prescriptions", json=payload)
        assert response.status_code == 400

    def test_end_date_preceding_start_date_rejected(self, client, patient_id, doctor_id):
        payload = _payload(
            patient_id,
            doctor_id,
            end_date="2025-12-31T08:00:00+00:00",
        )
        response = client.post("/prescriptions", json=payload)
        assert response.status_code == 400
        assert "end_date" in response.get_json()["error"]

    def test_empty_medicine_name_rejected(self, client, patient_id, doctor_id):
        payload = _payload(patient_id, doctor_id, medicine_name="   ")
        response = client.post("/prescriptions", json=payload)
        assert response.status_code == 400

    def test_naive_start_date_rejected(self, client, patient_id, doctor_id):
        payload = _payload(patient_id, doctor_id, start_date="2026-01-01T08:00:00")
        response = client.post("/prescriptions", json=payload)
        assert response.status_code == 400

class TestHistorySortingAndPartitioning:
    def test_history_sorted_start_date_desc_with_active_separated(self, service, patient_id, doctor_id):
        older = Prescription(
            patient_id=patient_id, doctor_id=doctor_id, medicine_name="MedA",
            dosage_amount="100", dosage_unit="mg", frequency="daily",
            start_date="2026-01-01T08:00:00+00:00",
        )
        newer = Prescription(
            patient_id=patient_id, doctor_id=doctor_id, medicine_name="MedB",
            dosage_amount="200", dosage_unit="mg", frequency="daily",
            start_date="2026-06-01T08:00:00+00:00",
        )
        middle = Prescription(
            patient_id=patient_id, doctor_id=doctor_id, medicine_name="MedC",
            dosage_amount="300", dosage_unit="mg", frequency="daily",
            start_date="2026-03-01T08:00:00+00:00",
        )

        service.create_prescription(older)
        service.create_prescription(newer)
        created_middle = service.create_prescription(middle)
        service.complete_prescription(created_middle.id)

        history = service.get_patient_history(patient_id)
        active = history["active"]
        historical = history["historical"]

        # Active partition holds the two still-active prescriptions, sorted DESC.
        active_starts = [datetime.fromisoformat(rx.start_date.isoformat()) for rx in active]
        assert active_starts == sorted(active_starts, reverse=True)
        assert all(rx.status == PrescriptionStatus.ACTIVE for rx in active)
        assert len(active) == 2

        # Historical partition holds the completed entry.
        assert len(historical) == 1
        assert historical[0].status == PrescriptionStatus.COMPLETED

    def test_history_includes_discontinued_and_completed(self, service, patient_id, doctor_id):
        rx1 = service.create_prescription(Prescription(
            patient_id=patient_id, doctor_id=doctor_id, medicine_name="MedA",
            dosage_amount="100", dosage_unit="mg", frequency="daily",
            start_date="2026-01-01T08:00:00+00:00",
        ))
        rx2 = service.create_prescription(Prescription(
            patient_id=patient_id, doctor_id=doctor_id, medicine_name="MedB",
            dosage_amount="200", dosage_unit="mg", frequency="daily",
            start_date="2026-02-01T08:00:00+00:00",
        ))

        service.discontinue_prescription(rx1.id, reason="Side effects")
        service.complete_prescription(rx2.id)

        history = service.get_patient_history(patient_id)
        statuses = {rx.status for rx in history["historical"]}
        assert PrescriptionStatus.DISCONTINUED in statuses
        assert PrescriptionStatus.COMPLETED in statuses
        # Both historical entries are present; assert the historical partition
        # is sorted by start_date descending (the README contract), not just
        # that both statuses appear. This is the assertion that guards the
        # sort order across a mixed-status historical set.
        hist_starts = [datetime.fromisoformat(rx.start_date.isoformat()) for rx in history["historical"]]
        assert len(hist_starts) == 2
        assert hist_starts == sorted(hist_starts, reverse=True), (
            f"historical partition not sorted by start_date DESC: {hist_starts}"
        )

    def test_history_via_api_partitions_active_and_historical(self, client, patient_id, doctor_id):
        first = client.post("/prescriptions", json=_payload(patient_id, doctor_id, medicine_name="MedA",
                                                              start_date="2026-01-01T08:00:00+00:00"))
        second = client.post("/prescriptions", json=_payload(patient_id, doctor_id, medicine_name="MedB",
                                                              start_date="2026-06-01T08:00:00+00:00"))
        client.patch(f"/prescriptions/{first.get_json()['id']}/complete")

        response = client.get(f"/patients/{patient_id}/prescriptions")
        assert response.status_code == 200
        body = response.get_json()
        assert len(body["active"]) == 1
        assert len(body["historical"]) == 1
        assert body["historical"][0]["status"] == "completed"

class TestDiscontinueReasonAndImmutability:
    def test_discontinue_without_reason_returns_400(self, client, patient_id, doctor_id):
        created = client.post("/prescriptions", json=_payload(patient_id, doctor_id))
        rx_id = created.get_json()["id"]

        response = client.patch(f"/prescriptions/{rx_id}/discontinue", json={})
        assert response.status_code == 400
        assert "reason" in response.get_json()["error"]

    def test_discontinue_with_reason_succeeds_and_records_reason(self, client, patient_id, doctor_id):
        created = client.post("/prescriptions", json=_payload(patient_id, doctor_id))
        rx_id = created.get_json()["id"]

        response = client.patch(
            f"/prescriptions/{rx_id}/discontinue",
            json={"reason": "Patient experienced nausea"},
        )
        assert response.status_code == 200
        body = response.get_json()
        assert body["status"] == "discontinued"

    def test_discontinue_prevents_deletion_of_historical_record(self, service, patient_id, doctor_id):
        rx = service.create_prescription(Prescription(
            patient_id=patient_id, doctor_id=doctor_id, medicine_name="MedA",
            dosage_amount="100", dosage_unit="mg", frequency="daily",
            start_date="2026-01-01T08:00:00+00:00",
        ))
        service.discontinue_prescription(rx.id, reason="No longer needed")

        # The row must still exist (immutability: no deletion permitted).
        fetched = service.get_prescription(rx.id)
        assert fetched is not None
        assert fetched.status == PrescriptionStatus.DISCONTINUED

    def test_no_put_or_delete_endpoints_on_prescriptions(self, client, patient_id, doctor_id):
        """Immutability: PUT and DELETE must not be supported on prescriptions."""
        created = client.post("/prescriptions", json=_payload(patient_id, doctor_id))
        rx_id = created.get_json()["id"]

        put_resp = client.put(f"/prescriptions/{rx_id}", json={"medicine_name": "Changed"})
        assert put_resp.status_code == 405

        delete_resp = client.delete(f"/prescriptions/{rx_id}")
        assert delete_resp.status_code == 405

    def test_only_post_allowed_on_prescriptions_collection(self, client):
        """Only POST is allowed on /prescriptions; GET, PUT, DELETE must return 405."""
        for method in ["get", "put", "delete"]:
            resp = getattr(client, method)("/prescriptions")
            assert resp.status_code == 405, f"{method.upper()} should be rejected with 405 on /prescriptions"

class TestOneActivePerMedicine:
    def test_duplicate_active_for_same_patient_medicine_rejected(self, service, patient_id, doctor_id):
        first = Prescription(
            patient_id=patient_id, doctor_id=doctor_id, medicine_name="Amoxicillin",
            dosage_amount="500", dosage_unit="mg", frequency="daily",
            start_date="2026-01-01T08:00:00+00:00",
        )
        service.create_prescription(first)

        second = Prescription(
            patient_id=patient_id, doctor_id=doctor_id, medicine_name="Amoxicillin",
            dosage_amount="250", dosage_unit="mg", frequency="daily",
            start_date="2026-02-01T08:00:00+00:00",
        )
        with pytest.raises(ConflictError):
            service.create_prescription(second)

    def test_duplicate_active_via_api_returns_409(self, client, patient_id, doctor_id):
        first = client.post("/prescriptions", json=_payload(patient_id, doctor_id, medicine_name="Amoxicillin"))
        assert first.status_code == 201

        second = client.post("/prescriptions", json=_payload(patient_id, doctor_id, medicine_name="Amoxicillin",
                                                              start_date="2026-06-01T08:00:00+00:00"))
        assert second.status_code == 409

    def test_allows_second_active_after_first_completed(self, service, patient_id, doctor_id):
        first = service.create_prescription(Prescription(
            patient_id=patient_id, doctor_id=doctor_id, medicine_name="Amoxicillin",
            dosage_amount="500", dosage_unit="mg", frequency="daily",
            start_date="2026-01-01T08:00:00+00:00",
        ))
        service.complete_prescription(first.id)

        second = service.create_prescription(Prescription(
            patient_id=patient_id, doctor_id=doctor_id, medicine_name="Amoxicillin",
            dosage_amount="250", dosage_unit="mg", frequency="daily",
            start_date="2026-06-01T08:00:00+00:00",
        ))
        assert second.status == PrescriptionStatus.ACTIVE

    def test_partial_unique_index_exists(self, database):
        cursor = database.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_one_active_per_medicine'"
        )
        row = cursor.fetchone()
        assert row is not None, "partial unique index idx_one_active_per_medicine must exist"

    def test_concurrent_creations_do_not_raise_threading_errors(self, service, patient_id, doctor_id):
        """Ensure that creating prescriptions across multiple threads does not raise SQLite threading errors."""
        def create_rx(i):
            rx = Prescription(
                patient_id=patient_id, doctor_id=doctor_id,
                medicine_name=f"Med{i}", dosage_amount="100",
                dosage_unit="mg", frequency="daily",
                start_date="2026-01-01T08:00:00+00:00",
            )
            return service.create_prescription(rx)

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            results = list(executor.map(create_rx, range(10)))

        assert len(results) == 10
        assert all(rx.status == PrescriptionStatus.ACTIVE for rx in results)

class TestEvidenceTranscript:
    """Drive the full milestone lifecycle through the real Flask test client
    and capture a readable console transcript of every request/response into
    .see/e2e-artifacts/console-transcript.txt.

    The assertions here are genuine lifecycle checks — the test still fails if
    any gate-relevant behaviour breaks. The transcript is a side effect.
    """

    @pytest.fixture(autouse=True)
    def _transcript_writer(self):
        lines: list = []
        self._lines = lines
        yield lines
        artifact_dir = Path(os.environ.get("EVIDENCE_DIR", ".see/e2e-artifacts"))
        artifact_dir.mkdir(parents=True, exist_ok=True)
        (artifact_dir / "console-transcript.txt").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )

    def _record(self, client, method, path, json_body=None, label=""):
        """Issue a request, append a transcript block, return the response."""
        self._lines.append("")
        if label:
            self._lines.append(f"# --- {label} ---")
        self._lines.append(f"> {method.upper()} {path}")
        if json_body is not None:
            self._lines.append(f"> body: {json.dumps(json_body)}")
        response = getattr(client, method)(path, json=json_body)
        self._lines.append(f"< HTTP {response.status_code}")
        try:
            body = response.get_json()
            self._lines.append(f"< body: {json.dumps(body)}")
        except Exception:
            self._lines.append(f"< body: {response.data.decode('utf-8', errors='replace')}")
        return response

    def test_lifecycle_transcript(self, client, patient_id, doctor_id):
        self._lines.append(
            "console-transcript: prescription tracker lifecycle "
            "(create, retrieve, list, complete, discontinue, immutability, duplicate-active)"
        )

        # 1. Create a valid prescription -> 201
        created = self._record(
            client, "post", "/prescriptions",
            _payload(patient_id, doctor_id, medicine_name="Amoxicillin"),
            label="Create valid prescription",
        )
        assert created.status_code == 201
        rx_id = created.get_json()["id"]

        # 2. Retrieve it by ID -> 200
        fetched = self._record(
            client, "get", f"/prescriptions/{rx_id}",
            label="Retrieve by ID",
        )
        assert fetched.status_code == 200
        assert fetched.get_json()["status"] == "active"

        # 3. Missing required field -> 400
        bad = _payload(patient_id, doctor_id)
        del bad["medicine_name"]
        invalid = self._record(
            client, "post", "/prescriptions", bad,
            label="Validation: missing required field",
        )
        assert invalid.status_code == 400

        # 4. end_date before start_date -> 400
        inverted = self._record(
            client, "post", "/prescriptions",
            _payload(patient_id, doctor_id, medicine_name="BadMed",
                     end_date="2025-12-31T08:00:00+00:00"),
            label="Validation: end_date precedes start_date",
        )
        assert inverted.status_code == 400

        # 5. Create a second prescription to exercise history sorting
        second = self._record(
            client, "post", "/prescriptions",
            _payload(patient_id, doctor_id, medicine_name="Metformin",
                     start_date="2026-06-01T08:00:00+00:00"),
            label="Create second prescription (newer start_date)",
        )
        assert second.status_code == 201
        second_id = second.get_json()["id"]

        # 6. Complete the first prescription
        completed = self._record(
            client, "patch", f"/prescriptions/{rx_id}/complete",
            label="Status transition: complete",
        )
        assert completed.status_code == 200
        assert completed.get_json()["status"] == "completed"

        # 7. Discontinue the second without reason -> 400
        no_reason = self._record(
            client, "patch", f"/prescriptions/{second_id}/discontinue", {},
            label="Discontinue without reason (rejected)",
        )
        assert no_reason.status_code == 400

        # 8. Discontinue with reason -> 200
        discontinued = self._record(
            client, "patch", f"/prescriptions/{second_id}/discontinue",
            {"reason": "Patient experienced nausea"},
            label="Discontinue with reason",
        )
        assert discontinued.status_code == 200
        assert discontinued.get_json()["status"] == "discontinued"

        # 9. Immutability: re-completing a completed prescription -> 400
        recomplete = self._record(
            client, "patch", f"/prescriptions/{rx_id}/complete",
            label="Immutability: re-complete a completed prescription (rejected)",
        )
        assert recomplete.status_code == 400

        # 10. PUT on a prescription -> 405 (mutation blocked)
        put_resp = self._record(
            client, "put", f"/prescriptions/{rx_id}",
            {"medicine_name": "Changed"}, label="Immutability: PUT rejected (405)",
        )
        assert put_resp.status_code == 405

        # 11. DELETE on a prescription -> 405 (no deletion of historical record)
        del_resp = self._record(
            client, "delete", f"/prescriptions/{rx_id}",
            label="Immutability: DELETE rejected (405)",
        )
        assert del_resp.status_code == 405

        # 12. List patient history -> active separated from historical, sorted DESC
        history = self._record(
            client, "get", f"/patients/{patient_id}/prescriptions",
            label="List patient history (sorted start_date DESC, active separated)",
        )
        assert history.status_code == 200
        body = history.get_json()
        assert len(body["historical"]) == 2
        starts = [datetime.fromisoformat(h["start_date"]) for h in body["historical"]]
        assert starts == sorted(starts, reverse=True)

        # 13. Create a fresh active prescription, then attempt a duplicate
        #     for the same patient+medicine while the first is still active -> 409
        active_rx = self._record(
            client, "post", "/prescriptions",
            _payload(patient_id, doctor_id, medicine_name="Ibuprofen",
                     start_date="2026-08-01T08:00:00+00:00"),
            label="Create a fresh active prescription (Ibuprofen)",
        )
        assert active_rx.status_code == 201

        dup = self._record(
            client, "post", "/prescriptions",
            _payload(patient_id, doctor_id, medicine_name="Ibuprofen",
                     start_date="2026-09-01T08:00:00+00:00"),
            label="Duplicate active prescription for same medicine (409)",
        )
        assert dup.status_code == 409

        self._lines.append("")
        self._lines.append("# end of transcript")

class TestDoseLogging:
    def test_log_dose_returns_201_and_is_retrievable(self, client, patient_id, doctor_id):
        created = client.post("/prescriptions", json=_payload(patient_id, doctor_id))
        rx_id = created.get_json()["id"]

        dose = client.post(
            f"/prescriptions/{rx_id}/doses",
            json={"taken_at": "2026-01-01T09:00:00+00:00", "status": "taken"},
        )
        assert dose.status_code == 201
        body = dose.get_json()
        assert body["status"] == "taken"
        assert body["prescription_id"] == rx_id

        logs = client.get(f"/prescriptions/{rx_id}/doses")
        assert logs.status_code == 200
        assert len(logs.get_json()) == 1

    def test_log_dose_defaults_taken_at_and_status(self, client, patient_id, doctor_id):
        created = client.post("/prescriptions", json=_payload(patient_id, doctor_id))
        rx_id = created.get_json()["id"]

        dose = client.post(f"/prescriptions/{rx_id}/doses", json={})
        assert dose.status_code == 201
        body = dose.get_json()
        assert body["status"] == "taken"
        assert body["taken_at"] is not None

    def test_log_dose_ordered_by_taken_at_ascending(self, client, patient_id, doctor_id):
        created = client.post("/prescriptions", json=_payload(patient_id, doctor_id))
        rx_id = created.get_json()["id"]

        client.post(f"/prescriptions/{rx_id}/doses",
                    json={"taken_at": "2026-01-03T09:00:00+00:00", "status": "taken"})
        client.post(f"/prescriptions/{rx_id}/doses",
                    json={"taken_at": "2026-01-01T09:00:00+00:00", "status": "taken"})
        client.post(f"/prescriptions/{rx_id}/doses",
                    json={"taken_at": "2026-01-02T09:00:00+00:00", "status": "skipped"})

        logs = client.get(f"/prescriptions/{rx_id}/doses").get_json()
        times = [datetime.fromisoformat(l["taken_at"]) for l in logs]
        assert times == sorted(times)
        assert [l["status"] for l in logs] == ["taken", "skipped", "taken"]

    def test_log_dose_unknown_prescription_returns_404(self, client):
        resp = client.post(f"/prescriptions/{uuid4()}/doses",
                           json={"taken_at": "2026-01-01T09:00:00+00:00"})
        assert resp.status_code == 404

    def test_log_dose_invalid_status_returns_400(self, client, patient_id, doctor_id):
        created = client.post("/prescriptions", json=_payload(patient_id, doctor_id))
        rx_id = created.get_json()["id"]

        resp = client.post(f"/prescriptions/{rx_id}/doses",
                           json={"taken_at": "2026-01-01T09:00:00+00:00", "status": "bogus"})
        assert resp.status_code == 400

    def test_log_dose_naive_timestamp_rejected(self, client, patient_id, doctor_id):
        created = client.post("/prescriptions", json=_payload(patient_id, doctor_id))
        rx_id = created.get_json()["id"]

        resp = client.post(f"/prescriptions/{rx_id}/doses",
                           json={"taken_at": "2026-01-01T09:00:00"})
        assert resp.status_code == 400

class TestTransitionsEndpoint:
    def test_transitions_returns_audit_trail(self, client, patient_id, doctor_id):
        created = client.post("/prescriptions", json=_payload(patient_id, doctor_id))
        rx_id = created.get_json()["id"]
        client.patch(f"/prescriptions/{rx_id}/discontinue",
                     json={"reason": "Side effects"})

        resp = client.get(f"/prescriptions/{rx_id}/transitions")
        assert resp.status_code == 200
        body = resp.get_json()
        assert len(body) == 1
        assert body[0]["to_status"] == "discontinued"
        assert body[0]["reason"] == "Side effects"

    def test_transitions_empty_for_fresh_prescription(self, client, patient_id, doctor_id):
        created = client.post("/prescriptions", json=_payload(patient_id, doctor_id))
        rx_id = created.get_json()["id"]

        resp = client.get(f"/prescriptions/{rx_id}/transitions")
        assert resp.status_code == 200
        assert resp.get_json() == []

class TestInvalidUuidPaths:
    def test_get_invalid_uuid_returns_400(self, client):
        assert client.get("/prescriptions/not-a-uuid").status_code == 400

    def test_history_invalid_patient_uuid_returns_400(self, client):
        assert client.get("/patients/not-a-uuid/prescriptions").status_code == 400

    def test_complete_invalid_uuid_returns_400(self, client):
        assert client.patch("/prescriptions/not-a-uuid/complete").status_code == 400

    def test_discontinue_invalid_uuid_returns_400(self, client):
        assert client.patch("/prescriptions/not-a-uuid/discontinue",
                            json={"reason": "x"}).status_code == 400

    def test_doses_invalid_uuid_returns_400(self, client):
        assert client.post("/prescriptions/not-a-uuid/doses").status_code == 400
        assert client.get("/prescriptions/not-a-uuid/doses").status_code == 400

    def test_transitions_invalid_uuid_returns_400(self, client):
        assert client.get("/prescriptions/not-a-uuid/transitions").status_code == 400

    def test_complete_unknown_prescription_returns_404(self, client):
        assert client.patch(f"/prescriptions/{uuid4()}/complete").status_code == 404

    def test_discontinue_unknown_prescription_returns_404(self, client):
        resp = client.patch(f"/prescriptions/{uuid4()}/discontinue",
                            json={"reason": "x"})
        assert resp.status_code == 404

    def test_create_empty_json_body_returns_400(self, client):
        resp = client.post("/prescriptions", data="",
                           content_type="application/json")
        assert resp.status_code == 400

    def test_recomplete_via_api_returns_400(self, client, patient_id, doctor_id):
        created = client.post("/prescriptions", json=_payload(patient_id, doctor_id))
        rx_id = created.get_json()["id"]
        assert client.patch(f"/prescriptions/{rx_id}/complete").status_code == 200
        assert client.patch(f"/prescriptions/{rx_id}/complete").status_code == 400

class TestRepositoryAndModelBranches:
    def test_get_by_id_missing_returns_none(self, service):
        assert service.get_prescription(uuid4()) is None

    def test_dose_logs_empty_for_new_prescription(self, service, patient_id, doctor_id):
        from prescription_tracker.models import DoseLog
        rx = service.create_prescription(Prescription(
            patient_id=patient_id, doctor_id=doctor_id, medicine_name="MedA",
            dosage_amount="100", dosage_unit="mg", frequency="daily",
            start_date="2026-01-01T08:00:00+00:00",
        ))
        assert service.get_dose_logs(rx.id) == []

        dose = DoseLog(
            prescription_id=rx.id,
            taken_at="2026-01-01T09:00:00+00:00",
            status="taken",
        )
        service.log_dose(dose)
        logs = service.get_dose_logs(rx.id)
        assert len(logs) == 1
        assert logs[0].status.value == "taken"

    def test_non_unique_integrity_error_propagates_as_non_conflict(self, service, patient_id, doctor_id):
        """A non-unique-constraint IntegrityError (e.g. FK failure) must not be
        misclassified as a ConflictError."""
        import sqlite3
        rx = Prescription(
            patient_id=patient_id, doctor_id=doctor_id, medicine_name="MedA",
            dosage_amount="100", dosage_unit="mg", frequency="daily",
            start_date="2026-01-01T08:00:00+00:00",
        )
        # Corrupt by deleting the patient row after create to force a non-unique
        # IntegrityError on a subsequent create path is hard; instead directly
        # exercise the service guard by forcing a generic IntegrityError.
        original = service.repository.create

        def _raise_generic(prescription):
            raise sqlite3.IntegrityError("foreign key constraint failed")

        service.repository.create = _raise_generic
        try:
            with pytest.raises(sqlite3.IntegrityError):
                service.create_prescription(rx)
        finally:
            service.repository.create = original

    def test_prescription_to_dict_roundtrip_includes_all_fields(self, patient_id, doctor_id):
        rx = Prescription(
            patient_id=patient_id, doctor_id=doctor_id, medicine_name="MedA",
            dosage_amount="100", dosage_unit="mg", frequency="daily",
            start_date="2026-01-01T08:00:00+00:00",
            end_date="2026-02-01T08:00:00+00:00",
        )
        d = rx.to_dict()
        assert d["medicine_name"] == "MedA"
        assert d["end_date"] == "2026-02-01T08:00:00+00:00"
        assert d["status"] == "active"
