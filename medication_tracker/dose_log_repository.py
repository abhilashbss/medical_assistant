"""Dose log repository: append-only dose adherence records."""

from typing import List, Optional

from .database import Database
from .models import DoseLog


class PrescriptionDoseLogRepository:
    """Repository for the append-only dose_logs table.

    Only INSERTs are permitted (no UPDATE path). History is returned ordered
    by timestamp ascending with an optional date-range filter.
    """

    def __init__(self, database: Database):
        self.db = database

    def append(self, log: DoseLog) -> DoseLog:
        """Append a dose log row. This is the only write path; rows are never
        updated or back-dated-edited after being inserted.
        """
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO dose_logs (id, prescription_id, event, timestamp, notes)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    log.id,
                    log.prescription_id,
                    log.event.value,
                    log.timestamp,
                    log.notes,
                ),
            )
        return log

    def get_history(
        self,
        prescription_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[DoseLog]:
        """Return dose logs for a prescription ordered by timestamp ascending.

        Args:
            prescription_id: Prescription to filter by.
            start_date: Optional inclusive lower bound on timestamp (ISO 8601).
            end_date: Optional inclusive upper bound on timestamp (ISO 8601).
        """
        query = "SELECT * FROM dose_logs WHERE prescription_id = ?"
        params: list = [prescription_id]
        if start_date is not None:
            query += " AND timestamp >= ?"
            params.append(start_date)
        if end_date is not None:
            query += " AND timestamp <= ?"
            params.append(end_date)
        query += " ORDER BY timestamp ASC"
        cursor = self.db.execute(query, tuple(params))
        return [DoseLog.from_row(row) for row in cursor.fetchall()]

    def count(self, prescription_id: str) -> int:
        """Return the number of dose log rows for a prescription."""
        cursor = self.db.execute(
            "SELECT COUNT(*) AS n FROM dose_logs WHERE prescription_id = ?",
            (prescription_id,),
        )
        row = cursor.fetchone()
        return int(row["n"]) if row is not None else 0