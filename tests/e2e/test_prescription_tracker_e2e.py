"""Feature-level end-to-end test for the prescription tracker.

This is the file the feature-level gate runs:
``pytest tests/e2e/test_prescription_tracker_e2e.py``. It drives the complete
prescription-tracker lifecycle from a user's perspective through the real
FastAPI HTTP surface, in order:

  1. Creating a prescription with all required fields.
  2. Fetching a patient's prescription history sorted by start date.
  3. Recording a status transition to discontinued with a mandatory reason.
  4. Confirming validation rejects malformed entries:
       a. missing required fields -> 400/422
       b. end date before start date -> 400
  5. Confirming a duplicate active prescription for the same medicine is
     rejected (409).

The test stands up its own app against a per-test on-disk SQLite file (via
``MEDICATION_TRACKER_DB``) so cross-request persistence is exercised the way a
real server run works, without relying on the repo-root conftest fixtures.
Every assertion is a genuine behavioural check — nothing is stubbed — so a
regression in any gate-relevant behaviour fails the feature E2E.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "e2e.db"


@pytest.fixture
def client(db_path: Path, monkeypatch) -> Iterator[TestClient]:
    # Point the app at a per-test on-disk file so rows persist across requests.
    monkeypatch.setenv("MEDICATION_TRACKER_DB", str(db_path))
    from medication_tracker.app import create_app

    with TestClient(create_app()) as c:
        yield c


def _payload(doctor_id: str | None = None, **overrides):
    """A minimal valid prescription request body."""
    base = {
        "doctor_id": doctor_id or str(uuid4()),
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


def test_prescription_tracker_lifecycle_end_to_end(client):
    """The full create -> history -> discontinue -> validation -> duplicate path."""
    patient_id = str(uuid4())

    # 1. Create a prescription with all required fields -> 201, retrievable.
    create_resp = client.post(
        f"/patients/{patient_id}/prescriptions", json=_payload()
    )
    assert create_resp.status_code == 201, create_resp.text
    created = create_resp.json()
    rx_id = created["id"]
    assert created["patient_id"] == patient_id
    assert created["medicine_name"] == "Amoxicillin"
    assert created["status"] == "active"
    assert created["start_date"] == "2026-01-01T00:00:00+00:00"

    # The created prescription is retrievable by id (separate request).
    fetch = client.get(f"/prescriptions/{rx_id}")
    assert fetch.status_code == 200
    assert fetch.json()["id"] == rx_id

    # 2. Fetch the patient's prescription history sorted by start date.
    #    Add a second, newer prescription so ordering is observable, then
    #    assert history is sorted by start_date descending.
    newer = client.post(
        f"/patients/{patient_id}/prescriptions",
        json=_payload(medicine_name="Metformin",
                      start_date="2026-06-01T00:00:00+00:00"),
    )
    assert newer.status_code == 201, newer.text

    history_resp = client.get(f"/patients/{patient_id}/prescriptions")
    assert history_resp.status_code == 200
    history = history_resp.json()
    assert len(history) == 2
    starts = [datetime.fromisoformat(h["start_date"]) for h in history]
    assert starts == sorted(starts, reverse=True), (
        f"history not sorted by start_date DESC: {starts}"
    )

    # 3. Record a status transition to discontinued with a mandatory reason.
    #    A discontinue without a reason is rejected first (400/422, row
    #    unchanged), then a valid discontinue succeeds (200).
    no_reason = client.patch(
        f"/prescriptions/{rx_id}/discontinue", json={"reason": ""}
    )
    assert no_reason.status_code in (400, 422), no_reason.text
    # Row must still be active — no partial mutation.
    assert client.get(f"/prescriptions/{rx_id}").json()["status"] == "active"

    discontinue = client.patch(
        f"/prescriptions/{rx_id}/discontinue",
        json={"reason": "Patient experienced an adverse reaction"},
    )
    assert discontinue.status_code == 200, discontinue.text
    discontinued = discontinue.json()
    assert discontinued["status"] == "discontinued"
    assert discontinued["id"] == rx_id
    # The row is preserved (immutability — no deletion), still retrievable.
    again = client.get(f"/prescriptions/{rx_id}")
    assert again.status_code == 200
    assert again.json()["status"] == "discontinued"

    # 4a. Validation rejects a missing required field -> 400/422, nothing
    #     persisted for that patient beyond the two rows above.
    bad = _payload(medicine_name="Naproxen")
    del bad["medicine_name"]
    bad_resp = client.post(
        f"/patients/{patient_id}/prescriptions", json=bad
    )
    assert bad_resp.status_code in (400, 422), bad_resp.text
    # No Naproxen row was created.
    all_rx = client.get(f"/patients/{patient_id}/prescriptions").json()
    names = {rx["medicine_name"] for rx in all_rx}
    assert "Naproxen" not in names

    # 4b. Validation rejects end date before start date -> 400.
    inverted = _payload(
        medicine_name="Ibuprofen",
        start_date="2026-02-01T00:00:00+00:00",
        end_date="2026-01-01T00:00:00+00:00",
    )
    inverted_resp = client.post(
        f"/patients/{patient_id}/prescriptions", json=inverted
    )
    assert inverted_resp.status_code == 400, inverted_resp.text

    # 5. A duplicate active prescription for the same medicine is rejected
    #    (409). The Amoxicillin prescription above was discontinued, so a fresh
    #    active one is allowed; then a second active one is not.
    re_prescribe = client.post(
        f"/patients/{patient_id}/prescriptions",
        json=_payload(medicine_name="Amoxicillin",
                      start_date="2026-07-01T00:00:00+00:00"),
    )
    assert re_prescribe.status_code == 201, re_prescribe.text

    dup = client.post(
        f"/patients/{patient_id}/prescriptions",
        json=_payload(medicine_name="Amoxicillin",
                      start_date="2026-08-01T00:00:00+00:00"),
    )
    assert dup.status_code == 409, dup.text