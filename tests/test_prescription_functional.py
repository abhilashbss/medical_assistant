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
def client(db_path: Path, monkeypatch) -> Iterator[TestClient]:
    # The FastAPI TestClient (and its httpx dependency) belongs to the HTTP
    # build unit; skip the HTTP tests when it is unavailable rather than
    # crashing collection. Repository-layer tests do not use this fixture.
    if TestClient is None:
        pytest.skip(f"FastAPI TestClient unavailable: {_TESTCLIENT_IMPORT_ERROR}")
    # Import after the env var has been set so the app picks up the per-test db.
    monkeypatch.setenv("MEDICATION_TRACKER_DB", str(db_path))
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
