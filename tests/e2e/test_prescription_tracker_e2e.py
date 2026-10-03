"""Feature-level end-to-end test for the prescription tracker.

Drives the complete prescription-tracker lifecycle from a user's perspective
through the real Flask HTTP API, exactly the way the feature-level gate runs
this file: ``pytest tests/e2e/test_prescription_tracker_e2e.py``. It exercises,
in order:

  1. Creating a prescription with all required fields.
  2. Fetching a patient's prescription history sorted by start date.
  3. Recording a status transition to discontinued with a mandatory reason.
  4. Confirming validation rejects malformed entries:
       a. missing required fields -> 400
       b. end date before start date -> 400
  5. Confirming a duplicate active prescription for the same medicine is
     rejected (409).

The test stands up its own in-memory Flask app so it does not depend on the
repo-root conftest fixtures. Every assertion is a genuine behavioural check —
nothing is stubbed — so a regression in any gate-relevant behaviour fails the
feature E2E.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import pytest


@pytest.fixture
def app():
    from prescription_tracker.api import create_app

    return create_app(db_path=":memory:")


@pytest.fixture
def client(app):
    return app.test_client()


def _payload(patient_id, doctor_id, **overrides):
    """A minimal valid prescription request body."""
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


def test_prescription_tracker_lifecycle_end_to_end(client):
    """The full create -> history -> discontinue -> validation -> duplicate path."""
    patient_id = uuid4()
    doctor_id = uuid4()

    # 1. Create a prescription with all required fields -> 201, retrievable.
    create_resp = client.post(
        "/prescriptions", json=_payload(patient_id, doctor_id)
    )
    assert create_resp.status_code == 201, create_resp.get_data(as_text=True)
    created = create_resp.get_json()
    rx_id = created["id"]
    assert created["patient_id"] == str(patient_id)
    assert created["medicine_name"] == "Amoxicillin"
    assert created["status"] == "active"
    assert created["start_date"] == "2026-01-01T08:00:00+00:00"

    # The created prescription is retrievable by id (separate request).
    fetch = client.get(f"/prescriptions/{rx_id}")
    assert fetch.status_code == 200
    assert fetch.get_json()["id"] == rx_id

    # 2. Fetch the patient's prescription history sorted by start date.
    #    Add a second, newer prescription so ordering is observable, then
    #    assert the active partition is sorted by start_date descending.
    newer = client.post(
        "/prescriptions",
        json=_payload(patient_id, doctor_id, medicine_name="Metformin",
                      start_date="2026-06-01T08:00:00+00:00"),
    )
    assert newer.status_code == 201, newer.get_data(as_text=True)

    history_resp = client.get(f"/patients/{patient_id}/prescriptions")
    assert history_resp.status_code == 200
    history = history_resp.get_json()
    active = history["active"]
    assert len(active) == 2
    starts = [datetime.fromisoformat(rx["start_date"]) for rx in active]
    assert starts == sorted(starts, reverse=True), (
        f"history not sorted by start_date DESC: {starts}"
    )

    # 3. Record a status transition to discontinued with a mandatory reason.
    #    A discontinue without a reason is rejected first (400, row unchanged),
    #    then a valid discontinue succeeds (200) and is reflected in history.
    #    Both an empty-string reason and a missing reason key are rejected.
    no_reason = client.patch(
        f"/prescriptions/{rx_id}/discontinue", json={"reason": ""}
    )
    assert no_reason.status_code == 400
    assert "reason" in no_reason.get_json()["error"].lower()

    no_reason_key = client.patch(
        f"/prescriptions/{rx_id}/discontinue", json={}
    )
    assert no_reason_key.status_code == 400
    assert "reason" in no_reason_key.get_json()["error"].lower()

    # Row must still be active — no partial mutation.
    assert client.get(f"/prescriptions/{rx_id}").get_json()["status"] == "active"

    discontinue = client.patch(
        f"/prescriptions/{rx_id}/discontinue",
        json={"reason": "Patient experienced an adverse reaction"},
    )
    assert discontinue.status_code == 200, discontinue.get_data(as_text=True)
    discontinued = discontinue.get_json()
    assert discontinued["status"] == "discontinued"
    assert discontinued["id"] == rx_id

    # The row is preserved (immutability — no deletion), still retrievable.
    again = client.get(f"/prescriptions/{rx_id}")
    assert again.status_code == 200
    assert again.get_json()["status"] == "discontinued"

    # The discontinued prescription moved from the active to the historical
    # partition, and history is still sorted by start_date descending.
    history_after = client.get(
        f"/patients/{patient_id}/prescriptions"
    ).get_json()
    active_ids = {rx["id"] for rx in history_after["active"]}
    historical_ids = {rx["id"] for rx in history_after["historical"]}
    assert rx_id not in active_ids
    assert rx_id in historical_ids
    hist_starts = [datetime.fromisoformat(rx["start_date"]) for rx in history_after["historical"]]
    assert hist_starts == sorted(hist_starts, reverse=True)

    # The status transition was recorded on the audit trail with a reason.
    transitions = client.get(f"/prescriptions/{rx_id}/transitions").get_json()
    assert len(transitions) == 1
    assert transitions[0]["to_status"] == "discontinued"
    assert transitions[0]["reason"] == "Patient experienced an adverse reaction"

    # 4a. Validation rejects a missing required field -> 400, nothing persisted.
    bad = _payload(patient_id, doctor_id, medicine_name="Naproxen")
    del bad["medicine_name"]
    bad_resp = client.post("/prescriptions", json=bad)
    assert bad_resp.status_code == 400, bad_resp.get_data(as_text=True)
    # No Naproxen row was created for this patient.
    all_rx = (
        client.get(f"/patients/{patient_id}/prescriptions").get_json()
    )
    names = {rx["medicine_name"] for rx in all_rx["active"]} | {
        rx["medicine_name"] for rx in all_rx["historical"]
    }
    assert "Naproxen" not in names

    # 4b. Validation rejects end date before start date -> 400.
    inverted = _payload(
        patient_id, doctor_id, medicine_name="Ibuprofen",
        start_date="2026-02-01T08:00:00+00:00",
        end_date="2026-01-01T08:00:00+00:00",
    )
    inverted_resp = client.post("/prescriptions", json=inverted)
    assert inverted_resp.status_code == 400, inverted_resp.get_data(as_text=True)
    assert "end_date" in inverted_resp.get_json()["error"]

    # 5. A duplicate active prescription for the same medicine is rejected (409).
    #    The Amoxicillin prescription above was discontinued, so a fresh active
    #    one is allowed; then a second active one for the same medicine is not.
    re_prescribe = client.post(
        "/prescriptions",
        json=_payload(patient_id, doctor_id, medicine_name="Amoxicillin",
                      start_date="2026-07-01T08:00:00+00:00"),
    )
    assert re_prescribe.status_code == 201, re_prescribe.get_data(as_text=True)

    dup = client.post(
        "/prescriptions",
        json=_payload(patient_id, doctor_id, medicine_name="Amoxicillin",
                      start_date="2026-08-01T08:00:00+00:00"),
    )
    assert dup.status_code == 409, dup.get_data(as_text=True)
    assert "active" in dup.get_json()["error"].lower()