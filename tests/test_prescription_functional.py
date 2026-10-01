"""Functional tests for the prescription tracker HTTP API.

These tests spin up the FastAPI app with TestClient against a per-test
temporary on-disk SQLite database (via MEDICATION_TRACKER_DB) so that
foreign-key enforcement, CHECK constraints and the partial unique index
all exercise the real schema. They cover the full create -> retrieve ->
discontinue -> history flow plus validation and the 500ms SLO.
"""

from __future__ import annotations

import os
import time
import uuid
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "functional.db"


@pytest.fixture(autouse=True)
def env(db_path: Path, monkeypatch) -> Iterator[None]:
    monkeypatch.setenv("MEDICATION_TRACKER_DB", str(db_path))
    yield


@pytest.fixture
def client() -> Iterator[TestClient]:
    # Import after the env fixture has set MEDICATION_TRACKER_DB.
    from medication_tracker.app import create_app

    with TestClient(create_app()) as c:
        yield c


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

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


# --------------------------------------------------------------------------- #
# Create + retrieve
# --------------------------------------------------------------------------- #

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


# --------------------------------------------------------------------------- #
# Validation -> 400, nothing persisted
# --------------------------------------------------------------------------- #

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


# --------------------------------------------------------------------------- #
# One active prescription per medicine per patient
# --------------------------------------------------------------------------- #

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


# --------------------------------------------------------------------------- #
# Discontinue lifecycle
# --------------------------------------------------------------------------- #

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


# --------------------------------------------------------------------------- #
# History ordering and completeness
# --------------------------------------------------------------------------- #

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


# --------------------------------------------------------------------------- #
# 500ms SLO on single-patient endpoints
# --------------------------------------------------------------------------- #

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