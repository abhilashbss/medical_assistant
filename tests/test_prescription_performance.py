"""Performance benchmark suite for single-patient workloads.

Asserts every prescription tracker endpoint completes under 500ms with a
single-patient workload of 500+ prescriptions and 5000+ dose_logs. Covers
both the repository layer and the FastAPI HTTP endpoints so the 500ms SLO
is verified end-to-end.
"""
from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timedelta, timezone

import pytest

from tests.asgi_client import ASGIClient
from prescription_tracker.app import app
from prescription_tracker.db import init_db, seed_reference_data
from prescription_tracker.models import DoseLogCreate, PrescriptionCreate
from prescription_tracker.repository import PrescriptionRepository

PATIENT = "patient-perf"
DOCTOR = "doctor-perf"
LATENCY_LIMIT_MS = 500
NUM_PRESCRIPTIONS = 600
NUM_DOSE_LOGS = 6000


def _iso(dt: datetime) -> str:
    return dt.isoformat()


@pytest.fixture(scope="module")
def seeded_repo():
    """Seed a database with 600 prescriptions (most discontinued/completed) and 6000 dose logs."""
    conn = init_db()
    seed_reference_data(conn, PATIENT, DOCTOR)
    repo = PrescriptionRepository(conn)

    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    # Create 600 prescriptions. Only the last one stays active to keep the
    # partial unique index happy (one active per medicine). We use unique
    # medicine names so all are active simultaneously... but the partial index
    # only blocks duplicates for the SAME medicine. So unique names are fine.
    rx_ids: list[str] = []
    for i in range(NUM_PRESCRIPTIONS):
        rx = repo.create_prescription(
            PrescriptionCreate(
                patient_id=PATIENT,
                doctor_id=DOCTOR,
                medicine_name=f"Med-{i:04d}",
                dosage_amount=100.0 + i,
                dosage_unit="mg",
                frequency="1x/day",
                start_date=_iso(base + timedelta(days=i)),
            )
        )
        rx_ids.append(rx["id"])

    # Transition most of them to completed/discontinued so history is rich.
    for i, rx_id in enumerate(rx_ids[:-1]):
        if i % 2 == 0:
            repo.complete(rx_id)
        else:
            repo.discontinue(rx_id, f"reason-{i}")

    # Add 6000 dose logs to the one remaining active prescription.
    active_rx = rx_ids[-1]
    for j in range(NUM_DOSE_LOGS):
        repo.add_dose_log(
            DoseLogCreate(
                prescription_id=active_rx,
                event="taken" if j % 3 != 0 else "skipped",
                timestamp=_iso(base + timedelta(minutes=j * 30)),
            )
        )
    return repo, active_rx


def _assert_under_limit(elapsed_ms: float, label: str):
    assert elapsed_ms < LATENCY_LIMIT_MS, (
        f"{label} took {elapsed_ms:.1f}ms (limit {LATENCY_LIMIT_MS}ms)"
    )


class TestEndpointLatency:
    def test_create_under_500ms(self, seeded_repo):
        repo, _ = seeded_repo
        start = time.perf_counter()
        repo.create_prescription(
            PrescriptionCreate(
                patient_id=PATIENT,
                doctor_id=DOCTOR,
                medicine_name="PerfTestNew",
                dosage_amount=200.0,
                dosage_unit="mg",
                frequency="2x/day",
                start_date=_iso(datetime(2026, 1, 1, tzinfo=timezone.utc)),
            )
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        _assert_under_limit(elapsed_ms, "create_prescription")

    def test_retrieve_by_id_under_500ms(self, seeded_repo):
        repo, active_rx = seeded_repo
        start = time.perf_counter()
        repo.get_prescription(active_rx)
        elapsed_ms = (time.perf_counter() - start) * 1000
        _assert_under_limit(elapsed_ms, "get_prescription")

    def test_list_by_patient_under_500ms(self, seeded_repo):
        repo, _ = seeded_repo
        start = time.perf_counter()
        result = repo.list_by_patient(PATIENT)
        elapsed_ms = (time.perf_counter() - start) * 1000
        _assert_under_limit(elapsed_ms, "list_by_patient")
        assert len(result["active"]) + len(result["historical"]) >= NUM_PRESCRIPTIONS

    def test_history_by_patient_under_500ms(self, seeded_repo):
        repo, _ = seeded_repo
        start = time.perf_counter()
        history = repo.list_history_by_patient(PATIENT)
        elapsed_ms = (time.perf_counter() - start) * 1000
        _assert_under_limit(elapsed_ms, "list_history_by_patient")
        assert len(history) >= NUM_PRESCRIPTIONS
        # Verify sorted descending.
        dates = [h["start_date"] for h in history]
        assert dates == sorted(dates, reverse=True)

    def test_list_by_patient_and_status_under_500ms(self, seeded_repo):
        repo, _ = seeded_repo
        start = time.perf_counter()
        active = repo.list_by_patient_and_status(PATIENT, "active")
        elapsed_ms = (time.perf_counter() - start) * 1000
        _assert_under_limit(elapsed_ms, "list_by_patient_and_status")
        assert len(active) >= 1

    def test_discontinue_under_500ms(self, seeded_repo):
        repo, _ = seeded_repo
        # Create a fresh rx to discontinue.
        rx = repo.create_prescription(
            PrescriptionCreate(
                patient_id=PATIENT,
                doctor_id=DOCTOR,
                medicine_name="PerfDiscontinue",
                dosage_amount=50.0,
                dosage_unit="mg",
                frequency="1x/day",
                start_date=_iso(datetime(2026, 6, 1, tzinfo=timezone.utc)),
            )
        )
        start = time.perf_counter()
        repo.discontinue(rx["id"], "benchmark")
        elapsed_ms = (time.perf_counter() - start) * 1000
        _assert_under_limit(elapsed_ms, "discontinue")

    def test_complete_under_500ms(self, seeded_repo):
        repo, _ = seeded_repo
        rx = repo.create_prescription(
            PrescriptionCreate(
                patient_id=PATIENT,
                doctor_id=DOCTOR,
                medicine_name="PerfComplete",
                dosage_amount=75.0,
                dosage_unit="mg",
                frequency="1x/day",
                start_date=_iso(datetime(2026, 7, 1, tzinfo=timezone.utc)),
            )
        )
        start = time.perf_counter()
        repo.complete(rx["id"])
        elapsed_ms = (time.perf_counter() - start) * 1000
        _assert_under_limit(elapsed_ms, "complete")

    def test_add_dose_log_under_500ms(self, seeded_repo):
        repo, active_rx = seeded_repo
        start = time.perf_counter()
        repo.add_dose_log(
            DoseLogCreate(
                prescription_id=active_rx,
                event="taken",
                timestamp=_iso(datetime(2026, 9, 1, 8, 0, tzinfo=timezone.utc)),
            )
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        _assert_under_limit(elapsed_ms, "add_dose_log")

    def test_get_dose_logs_under_500ms(self, seeded_repo):
        repo, active_rx = seeded_repo
        start = time.perf_counter()
        logs = repo.get_dose_logs(active_rx)
        elapsed_ms = (time.perf_counter() - start) * 1000
        _assert_under_limit(elapsed_ms, "get_dose_logs")
        assert len(logs) >= NUM_DOSE_LOGS


class TestExplainQueryPlan:
    """Verify single-patient read paths use indexes, not full table scans."""

    def _plan(self, repo, sql, params=()):
        rows = repo.explain_query_plan(sql, params)
        plan_text = " ".join(r["detail"] for r in rows)
        return plan_text

    def test_history_uses_index(self, seeded_repo):
        repo, _ = seeded_repo
        plan = self._plan(
            repo,
            "SELECT * FROM prescriptions WHERE patient_id = ? ORDER BY start_date DESC",
            (PATIENT,),
        )
        assert "SCAN" not in plan.upper(), f"Full table scan detected: {plan}"
        assert "idx_prescriptions_patient_startdate" in plan or "SEARCH" in plan.upper()

    def test_status_filter_uses_index(self, seeded_repo):
        repo, _ = seeded_repo
        plan = self._plan(
            repo,
            "SELECT * FROM prescriptions WHERE patient_id = ? AND status = ?",
            (PATIENT, "active"),
        )
        assert "SCAN" not in plan.upper(), f"Full table scan detected: {plan}"
        assert "idx_prescriptions_patient_status" in plan or "SEARCH" in plan.upper()

    def test_dose_logs_use_index(self, seeded_repo):
        repo, active_rx = seeded_repo
        plan = self._plan(
            repo,
            "SELECT * FROM dose_logs WHERE prescription_id = ? ORDER BY timestamp ASC",
            (active_rx,),
        )
        assert "SCAN" not in plan.upper(), f"Full table scan detected: {plan}"
        assert "idx_dose_logs_rx_time" in plan or "SEARCH" in plan.upper()


@pytest.fixture(scope="module")
def api_client(seeded_repo):
    """Point the FastAPI app at the seeded repository's connection."""
    repo, _ = seeded_repo
    import prescription_tracker.app as appmod

    appmod._conn = repo.conn
    appmod._repo = repo
    return ASGIClient(app)


class TestEndpointLatencyHTTP:
    """End-to-end HTTP latency: every endpoint under 500ms for a single patient."""

    def test_http_create_under_500ms(self, api_client):
        start = time.perf_counter()
        r = api_client.post(
            f"/patients/{PATIENT}/prescriptions",
            json={
                "doctor_id": DOCTOR,
                "medicine_name": "HttpCreate",
                "dosage_amount": 300.0,
                "dosage_unit": "mg",
                "frequency": "1x/day",
                "start_date": _iso(datetime(2026, 8, 1, tzinfo=timezone.utc)),
            },
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert r.status_code == 200
        _assert_under_limit(elapsed_ms, "HTTP create")

    def test_http_retrieve_under_500ms(self, api_client, seeded_repo):
        _, active_rx = seeded_repo
        start = time.perf_counter()
        r = api_client.get(f"/prescriptions/{active_rx}")
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert r.status_code == 200
        _assert_under_limit(elapsed_ms, "HTTP retrieve")

    def test_http_list_by_patient_under_500ms(self, api_client):
        start = time.perf_counter()
        r = api_client.get(f"/patients/{PATIENT}/prescriptions")
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert r.status_code == 200
        _assert_under_limit(elapsed_ms, "HTTP list_by_patient")

    def test_http_history_under_500ms(self, api_client):
        start = time.perf_counter()
        r = api_client.get(f"/patients/{PATIENT}/prescriptions")
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert r.status_code == 200
        _assert_under_limit(elapsed_ms, "HTTP history")

    def test_http_complete_under_500ms(self, api_client):
        rx = api_client.post(
            f"/patients/{PATIENT}/prescriptions",
            json={
                "doctor_id": DOCTOR,
                "medicine_name": "HttpComplete",
                "dosage_amount": 10.0,
                "dosage_unit": "mg",
                "frequency": "1x/day",
                "start_date": _iso(datetime(2026, 9, 1, tzinfo=timezone.utc)),
            },
        ).json()["id"]
        start = time.perf_counter()
        r = api_client.patch(f"/prescriptions/{rx}/complete")
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert r.status_code == 200
        _assert_under_limit(elapsed_ms, "HTTP complete")

    def test_http_discontinue_under_500ms(self, api_client):
        rx = api_client.post(
            f"/patients/{PATIENT}/prescriptions",
            json={
                "doctor_id": DOCTOR,
                "medicine_name": "HttpDiscontinue",
                "dosage_amount": 20.0,
                "dosage_unit": "mg",
                "frequency": "1x/day",
                "start_date": _iso(datetime(2026, 10, 1, tzinfo=timezone.utc)),
            },
        ).json()["id"]
        start = time.perf_counter()
        r = api_client.patch(
            f"/prescriptions/{rx}/discontinue", json={"reason": "http bench"}
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert r.status_code == 200
        _assert_under_limit(elapsed_ms, "HTTP discontinue")

    def test_http_add_dose_log_under_500ms(self, api_client, seeded_repo):
        _, active_rx = seeded_repo
        start = time.perf_counter()
        r = api_client.post(
            f"/prescriptions/{active_rx}/dose-logs",
            json={
                "event": "taken",
                "timestamp": _iso(datetime(2026, 9, 1, 8, 0, tzinfo=timezone.utc)),
            },
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert r.status_code == 200
        _assert_under_limit(elapsed_ms, "HTTP add_dose_log")

    def test_http_get_dose_logs_under_500ms(self, api_client, seeded_repo):
        _, active_rx = seeded_repo
        start = time.perf_counter()
        r = api_client.get(f"/prescriptions/{active_rx}/dose-logs")
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert r.status_code == 200
        _assert_under_limit(elapsed_ms, "HTTP get_dose_logs")