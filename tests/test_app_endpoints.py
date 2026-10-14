"""API endpoint tests via a stdlib ASGI client — exercises app.py and lifts coverage."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from tests.asgi_client import ASGIClient
from prescription_tracker.app import app
from prescription_tracker.db import seed_reference_data, init_db
from prescription_tracker.repository import PrescriptionRepository

PATIENT = "patient-api"
DOCTOR = "doctor-api"


def _iso(dt: datetime) -> str:
    return dt.isoformat()


@pytest.fixture
def client(monkeypatch):
    # Fresh in-memory DB for each test.
    conn = init_db()
    monkeypatch.setattr("prescription_tracker.app._conn", conn)
    monkeypatch.setattr("prescription_tracker.app._repo", PrescriptionRepository(conn))
    return ASGIClient(app)


def _payload(medicine="ApiMed", **kw):
    base = {
        "doctor_id": DOCTOR,
        "medicine_name": medicine,
        "dosage_amount": 100.0,
        "dosage_unit": "mg",
        "frequency": "1x/day",
        "start_date": _iso(datetime(2026, 1, 1, tzinfo=timezone.utc)),
    }
    base.update(kw)
    return base


class TestCreateAndRetrieve:
    def test_create_and_get(self, client):
        r = client.post(f"/patients/{PATIENT}/prescriptions", json=_payload())
        assert r.status_code == 200
        rx_id = r.json()["id"]
        r2 = client.get(f"/prescriptions/{rx_id}")
        assert r2.status_code == 200
        assert r2.json()["medicine_name"] == "ApiMed"

    def test_create_missing_field_422(self, client):
        p = _payload()
        p["medicine_name"] = ""
        r = client.post(f"/patients/{PATIENT}/prescriptions", json=p)
        assert r.status_code == 422

    def test_create_end_before_start_422(self, client):
        p = _payload(
            start_date=_iso(datetime(2026, 6, 1, tzinfo=timezone.utc)),
            end_date=_iso(datetime(2026, 5, 1, tzinfo=timezone.utc)),
        )
        r = client.post(f"/patients/{PATIENT}/prescriptions", json=p)
        assert r.status_code == 422

    def test_get_404(self, client):
        assert client.get("/prescriptions/nope").status_code == 404


class TestListAndHistory:
    def test_list_by_patient(self, client):
        client.post(f"/patients/{PATIENT}/prescriptions", json=_payload(medicine="M1"))
        r = client.get(f"/patients/{PATIENT}/prescriptions")
        assert r.status_code == 200
        body = r.json()
        assert "active" in body and "historical" in body
        assert len(body["active"]) >= 1


class TestLifecycle:
    def test_complete(self, client):
        rx_id = client.post(
            f"/patients/{PATIENT}/prescriptions", json=_payload(medicine="Comp")
        ).json()["id"]
        r = client.patch(f"/prescriptions/{rx_id}/complete")
        assert r.status_code == 200
        assert r.json()["status"] == "completed"

    def test_discontinue_no_reason_422(self, client):
        rx_id = client.post(
            f"/patients/{PATIENT}/prescriptions", json=_payload(medicine="Disc")
        ).json()["id"]
        r = client.patch(f"/prescriptions/{rx_id}/discontinue", json={"reason": ""})
        assert r.status_code == 422

    def test_discontinue_with_reason(self, client):
        rx_id = client.post(
            f"/patients/{PATIENT}/prescriptions", json=_payload(medicine="Disc2")
        ).json()["id"]
        r = client.patch(
            f"/prescriptions/{rx_id}/discontinue", json={"reason": "side effects"}
        )
        assert r.status_code == 200
        assert r.json()["status"] == "discontinued"

    def test_complete_404(self, client):
        assert client.patch("/prescriptions/nope/complete").status_code == 404

    def test_discontinue_404(self, client):
        r = client.patch("/prescriptions/nope/discontinue", json={"reason": "x"})
        assert r.status_code == 404


class TestDoseLogs:
    def test_add_and_get_dose_log(self, client):
        rx_id = client.post(
            f"/patients/{PATIENT}/prescriptions", json=_payload(medicine="DL")
        ).json()["id"]
        r = client.post(
            f"/prescriptions/{rx_id}/dose-logs",
            json={
                "event": "taken",
                "timestamp": _iso(datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc)),
            },
        )
        assert r.status_code == 200
        assert r.json()["event"] == "taken"
        r2 = client.get(f"/prescriptions/{rx_id}/dose-logs")
        assert r2.status_code == 200
        assert len(r2.json()) == 1

    def test_dose_log_invalid_event_422(self, client):
        rx_id = client.post(
            f"/patients/{PATIENT}/prescriptions", json=_payload(medicine="DL2")
        ).json()["id"]
        r = client.post(
            f"/prescriptions/{rx_id}/dose-logs",
            json={
                "event": "maybe",
                "timestamp": _iso(datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc)),
            },
        )
        assert r.status_code == 422

    def test_dose_log_nonexistent_rx_404(self, client):
        r = client.post(
            "/prescriptions/nope/dose-logs",
            json={
                "event": "taken",
                "timestamp": _iso(datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc)),
            },
        )
        assert r.status_code == 404

    def test_dose_log_with_date_range(self, client):
        rx_id = client.post(
            f"/patients/{PATIENT}/prescriptions", json=_payload(medicine="DL3")
        ).json()["id"]
        for h in (8, 14, 20):
            client.post(
                f"/prescriptions/{rx_id}/dose-logs",
                json={
                    "event": "taken",
                    "timestamp": _iso(datetime(2026, 1, 1, h, 0, tzinfo=timezone.utc)),
                },
            )
        r = client.get(
            f"/prescriptions/{rx_id}/dose-logs",
            params={
                "start": _iso(datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)),
                "end": _iso(datetime(2026, 1, 1, 16, 0, tzinfo=timezone.utc)),
            },
        )
        assert r.status_code == 200
        logs = r.json()
        assert len(logs) == 1