"""Dose adherence logging API endpoints (my build unit's routes)."""

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from medication_tracker.dose_log_service import DoseLogService
from medication_tracker.repository import PrescriptionNotFoundError


class DoseLogCreate(BaseModel):
    """Request schema for appending a dose log event."""

    event: str = Field(..., description="Adherence event: 'taken' or 'skipped'")
    timestamp: Optional[str] = Field(
        None, description="ISO 8601 timestamp with timezone; defaults to now (UTC)"
    )
    notes: Optional[str] = None

    @field_validator("event")
    @classmethod
    def validate_event(cls, v: str) -> str:
        if v not in ("taken", "skipped"):
            raise ValueError("event must be 'taken' or 'skipped'")
        return v


class DoseLogResponse(BaseModel):
    id: str
    prescription_id: str
    event: str
    timestamp: str
    notes: Optional[str] = None


class ErrorResponse(BaseModel):
    error: str


def create_dose_log_router(service: DoseLogService) -> APIRouter:
    """Build the dose adherence logging router."""
    router = APIRouter(tags=["dose-logs"])

    @router.post(
        "/prescriptions/{prescription_id}/dose-logs",
        response_model=DoseLogResponse,
        status_code=201,
    )
    def append_dose_log(prescription_id: str, data: DoseLogCreate):
        """Append a timestamped taken/skipped dose event to a prescription.

        Returns 201 with the created dose log (ISO 8601 timestamp).
        Returns 400 for an unknown event or malformed timestamp.
        Returns 404 if the prescription does not exist.
        Returns 409 if the prescription is discontinued/completed.
        """
        try:
            log = service.append_dose_log(
                prescription_id=prescription_id,
                event=data.event,
                timestamp=data.timestamp,
                notes=data.notes,
            )
        except PrescriptionNotFoundError:
            raise HTTPException(
                status_code=404, detail={"error": "prescription not found"}
            )
        except ValueError as e:
            message = str(e).lower()
            if "not found" in message:
                raise HTTPException(status_code=404, detail={"error": str(e)})
            if "status" in message or "discontinued" in message or "completed" in message:
                raise HTTPException(status_code=409, detail={"error": str(e)})
            raise HTTPException(status_code=400, detail={"error": str(e)})
        return DoseLogResponse(**log.to_dict())

    @router.get(
        "/prescriptions/{prescription_id}/dose-logs",
        response_model=List[DoseLogResponse],
    )
    def get_dose_logs(
        prescription_id: str,
        start_date: Optional[str] = Query(None, description="Inclusive lower bound (ISO 8601)"),
        end_date: Optional[str] = Query(None, description="Inclusive upper bound (ISO 8601)"),
    ):
        """Return adherence history for a prescription ordered by timestamp ascending.

        Optional `start_date` / `end_date` query params filter the date range.
        Returns 404 if the prescription does not exist.
        """
        try:
            history = service.get_adherence_history(
                prescription_id=prescription_id,
                start_date=start_date,
                end_date=end_date,
            )
        except PrescriptionNotFoundError:
            raise HTTPException(
                status_code=404, detail={"error": "prescription not found"}
            )
        except ValueError as e:
            raise HTTPException(status_code=404, detail={"error": str(e)})
        return [DoseLogResponse(**log.to_dict()) for log in history]

    return router