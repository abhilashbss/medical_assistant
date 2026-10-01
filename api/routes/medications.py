"""Medication CRUD API endpoints."""

from datetime import date
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class MedicationCreate(BaseModel):
    """Request schema for creating a medication."""

    name: str = Field(..., description="Medication name", min_length=1)
    dosage: str = Field(..., description="Dosage amount and unit, e.g., '500mg'", min_length=1)
    frequency: str = Field(..., description="How often to take, e.g., 'twice daily'", min_length=1)
    start_date: Optional[date] = Field(None, description="Treatment start date")
    end_date: Optional[date] = Field(None, description="Treatment end date")
    status: str = Field("active", description="Status: 'active' or 'completed'")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate name is not empty or whitespace only."""
        if not v or not v.strip():
            raise ValueError("name must be a non-empty string")
        return v.strip()

    @field_validator("dosage")
    @classmethod
    def validate_dosage(cls, v: str) -> str:
        """Validate dosage is not empty or whitespace only."""
        if not v or not v.strip():
            raise ValueError("dosage must be a non-empty string")
        return v.strip()

    @field_validator("frequency")
    @classmethod
    def validate_frequency(cls, v: str) -> str:
        """Validate frequency is not empty or whitespace only."""
        if not v or not v.strip():
            raise ValueError("frequency must be a non-empty string")
        return v.strip()

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        """Validate status is either 'active' or 'completed'."""
        if v not in ("active", "completed"):
            raise ValueError("status must be 'active' or 'completed'")
        return v


class MedicationUpdate(BaseModel):
    """Request schema for updating a medication."""

    name: Optional[str] = Field(None, description="Medication name", min_length=1)
    dosage: Optional[str] = Field(None, description="Dosage amount and unit", min_length=1)
    frequency: Optional[str] = Field(None, description="How often to take", min_length=1)
    start_date: Optional[date] = Field(None, description="Treatment start date")
    end_date: Optional[date] = Field(None, description="Treatment end date")
    status: Optional[str] = Field(None, description="Status: 'active' or 'completed'")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        """Validate name is not empty or whitespace only."""
        if v is not None and (not v or not v.strip()):
            raise ValueError("name must be a non-empty string")
        return v.strip() if v else v

    @field_validator("dosage")
    @classmethod
    def validate_dosage(cls, v: Optional[str]) -> Optional[str]:
        """Validate dosage is not empty or whitespace only."""
        if v is not None and (not v or not v.strip()):
            raise ValueError("dosage must be a non-empty string")
        return v.strip() if v else v

    @field_validator("frequency")
    @classmethod
    def validate_frequency(cls, v: Optional[str]) -> Optional[str]:
<<<<<<< HEAD
        """Validate frequency is not empty or whitespace only."""
=======
>>>>>>> 9105369 (runctl: build runctl/build-09d3fc65 (pass))
        if v is not None and (not v or not v.strip()):
            raise ValueError("frequency must be a non-empty string")
        return v.strip() if v else v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
<<<<<<< HEAD
        """Validate status is either 'active' or 'completed'."""
=======
>>>>>>> 9105369 (runctl: build runctl/build-09d3fc65 (pass))
        if v is not None and v not in ("active", "completed"):
            raise ValueError("status must be 'active' or 'completed'")
        return v


class MedicationResponse(BaseModel):
    """Response schema for medication data."""

    id: str
    name: str
    dosage: str
    frequency: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    status: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ErrorResponse(BaseModel):
    """Response schema for error messages."""

    error: str
    details: Optional[List[str]] = None


class MedicationAPI:
    """Medication API endpoints."""

    def __init__(self, repository):
<<<<<<< HEAD
        """Initialize API with repository.

        Args:
            repository: MedicationRepository instance
        """
        self.repository = repository

    def create(self, data: MedicationCreate) -> tuple[MedicationResponse, int]:
        """Create a new medication.

        Args:
            data: MedicationCreate request data

        Returns:
            Tuple of (MedicationResponse, status_code)

        Raises:
            ValueError: If validation fails
        """
=======
        self.repository = repository

    def create(self, data: MedicationCreate) -> tuple:
        """Create a new medication."""
>>>>>>> 9105369 (runctl: build runctl/build-09d3fc65 (pass))
        from medication_tracker.models import Medication, MedicationStatus

        medication = Medication(
            name=data.name,
            dosage=data.dosage,
            frequency=data.frequency,
            start_date=data.start_date,
            end_date=data.end_date,
            status=MedicationStatus(data.status),
        )

        created = self.repository.create(medication)
        return MedicationResponse(**created.to_dict()), 201

<<<<<<< HEAD
    def get_all(self, status: Optional[str] = None) -> tuple[List[MedicationResponse], int]:
        """Get all medications, optionally filtered by status.

        Args:
            status: Optional status filter ('active' or 'completed')

        Returns:
            Tuple of (list of MedicationResponse, status_code)
        """
=======
    def get_all(self, status: Optional[str] = None) -> tuple:
        """Get all medications, optionally filtered by status."""
>>>>>>> 9105369 (runctl: build runctl/build-09d3fc65 (pass))
        from medication_tracker.models import MedicationStatus

        if status:
            medications = self.repository.get_all(status=MedicationStatus(status))
        else:
            medications = self.repository.get_all()

        return [MedicationResponse(**med.to_dict()) for med in medications], 200

<<<<<<< HEAD
    def get_by_id(self, medication_id: str) -> tuple[MedicationResponse, int]:
        """Get a medication by ID.

        Args:
            medication_id: UUID string of medication

        Returns:
            Tuple of (MedicationResponse, status_code)

        Raises:
            ValueError: If medication not found
        """
=======
    def get_by_id(self, medication_id: str) -> tuple:
        """Get a medication by ID."""
>>>>>>> 9105369 (runctl: build runctl/build-09d3fc65 (pass))
        try:
            uuid = UUID(medication_id)
        except ValueError:
            raise ValueError(f"Invalid medication ID format: {medication_id}")

        medication = self.repository.get_by_id(uuid)
        if medication is None:
            raise ValueError(f"Medication with ID {medication_id} not found")

        return MedicationResponse(**medication.to_dict()), 200

<<<<<<< HEAD
    def update(self, medication_id: str, data: MedicationUpdate) -> tuple[MedicationResponse, int]:
        """Update an existing medication.

        Args:
            medication_id: UUID string of medication
            data: MedicationUpdate request data

        Returns:
            Tuple of (MedicationResponse, status_code)

        Raises:
            ValueError: If medication not found or validation fails
        """
=======
    def update(self, medication_id: str, data: MedicationUpdate) -> tuple:
        """Update an existing medication."""
>>>>>>> 9105369 (runctl: build runctl/build-09d3fc65 (pass))
        try:
            uuid = UUID(medication_id)
        except ValueError:
            raise ValueError(f"Invalid medication ID format: {medication_id}")

        medication = self.repository.get_by_id(uuid)
        if medication is None:
            raise ValueError(f"Medication with ID {medication_id} not found")

<<<<<<< HEAD
        # Update fields if provided
=======
>>>>>>> 9105369 (runctl: build runctl/build-09d3fc65 (pass))
        if data.name is not None:
            medication.name = data.name
        if data.dosage is not None:
            medication.dosage = data.dosage
        if data.frequency is not None:
            medication.frequency = data.frequency
        if data.start_date is not None:
            medication.start_date = data.start_date
        if data.end_date is not None:
            medication.end_date = data.end_date
        if data.status is not None:
            from medication_tracker.models import MedicationStatus
            medication.status = MedicationStatus(data.status)

        updated = self.repository.update(medication)
        if updated is None:
            raise ValueError(f"Failed to update medication with ID {medication_id}")

        return MedicationResponse(**updated.to_dict()), 200

<<<<<<< HEAD
    def delete(self, medication_id: str) -> tuple[None, int]:
        """Delete a medication.

        Args:
            medication_id: UUID string of medication

        Returns:
            Tuple of (None, status_code)

        Raises:
            ValueError: If medication not found
        """
=======
    def delete(self, medication_id: str) -> tuple:
        """Delete a medication."""
>>>>>>> 9105369 (runctl: build runctl/build-09d3fc65 (pass))
        try:
            uuid = UUID(medication_id)
        except ValueError:
            raise ValueError(f"Invalid medication ID format: {medication_id}")

        deleted = self.repository.delete(uuid)
        if not deleted:
            raise ValueError(f"Medication with ID {medication_id} not found")

<<<<<<< HEAD
        return None, 204
=======
        return None, 204
>>>>>>> 9105369 (runctl: build runctl/build-09d3fc65 (pass))
