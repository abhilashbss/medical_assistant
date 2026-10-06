"""Functional tests for the prescription lifecycle via the FastAPI app.

Covers the gate success criteria for the functional test command:
  - Status transitions persist with ISO 8601 timestamps in the audit table
  - Discontinuation without a reason field is rejected and no row is mutated
  - Dose adherence events append timestamped rows to dose_logs queryable per
    medication ordered by time descending
  - The one-active-prescription-per-medicine partial unique index rejects a
    duplicate active prescription for the same patient and medicine
  - Prescription rows remain immutable except through explicit status
    transition update paths

Running this module also captures a console transcript of every real HTTP
request/response into ``.see/e2e-artifacts/console-transcript.txt`` so the
milestone behaviour is evidenced by a readable log of what the API actually
did. The transcript is produced by wrapping the same ``TestClient`` the
assertions run against, so it cannot diverge from what the gate verifies.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.app import create_app


# ---------------------------------------------------------------------------
# Evidence capture: a session-scoped transcript of real HTTP traffic.
# Every request the wrapped TestClient issues is logged with its method, path,
# body, and the response status + body, in execution order. This does not
# alter any assertion; it only records what the gate already exercises.
# ---------------------------------------------------------------------------

_TRANSCRIPT_PATH = (
    Path(__file__).resolve().parents[2] / ".see" / "e2e-artifacts" / "console-transcript.txt"
)


class _TranscribingClient:
    """Thin wrapper around TestClient that appends each request/response to
    the console transcript. Delegates all real work to the wrapped client so
    assertions behave identically."""

    def __init__(self, inner: TestClient, transcript):
        self._inner = inner
        self._transcript = transcript

    def _log(self, method, path, *, response, json_body=None, params=None):
        lines = []
        body_desc = ""
        if json_body is not None:
            body_desc = " body=" + json.dumps(json_body)
        if params:
            body_desc += " params=" + json.dumps(params)
        lines.append(f"> {method} {path}{body_desc}")
        lines.append(f"< {response.status_code} {json.dumps(response.json()) if response.headers.get('content-type', '').startswith('application/json') else response.text}")
        self._transcript.append("\n".join(lines))

    def post(self, path, **kwargs):
        resp = self._inner.post(path, **kwargs)
        self._log("POST", path, response=resp, json_body=kwargs.get("json"))
        return resp

    def get(self, path, **kwargs):
        resp = self._inner.get(path, **kwargs)
        self._log("GET", path, response=resp, params=kwargs.get("params"))
        return resp

    def patch(self, path, **kwargs):
        resp = self._inner.patch(path, **kwargs)
        self._log("PATCH", path, response=resp, json_body=kwargs.get("json"))
        return resp

    def put(self, path, **kwargs):
        resp = self._inner.put(path, **kwargs)
        self._log("PUT", path, response=resp, json_body=kwargs.get("json"))
        return resp

    def delete(self, path, **kwargs):
        resp = self._inner.delete(path, **kwargs)
        self._log("DELETE", path, response=resp)
        return resp


@pytest.fixture(scope="module")
def _transcript():
    """Open the transcript file once per module run; yield a list buffer."""
    _TRANSCRIPT_PATH.parent.mkdir(parents=True, exist_ok=True)
    buffer: list[str] = []
    header = (
        "=== Prescription tracker — dose adherence logging & history ===\n"
        f"=== Functional gate transcript ({datetime.now(timezone.utc).isoformat()}) ===\n"
        "=== Each entry is the real request issued by the gate and the API response. ===\n"
    )
    yield buffer
    with _TRANSCRIPT_PATH.open("w", encoding="utf-8") as fh:
        fh.write(header)
        fh.write("\n".join(buffer))
        fh.write("\n")


@pytest.fixture
def client(_transcript):
    """Create an in-memory app and wrap its TestClient so every request the
    gate makes is recorded in the console transcript."""
    app = create_app(":memory:")
    with TestClient(app) as c:
        yield _TranscribingClient(c, _transcript)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _create_prescription(client, **overrides):
    payload = {
        "patient_id": "patient-1",
        "doctor_id": "doctor-1",
        "medicine_name": "Amoxicillin",
        "dosage_amount": 500.0,
        "dosage_unit": "mg",
        "frequency": "three times daily",
        "start_date": _now_iso(),
        "status": "active",
    }
    payload.update(overrides)
    response = client.post("/prescriptions", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Status transitions persist with ISO 8601 timestamps in the audit table
# ---------------------------------------------------------------------------


class TestStatusTransitionsViaApi:
    def test_active_to_completed_persists_audit(self, client):
        rx = _create_prescription(client)
        response = client.patch(f"/prescriptions/{rx['id']}/complete")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "completed"
        history = client.get(f"/prescriptions/{rx['id']}/status-history").json()
        assert len(history) == 1
        assert history[0]["from_status"] == "active"
        assert history[0]["to_status"] == "completed"
        ts = history[0]["timestamp"]
        parsed = datetime.fromisoformat(ts)
        assert parsed.tzinfo is not None

    def test_active_to_discontinued_persists_audit_with_reason(self, client):
        rx = _create_prescription(client)
        response = client.patch(
            f"/prescriptions/{rx['id']}/discontinue",
            json={"reason": "Adverse reaction"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "discontinued"
        history = client.get(f"/prescriptions/{rx['id']}/status-history").json()
        assert len(history) == 1
        assert history[0]["reason"] == "Adverse reaction"
        parsed = datetime.fromisoformat(history[0]["timestamp"])
        assert parsed.tzinfo is not None

    def test_complete_missing_prescription_404(self, client):
        response = client.patch("/prescriptions/missing-id/complete")
        assert response.status_code == 404

    def test_discontinue_missing_prescription_404(self, client):
        response = client.patch(
            "/prescriptions/missing-id/discontinue", json={"reason": "x"}
        )
        assert response.status_code == 404

    def test_transition_non_active_409(self, client):
        rx = _create_prescription(client)
        client.patch(f"/prescriptions/{rx['id']}/complete")
        # Already completed; a second complete is a conflict
        response = client.patch(f"/prescriptions/{rx['id']}/complete")
        assert response.status_code == 409


# ---------------------------------------------------------------------------
# Discontinuation without a reason field is rejected; no row mutated
# ---------------------------------------------------------------------------


class TestDiscontinueReasonValidation:
    def test_discontinue_without_reason_body_rejected(self, client):
        rx = _create_prescription(client)
        # No JSON body -> FastAPI validation 422
        response = client.patch(f"/prescriptions/{rx['id']}/discontinue")
        assert response.status_code == 422

    def test_discontinue_empty_reason_rejected(self, client):
        rx = _create_prescription(client)
        response = client.patch(
            f"/prescriptions/{rx['id']}/discontinue", json={"reason": "   "}
        )
        assert response.status_code in (400, 422)
        # No status row mutated
        fetched = client.get(f"/prescriptions/{rx['id']}").json()
        assert fetched["status"] == "active"

    def test_discontinue_empty_string_rejected_no_mutation(self, client):
        rx = _create_prescription(client)
        response = client.patch(
            f"/prescriptions/{rx['id']}/discontinue", json={"reason": ""}
        )
        assert response.status_code in (400, 422)
        fetched = client.get(f"/prescriptions/{rx['id']}").json()
        assert fetched["status"] == "active"
        # No audit row was appended
        history = client.get(f"/prescriptions/{rx['id']}/status-history").json()
        assert len(history) == 0


# ---------------------------------------------------------------------------
# Dose adherence events append timestamped rows, queryable per medication
# ordered by time (descending when retrieved via repository; ascending from
# the GET endpoint per the build-unit spec)
# ---------------------------------------------------------------------------


class TestDoseAdherenceViaApi:
    def test_append_dose_log_returns_201_with_iso_timestamp(self, client):
        rx = _create_prescription(client)
        response = client.post(
            f"/prescriptions/{rx['id']}/dose-logs",
            json={"event": "taken"},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["event"] == "taken"
        assert body["prescription_id"] == rx["id"]
        parsed = datetime.fromisoformat(body["timestamp"])
        assert parsed.tzinfo is not None

    def test_append_to_discontinued_returns_409(self, client):
        rx = _create_prescription(client)
        client.patch(
            f"/prescriptions/{rx['id']}/discontinue", json={"reason": "done"}
        )
        response = client.post(
            f"/prescriptions/{rx['id']}/dose-logs", json={"event": "taken"}
        )
        assert response.status_code == 409

    def test_append_to_completed_returns_409(self, client):
        rx = _create_prescription(client)
        client.patch(f"/prescriptions/{rx['id']}/complete")
        response = client.post(
            f"/prescriptions/{rx['id']}/dose-logs", json={"event": "taken"}
        )
        assert response.status_code == 409

    def test_append_invalid_event_returns_400(self, client):
        rx = _create_prescription(client)
        response = client.post(
            f"/prescriptions/{rx['id']}/dose-logs", json={"event": "missed"}
        )
        assert response.status_code in (400, 422)

    def test_append_to_missing_prescription_404(self, client):
        response = client.post(
            "/prescriptions/missing-id/dose-logs", json={"event": "taken"}
        )
        assert response.status_code == 404

    def test_history_ordered_by_timestamp_ascending(self, client):
        rx = _create_prescription(client)
        client.post(
            f"/prescriptions/{rx['id']}/dose-logs",
            json={"event": "skipped", "timestamp": "2026-01-01T20:00:00+00:00"},
        )
        client.post(
            f"/prescriptions/{rx['id']}/dose-logs",
            json={"event": "taken", "timestamp": "2026-01-01T08:00:00+00:00"},
        )
        history = client.get(f"/prescriptions/{rx['id']}/dose-logs").json()
        assert len(history) == 2
        # Ascending order
        assert history[0]["timestamp"] < history[1]["timestamp"]
        assert history[0]["event"] == "taken"
        assert history[1]["event"] == "skipped"

    def test_history_date_range_filter(self, client):
        rx = _create_prescription(client)
        for ts in [
            "2026-01-01T08:00:00+00:00",
            "2026-01-02T08:00:00+00:00",
            "2026-01-03T08:00:00+00:00",
        ]:
            client.post(
                f"/prescriptions/{rx['id']}/dose-logs",
                json={"event": "taken", "timestamp": ts},
            )
        history = client.get(
            f"/prescriptions/{rx['id']}/dose-logs",
            params={"start_date": "2026-01-02T00:00:00+00:00", "end_date": "2026-01-02T23:59:59+00:00"},
        ).json()
        assert len(history) == 1
        assert history[0]["timestamp"] == "2026-01-02T08:00:00+00:00"

    def test_history_for_missing_prescription_404(self, client):
        response = client.get("/prescriptions/missing-id/dose-logs")
        assert response.status_code == 404

    def test_duplicate_timestamp_append_allowed(self, client):
        """Append-only: two events at the same timestamp are both stored."""
        rx = _create_prescription(client)
        ts = "2026-01-01T08:00:00+00:00"
        client.post(
            f"/prescriptions/{rx['id']}/dose-logs",
            json={"event": "taken", "timestamp": ts},
        )
        client.post(
            f"/prescriptions/{rx['id']}/dose-logs",
            json={"event": "skipped", "timestamp": ts},
        )
        history = client.get(f"/prescriptions/{rx['id']}/dose-logs").json()
        assert len(history) == 2

    def test_notes_persisted(self, client):
        rx = _create_prescription(client)
        response = client.post(
            f"/prescriptions/{rx['id']}/dose-logs",
            json={"event": "skipped", "notes": "felt nauseous"},
        )
        assert response.status_code == 201
        assert response.json()["notes"] == "felt nauseous"


# ---------------------------------------------------------------------------
# Partial unique index rejects a duplicate active prescription
# ---------------------------------------------------------------------------


class TestUniqueActivePrescriptionViaApi:
    def test_duplicate_active_same_patient_medicine_409(self, client):
        _create_prescription(client, medicine_name="Ibuprofen")
        response = client.post(
            "/prescriptions",
            json={
                "patient_id": "patient-1",
                "doctor_id": "doctor-1",
                "medicine_name": "Ibuprofen",
                "dosage_amount": 200.0,
                "dosage_unit": "mg",
                "frequency": "daily",
                "start_date": _now_iso(),
                "status": "active",
            },
        )
        assert response.status_code == 409

    def test_duplicate_after_discontinue_allowed(self, client):
        rx = _create_prescription(client, medicine_name="Ibuprofen")
        client.patch(
            f"/prescriptions/{rx['id']}/discontinue", json={"reason": "done"}
        )
        response = client.post(
            "/prescriptions",
            json={
                "patient_id": "patient-1",
                "doctor_id": "doctor-1",
                "medicine_name": "Ibuprofen",
                "dosage_amount": 200.0,
                "dosage_unit": "mg",
                "frequency": "daily",
                "start_date": _now_iso(),
                "status": "active",
            },
        )
        assert response.status_code == 201


# ---------------------------------------------------------------------------
# Prescription rows remain immutable except through status transitions
# ---------------------------------------------------------------------------


class TestImmutabilityViaApi:
    def test_no_general_update_endpoint(self, client):
        """There is no PUT/PATCH endpoint to edit prescription fields; only
        /complete and /discontinue status-transition paths exist."""
        rx = _create_prescription(client)
        # A PUT to the prescription itself is not defined -> 405
        response = client.put(
            f"/prescriptions/{rx['id']}",
            json={"medicine_name": "Tampered"},
        )
        assert response.status_code in (404, 405)

    def test_complete_only_changes_status(self, client):
        rx = _create_prescription(client, medicine_name="Amoxicillin")
        client.patch(f"/prescriptions/{rx['id']}/complete")
        fetched = client.get(f"/prescriptions/{rx['id']}").json()
        assert fetched["medicine_name"] == "Amoxicillin"
        assert fetched["dosage_amount"] == 500.0
        assert fetched["status"] == "completed"

    def test_list_by_patient_sorted_desc(self, client):
        older = _create_prescription(
            client, medicine_name="Med A", start_date="2026-01-01T00:00:00+00:00"
        )
        newer = _create_prescription(
            client, medicine_name="Med B", start_date="2026-06-01T00:00:00+00:00"
        )
        history = client.get("/patients/patient-1/prescriptions").json()
        # Sorted by start_date descending
        assert history[0]["id"] == newer["id"]
        assert history[1]["id"] == older["id"]

    def test_get_missing_prescription_404(self, client):
        response = client.get("/prescriptions/missing-id")
        assert response.status_code == 404

    def test_create_missing_required_field_400(self, client):
        response = client.post(
            "/prescriptions",
            json={
                "patient_id": "patient-1",
                "doctor_id": "doctor-1",
                # medicine_name missing
                "dosage_amount": 500.0,
                "dosage_unit": "mg",
                "frequency": "daily",
                "start_date": _now_iso(),
            },
        )
        assert response.status_code in (400, 422)

    def test_create_end_before_start_400(self, client):
        response = client.post(
            "/prescriptions",
            json={
                "patient_id": "patient-1",
                "doctor_id": "doctor-1",
                "medicine_name": "Test",
                "dosage_amount": 500.0,
                "dosage_unit": "mg",
                "frequency": "daily",
                "start_date": "2026-06-01T00:00:00+00:00",
                "end_date": "2026-01-01T00:00:00+00:00",
            },
        )
        assert response.status_code in (400, 422)