"""Data-access layer: parameterized SQL against SQLite.

All queries use parameterized SQL — no string interpolation — to prevent
SQL injection. Prescription rows are immutable after creation; only
explicit status transitions (complete / discontinue) mutate status, and
those insert timestamped audit rows into status_transitions.
"""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from .models import (
    DoseLogCreate,
    PrescriptionCreate,
    StatusTransition,
    ValidationError,
)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


class NotFoundError(Exception):
    pass


class PrescriptionRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    # ------------------------------------------------------------------ create
    def create_prescription(self, data: PrescriptionCreate) -> dict[str, Any]:
        data.validate()
        rx_id = _new_id()
        self.conn.execute(
            """
            INSERT INTO prescriptions
                (id, patient_id, doctor_id, medicine_name,
                 dosage_amount, dosage_unit, frequency,
                 start_date, end_date, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
            """,
            (
                rx_id,
                data.patient_id,
                data.doctor_id,
                data.medicine_name,
                data.dosage_amount,
                data.dosage_unit,
                data.frequency,
                data.start_date,
                data.end_date,
            ),
        )
        self.conn.commit()
        return self.get_prescription(rx_id)

    # ------------------------------------------------------------------ read
    def get_prescription(self, rx_id: str) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT * FROM prescriptions WHERE id = ?", (rx_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"prescription {rx_id} not found")
        return dict(row)

    def list_by_patient(self, patient_id: str) -> dict[str, list[dict[str, Any]]]:
        """Return active and historical prescriptions, sorted by start_date DESC."""
        rows = self.conn.execute(
            """
            SELECT * FROM prescriptions
            WHERE patient_id = ?
            ORDER BY start_date DESC
            """,
            (patient_id,),
        ).fetchall()
        active = [dict(r) for r in rows if r["status"] == "active"]
        historical = [dict(r) for r in rows if r["status"] != "active"]
        return {"active": active, "historical": historical}

    def list_history_by_patient(self, patient_id: str) -> list[dict[str, Any]]:
        """Full prescription history sorted by start_date DESC."""
        rows = self.conn.execute(
            """
            SELECT * FROM prescriptions
            WHERE patient_id = ?
            ORDER BY start_date DESC
            """,
            (patient_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def list_by_patient_and_status(
        self, patient_id: str, status: str
    ) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT * FROM prescriptions
            WHERE patient_id = ? AND status = ?
            ORDER BY start_date DESC
            """,
            (patient_id, status),
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------ transitions
    def transition_status(
        self, rx_id: str, transition: StatusTransition
    ) -> dict[str, Any]:
        transition.validate()
        row = self.conn.execute(
            "SELECT status FROM prescriptions WHERE id = ?", (rx_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"prescription {rx_id} not found")
        from_status = row["status"]
        to_status = transition.to_status

        if from_status == to_status:
            raise ValidationError(
                {"to_status": f"prescription already {to_status}"}
            )
        if from_status != "active":
            raise ValidationError(
                {"to_status": f"cannot transition from {from_status} to {to_status}"}
            )

        self.conn.execute("BEGIN")
        try:
            self.conn.execute(
                "UPDATE prescriptions SET status = ? WHERE id = ?",
                (to_status, rx_id),
            )
            self.conn.execute(
                """
                INSERT INTO status_transitions
                    (prescription_id, from_status, to_status, reason)
                VALUES (?, ?, ?, ?)
                """,
                (rx_id, from_status, to_status, transition.reason),
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        return self.get_prescription(rx_id)

    def complete(self, rx_id: str) -> dict[str, Any]:
        return self.transition_status(rx_id, StatusTransition(to_status="completed"))

    def discontinue(self, rx_id: str, reason: str) -> dict[str, Any]:
        return self.transition_status(
            rx_id, StatusTransition(to_status="discontinued", reason=reason)
        )

    # ------------------------------------------------------------------ dose logs
    def add_dose_log(self, data: DoseLogCreate) -> dict[str, Any]:
        data.validate()
        rx = self.conn.execute(
            "SELECT status FROM prescriptions WHERE id = ?",
            (data.prescription_id,),
        ).fetchone()
        if rx is None:
            raise NotFoundError(f"prescription {data.prescription_id} not found")
        if rx["status"] != "active":
            raise ValidationError(
                {"prescription_id": "cannot log doses for a non-active prescription"}
            )
        cur = self.conn.execute(
            """
            INSERT INTO dose_logs (prescription_id, event, timestamp, notes)
            VALUES (?, ?, ?, ?)
            """,
            (
                data.prescription_id,
                data.event,
                data.timestamp,
                data.notes,
            ),
        )
        self.conn.commit()
        log_id = cur.lastrowid
        row = self.conn.execute(
            "SELECT * FROM dose_logs WHERE id = ?", (log_id,)
        ).fetchone()
        return dict(row)

    def get_dose_logs(
        self,
        prescription_id: str,
        start_ts: Optional[str] = None,
        end_ts: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Dose logs for a prescription ordered by timestamp ascending,
        optionally filtered by ISO 8601 date range."""
        if start_ts and end_ts:
            rows = self.conn.execute(
                """
                SELECT * FROM dose_logs
                WHERE prescription_id = ? AND timestamp >= ? AND timestamp <= ?
                ORDER BY timestamp ASC
                """,
                (prescription_id, start_ts, end_ts),
            ).fetchall()
        elif start_ts:
            rows = self.conn.execute(
                """
                SELECT * FROM dose_logs
                WHERE prescription_id = ? AND timestamp >= ?
                ORDER BY timestamp ASC
                """,
                (prescription_id, start_ts),
            ).fetchall()
        elif end_ts:
            rows = self.conn.execute(
                """
                SELECT * FROM dose_logs
                WHERE prescription_id = ? AND timestamp <= ?
                ORDER BY timestamp ASC
                """,
                (prescription_id, end_ts),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """
                SELECT * FROM dose_logs
                WHERE prescription_id = ?
                ORDER BY timestamp ASC
                """,
                (prescription_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------ query plan
    def explain_query_plan(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        """Return EXPLAIN QUERY PLAN rows for a query."""
        rows = self.conn.execute("EXPLAIN QUERY PLAN " + sql, params).fetchall()
        return [dict(r) for r in rows]

    def _plan_detail(self, sql: str, params: tuple = ()) -> str:
        """Concatenate EXPLAIN QUERY PLAN detail lines into one string."""
        return " ".join(r["detail"] for r in self.explain_query_plan(sql, params))

    def plan_history_by_patient(self, patient_id: str) -> str:
        """Query plan for patient history ordered by start_date DESC."""
        return self._plan_detail(
            "SELECT * FROM prescriptions WHERE patient_id = ? ORDER BY start_date DESC",
            (patient_id,),
        )

    def plan_by_patient_and_status(self, patient_id: str, status: str) -> str:
        """Query plan for filtering by patient_id and status."""
        return self._plan_detail(
            "SELECT * FROM prescriptions WHERE patient_id = ? AND status = ?",
            (patient_id, status),
        )

    def plan_dose_logs(self, prescription_id: str) -> str:
        """Query plan for dose logs ordered by timestamp ascending."""
        return self._plan_detail(
            "SELECT * FROM dose_logs WHERE prescription_id = ? ORDER BY timestamp ASC",
            (prescription_id,),
        )

    def uses_full_scan(self, plan: str) -> bool:
        """True if the plan text indicates a full-table scan."""
        return "SCAN" in plan.upper() and "USING INDEX" not in plan.upper()