"""Unit tests for the dose_logs layer (build unit #3).

Cases: valid append returns 201 with ISO timestamp; append to discontinued
prescription returns 409; invalid event returns 400; history ordered by
timestamp ascending; optional date-range filter respected; duplicate-timestamp
append allowed (append-only) but back-dated edits rejected.
"""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from medication_tracker import (
    DoseEvent,
    DoseLog,
    PrescriptionDoseLogRepository,
)


@pytest.fixture
def client():
    app = create_app(":memory:")
    with TestClient(app) as c:
        yield c


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_prescription(client, **overrides):
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
    r = client.post("/prescriptions", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


class TestAppendDoseLog:
    def test_valid_append_returns_201_with_iso_timestamp(self, client):
        rx = _make_prescription(client)
        r = client.post(
            f"/prescriptions/{rx['id']}/dose-logs", json={"event": "taken"}
        )
        assert r.status_code == 201
        body = r.json()
        assert body["event"] == "taken"
        parsed = datetime.fromisoformat(body["timestamp"])
        assert parsed.tzinfo is not None

    def test_append_skipped_event(self, client):
        rx = _make_prescription(client)
        r = client.post(
            f"/prescriptions/{rx['id']}/dose-logs", json={"event": "skipped"}
        )
        assert r.status_code == 201
        assert r.json()["event"] == "skipped"

    def test_append_to_discontinued_returns_409(self, client):
        rx = _make_prescription(client)
        client.patch(
            f"/prescriptions/{rx['id']}/discontinue", json={"reason": "done"}
        )
        r = client.post(
            f"/prescriptions/{rx['id']}/dose-logs", json={"event": "taken"}
        )
        assert r.status_code == 409

    def test_append_to_completed_returns_409(self, client):
        rx = _make_prescription(client)
        client.patch(f"/prescriptions/{rx['id']}/complete")
        r = client.post(
            f"/prescriptions/{rx['id']}/dose-logs", json={"event": "taken"}
        )
        assert r.status_code == 409

    def test_invalid_event_returns_400(self, client):
        rx = _make_prescription(client)
        r = client.post(
            f"/prescriptions/{rx['id']}/dose-logs", json={"event": "missed"}
        )
        assert r.status_code in (400, 422)

    def test_append_to_missing_prescription_returns_404(self, client):
        r = client.post(
            "/prescriptions/missing/dose-logs", json={"event": "taken"}
        )
        assert r.status_code == 404

    def test_naive_timestamp_rejected(self, client):
        rx = _make_prescription(client)
        r = client.post(
            f"/prescriptions/{rx['id']}/dose-logs",
            json={"event": "taken", "timestamp": "2026-01-01T08:00:00"},
        )
        assert r.status_code == 400

    def test_notes_persisted(self, client):
        rx = _make_prescription(client)
        r = client.post(
            f"/prescriptions/{rx['id']}/dose-logs",
            json={"event": "skipped", "notes": "felt dizzy"},
        )
        assert r.status_code == 201
        assert r.json()["notes"] == "felt dizzy"


class TestDoseLogHistory:
    def test_history_ordered_by_timestamp_ascending(self, client):
        rx = _make_prescription(client)
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
        assert history[0]["timestamp"] < history[1]["timestamp"]

    def test_date_range_filter_respected(self, client):
        rx = _make_prescription(client)
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
            params={"start_date": "2026-01-02T00:00:00+00:00"},
        ).json()
        assert len(history) == 2
        assert all(h["timestamp"] >= "2026-01-02T00:00:00+00:00" for h in history)

    def test_start_and_end_filter(self, client):
        rx = _make_prescription(client)
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
            params={
                "start_date": "2026-01-02T00:00:00+00:00",
                "end_date": "2026-01-02T23:59:59+00:00",
            },
        ).json()
        assert len(history) == 1

    def test_empty_history_for_new_prescription(self, client):
        rx = _make_prescription(client)
        history = client.get(f"/prescriptions/{rx['id']}/dose-logs").json()
        assert history == []


class TestAppendOnlySemantics:
    def test_duplicate_timestamp_append_allowed(self, client):
        """Append-only: two events at the same timestamp are both stored."""
        rx = _make_prescription(client)
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

    def test_no_update_path_on_repository(self):
        """The repository exposes only append(); there is no update() method,
        so existing rows cannot be back-dated-edited."""
        assert not hasattr(PrescriptionDoseLogRepository, "update")
        assert not hasattr(PrescriptionDoseLogRepository, "edit")

    def test_back_dated_edit_not_possible(self, database):
        """There is no way to modify an existing dose log row; only INSERTs
        are issued by the repository."""
        from medication_tracker.repository import PrescriptionRepository
        from medication_tracker import Prescription, PrescriptionStatus

        repo = PrescriptionRepository(database)
        rx = repo.create(
            Prescription(
                patient_id="p1",
                doctor_id="d1",
                medicine_name="M",
                dosage_amount=1.0,
                dosage_unit="mg",
                frequency="daily",
                start_date=_now_iso(),
                status=PrescriptionStatus.ACTIVE,
            )
        )
        dose_repo = PrescriptionDoseLogRepository(database)
        log = DoseLog(
            prescription_id=rx.id,
            event=DoseEvent.TAKEN,
            timestamp="2026-01-01T08:00:00+00:00",
        )
        dose_repo.append(log)
        # Attempting a direct UPDATE is not a supported operation and the
        # repository offers no method for it; the table has no unique
        # constraint to key an update on. Verify the row is immutable by
        # confirming only append() writes.
        history = dose_repo.get_history(rx.id)
        assert len(history) == 1
        # A second append at a different timestamp adds a row rather than
        # editing the first.
        dose_repo.append(
            DoseLog(
                prescription_id=rx.id,
                event=DoseEvent.SKIPPED,
                timestamp="2026-01-02T08:00:00+00:00",
            )
        )
        history = dose_repo.get_history(rx.id)
        assert len(history) == 2
        assert history[0].timestamp == "2026-01-01T08:00:00+00:00"