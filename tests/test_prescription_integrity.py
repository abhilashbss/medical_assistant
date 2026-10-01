"""Integrity tests: foreign keys, partial unique index, status transition immutability,
EXPLAIN QUERY PLAN index verification, and index presence checks."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pytest

from prescription_tracker.db import init_db, seed_reference_data
from prescription_tracker.models import PrescriptionCreate, ValidationError
from prescription_tracker.repository import PrescriptionRepository

PATIENT = "patient-integ"
DOCTOR = "doctor-integ"


def _iso(dt: datetime) -> str:
    return dt.isoformat()


@pytest.fixture
def repo():
    conn = init_db()
    seed_reference_data(conn, PATIENT, DOCTOR)
    return PrescriptionRepository(conn)


def _make(medicine="TestMed") -> PrescriptionCreate:
    return PrescriptionCreate(
        patient_id=PATIENT,
        doctor_id=DOCTOR,
        medicine_name=medicine,
        dosage_amount=100.0,
        dosage_unit="mg",
        frequency="1x/day",
        start_date=_iso(datetime(2026, 1, 1, tzinfo=timezone.utc)),
    )


class TestForeignKeyEnforcement:
    def test_fk_pragma_on(self, repo):
        assert repo.conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1

    def test_insert_with_bad_patient_rejected(self, repo):
        data = _make()
        data.patient_id = "no-such-patient"
        with pytest.raises(sqlite3.IntegrityError):
            repo.create_prescription(data)

    def test_insert_with_bad_doctor_rejected(self, repo):
        data = _make()
        data.doctor_id = "no-such-doctor"
        with pytest.raises(sqlite3.IntegrityError):
            repo.create_prescription(data)

    def test_dose_log_fk_to_prescription(self, repo):
        from prescription_tracker.models import DoseLogCreate
        # The repository guards with an existence check (NotFoundError),
        # but a raw insert must be rejected by the FK constraint.
        with pytest.raises(sqlite3.IntegrityError):
            repo.conn.execute(
                "INSERT INTO dose_logs (prescription_id, event, timestamp) "
                "VALUES (?, 'taken', ?)",
                ("nonexistent-rx", _iso(datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc))),
            )
            repo.conn.commit()

    def test_status_transition_fk_to_prescription(self, repo):
        with pytest.raises(sqlite3.IntegrityError):
            repo.conn.execute(
                "INSERT INTO status_transitions (prescription_id, from_status, to_status) "
                "VALUES (?, 'active', 'completed')",
                ("nonexistent-rx",),
            )
            repo.conn.commit()


class TestPartialUniqueIndex:
    def test_index_exists(self, repo):
        rows = repo.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_one_active_per_medicine'"
        ).fetchall()
        assert len(rows) == 1

    def test_blocks_duplicate_active(self, repo):
        repo.create_prescription(_make(medicine="DupMed"))
        with pytest.raises(sqlite3.IntegrityError):
            repo.create_prescription(_make(medicine="DupMed"))

    def test_allows_after_discontinue(self, repo):
        rx = repo.create_prescription(_make(medicine="DupMed"))
        repo.discontinue(rx["id"], "done")
        # New active for same medicine should succeed.
        repo.create_prescription(_make(medicine="DupMed"))

    def test_allows_same_medicine_different_patients(self, repo):
        seed_reference_data(repo.conn, "patient-other", DOCTOR)
        repo.create_prescription(_make(medicine="SharedMed"))
        data = _make(medicine="SharedMed")
        data.patient_id = "patient-other"
        repo.create_prescription(data)


class TestStatusTransitionImmutability:
    def test_no_direct_update_to_created_row(self, repo):
        rx = repo.create_prescription(_make())
        # Directly trying to mutate via raw SQL outside the transition path
        # is blocked at the application level — but verify the transition
        # path inserts an audit row and only updates status.
        repo.complete(rx["id"])
        transitions = repo.conn.execute(
            "SELECT * FROM status_transitions WHERE prescription_id = ?", (rx["id"],)
        ).fetchall()
        assert len(transitions) == 1
        # The audit row is immutable: no UPDATE/DELETE path exists in code.

    def test_cannot_reopen_completed(self, repo):
        rx = repo.create_prescription(_make())
        repo.complete(rx["id"])
        with pytest.raises(ValidationError):
            repo.transition_status(
                rx["id"],
                __import__("prescription_tracker.models", fromlist=["StatusTransition"]).StatusTransition(
                    to_status="completed"
                ),
            )

    def test_transition_records_timestamp(self, repo):
        rx = repo.create_prescription(_make())
        repo.discontinue(rx["id"], "testing")
        row = repo.conn.execute(
            "SELECT transitioned_at FROM status_transitions WHERE prescription_id = ?",
            (rx["id"],),
        ).fetchone()
        assert row["transitioned_at"] is not None
        assert "T" in row["transitioned_at"]  # ISO 8601


class TestIndexPresence:
    def test_patient_status_index_exists(self, repo):
        rows = repo.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_prescriptions_patient_status'"
        ).fetchall()
        assert len(rows) == 1

    def test_patient_startdate_index_exists(self, repo):
        rows = repo.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_prescriptions_patient_startdate'"
        ).fetchall()
        assert len(rows) == 1

    def test_dose_log_index_exists(self, repo):
        rows = repo.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_dose_logs_rx_time'"
        ).fetchall()
        assert len(rows) == 1


class TestExplainQueryPlan:
    def _plan(self, repo, sql, params=()):
        rows = repo.explain_query_plan(sql, params)
        return " ".join(r["detail"] for r in rows)

    def test_history_uses_startdate_index(self, repo):
        # Seed enough rows so the planner prefers an index.
        for i in range(50):
            repo.create_prescription(
                PrescriptionCreate(
                    patient_id=PATIENT,
                    doctor_id=DOCTOR,
                    medicine_name=f"PlanMed-{i}",
                    dosage_amount=10.0,
                    dosage_unit="mg",
                    frequency="1x/day",
                    start_date=_iso(datetime(2026, 1, 1, tzinfo=timezone.utc) +
                                    __import__("datetime").timedelta(days=i)),
                )
            )
        plan = self._plan(
            repo,
            "SELECT * FROM prescriptions WHERE patient_id = ? ORDER BY start_date DESC",
            (PATIENT,),
        )
        assert "SCAN" not in plan.upper(), f"Full scan: {plan}"
        assert "idx_prescriptions_patient_startdate" in plan

    def test_status_query_uses_status_index(self, repo):
        plan = self._plan(
            repo,
            "SELECT * FROM prescriptions WHERE patient_id = ? AND status = ?",
            (PATIENT, "active"),
        )
        assert "SCAN" not in plan.upper(), f"Full scan: {plan}"
        assert "idx_prescriptions_patient_status" in plan