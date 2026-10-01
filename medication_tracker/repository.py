"""Medication repository for database operations."""

import sqlite3
from datetime import datetime
from typing import List, Optional
from uuid import UUID, uuid4

from .database import Database
from .models import DoseRecord, Medication, MedicationStatus


class MedicationRepository:
    """Repository for medication CRUD operations."""

    def __init__(self, database: Database):
        """Initialize repository with database connection.

        Args:
            database: Database instance
        """
        self.db = database

    def create(self, medication: Medication) -> Medication:
        """Create a new medication record.

        Args:
            medication: Medication to create

        Returns:
            Created medication with generated ID and timestamps

        Raises:
            ValueError: If validation fails
        """
        now = datetime.now().isoformat()

        with self.db.transaction() as conn:
            cursor = conn.execute(
                """
                INSERT INTO medications (id, name, dosage, frequency, start_date, end_date, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(medication.id),
                    medication.name,
                    medication.dosage,
                    medication.frequency,
                    medication.start_date.isoformat() if medication.start_date else None,
                    medication.end_date.isoformat() if medication.end_date else None,
                    medication.status.value if isinstance(medication.status, MedicationStatus) else medication.status,
                    now,
                    now,
                ),
            )
            conn.commit()

        medication.created_at = datetime.fromisoformat(now)
        medication.updated_at = datetime.fromisoformat(now)
        return medication

    def get_by_id(self, medication_id: UUID) -> Optional[Medication]:
        """Get a medication by ID.

        Args:
            medication_id: UUID of medication to retrieve

        Returns:
            Medication if found, None otherwise
        """
        cursor = self.db.execute(
            "SELECT * FROM medications WHERE id = ?",
            (str(medication_id),)
        )
        row = cursor.fetchone()

        if row is None:
            return None

        return self._row_to_medication(row)

    def get_all(self, status: Optional[MedicationStatus] = None) -> List[Medication]:
        """Get all medications, optionally filtered by status.

        Args:
            status: Optional status filter

        Returns:
            List of medications sorted by created_at descending
        """
        if status:
            cursor = self.db.execute(
                "SELECT * FROM medications WHERE status = ? ORDER BY created_at DESC",
                (status.value,)
            )
        else:
            cursor = self.db.execute(
                "SELECT * FROM medications ORDER BY created_at DESC"
            )

        return [self._row_to_medication(row) for row in cursor.fetchall()]

    def update(self, medication: Medication) -> Optional[Medication]:
        """Update an existing medication.

        Args:
            medication: Medication with updated values

        Returns:
            Updated medication if found, None otherwise
        """
        now = datetime.now().isoformat()

        with self.db.transaction() as conn:
            cursor = conn.execute(
                """
                UPDATE medications
                SET name = ?, dosage = ?, frequency = ?, start_date = ?, end_date = ?,
                    status = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    medication.name,
                    medication.dosage,
                    medication.frequency,
                    medication.start_date.isoformat() if medication.start_date else None,
                    medication.end_date.isoformat() if medication.end_date else None,
                    medication.status.value if isinstance(medication.status, MedicationStatus) else medication.status,
                    now,
                    str(medication.id),
                ),
            )

            if cursor.rowcount == 0:
                return None

            conn.commit()

        medication.updated_at = datetime.fromisoformat(now)
        return medication

    def delete(self, medication_id: UUID) -> bool:
        """Delete a medication.

        Args:
            medication_id: UUID of medication to delete

        Returns:
            True if deleted, False if not found
        """
        with self.db.transaction() as conn:
            cursor = conn.execute(
                "DELETE FROM medications WHERE id = ?",
                (str(medication_id),)
            )
            conn.commit()
            return cursor.rowcount > 0

    def create_dose_record(self, dose: DoseRecord) -> DoseRecord:
        """Create a dose record for a medication.

        Args:
            dose: DoseRecord to create

        Returns:
            Created dose record
        """
        now = datetime.now().isoformat()

        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO dose_records (id, medication_id, date, timestamp, status)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    str(dose.id),
                    str(dose.medication_id),
                    dose.date.isoformat(),
                    dose.timestamp.isoformat() if dose.timestamp else now,
                    dose.status,
                ),
            )
            conn.commit()

        if dose.timestamp is None:
            dose.timestamp = datetime.fromisoformat(now)
        return dose

    def get_dose_records(self, medication_id: UUID, start_date: Optional[str] = None,
                         end_date: Optional[str] = None) -> List[DoseRecord]:
        """Get dose records for a medication.

        Args:
            medication_id: UUID of medication
            start_date: Optional start date filter (ISO format)
            end_date: Optional end date filter (ISO format)

        Returns:
            List of dose records
        """
        query = "SELECT * FROM dose_records WHERE medication_id = ?"
        params = [str(medication_id)]

        if start_date:
            query += " AND date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND date <= ?"
            params.append(end_date)

        query += " ORDER BY date DESC, timestamp DESC"

        cursor = self.db.execute(query, params)
        return [self._row_to_dose_record(row) for row in cursor.fetchall()]

    def _row_to_medication(self, row: sqlite3.Row) -> Medication:
        """Convert a database row to a Medication object."""
        from datetime import date

        status_str = row["status"]
        try:
            status = MedicationStatus(status_str)
        except ValueError:
            status = MedicationStatus.ACTIVE

        # Parse date strings from database
        start_date = None
        if row["start_date"]:
            try:
                start_date = date.fromisoformat(row["start_date"])
            except (ValueError, AttributeError):
                start_date = row["start_date"]

        end_date = None
        if row["end_date"]:
            try:
                end_date = date.fromisoformat(row["end_date"])
            except (ValueError, AttributeError):
                end_date = row["end_date"]

        return Medication(
            id=UUID(row["id"]),
            name=row["name"],
            dosage=row["dosage"],
            frequency=row["frequency"],
            start_date=start_date,
            end_date=end_date,
            status=status,
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
            updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None,
        )

    def _row_to_dose_record(self, row: sqlite3.Row) -> DoseRecord:
        """Convert a database row to a DoseRecord object."""
        from datetime import date

        return DoseRecord(
            id=UUID(row["id"]),
            medication_id=UUID(row["medication_id"]),
            date=date.fromisoformat(row["date"]),
            timestamp=datetime.fromisoformat(row["timestamp"]) if row["timestamp"] else None,
            status=row["status"],
        )
