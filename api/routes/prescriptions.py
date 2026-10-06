"""Prescription CRUD and lifecycle API endpoints."""

import sqlite3
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from medication_tracker.models import PrescriptionStatus
from medication_tracker.prescription_service import PrescriptionService
from medication_tracker.repository import PrescriptionNotFoundError


class PrescriptionCreate(BaseModel):
    """Request schema for creating a prescription."""

    patient_id: str = Field(..., min_length=1)
    doctor_id: str = Field(..., min_length=1)
    medicine_name: str = Field(..., min_length=1)
    dosage_amount: float = Field(..., gt=0)
    dosage_unit: str = Field(..., min_length=1)
    frequency: str = Field(..., min_length=1)
    start_date: str = Field(..., min_length=1)
    end_date: Optional[str] = None
    status: str = Field("active")

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in ("active", "completed", "discontinued"):
            raise ValueError("status must be 'active', 'completed', or 'discontinued'")
        return v


class DiscontinueRequest(BaseModel):
    """Request schema for discontinuing a prescription."""

    reason: str = Field(..., min_length=1)

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("reason must be a non-empty string")
        return v.strip()


class PrescriptionResponse(BaseModel):
    id: str
    patient_id: str
    doctor_id: str
    medicine_name: str
    dosage_amount: float
    dosage_unit: str
    frequency: str
    start_date: str
    end_date: Optional[str] = None
    status: str
    created_at: str


class StatusTransitionResponse(BaseModel):
    id: str
    prescription_id: str
    from_status: str
    to_status: str
    reason: Optional[str] = None
    timestamp: str


class ErrorResponse(BaseModel):
    error: str


def create_prescription_router(service: PrescriptionService) -> APIRouter:
    """Build the prescription CRUD/lifecycle router."""
    router = APIRouter(tags=["prescriptions"])

    @router.post("/prescriptions", response_model=PrescriptionResponse, status_code=201)
    def create_prescription(data: PrescriptionCreate):
        try:
            prescription = service.create_prescription(data.model_dump())
        except ValueError as e:
            raise HTTPException(status_code=400, detail={"error": str(e)})
        except sqlite3.IntegrityError as e:
            raise HTTPException(status_code=409, detail={"error": str(e)})
        return PrescriptionResponse(**prescription.to_dict())

    @router.get("/prescriptions/{prescription_id}", response_model=PrescriptionResponse)
    def get_prescription(prescription_id: str):
        try:
            prescription = service.get_prescription(prescription_id)
        except PrescriptionNotFoundError:
            raise HTTPException(status_code=404, detail={"error": "prescription not found"})
        return PrescriptionResponse(**prescription.to_dict())

    @router.get("/patients/{patient_id}/prescriptions", response_model=List[PrescriptionResponse])
    def list_patient_prescriptions(
        patient_id: str,
        status: Optional[str] = Query(None, description="Filter by status"),
    ):
        status_filter = None
        if status is not None:
            try:
                status_filter = PrescriptionStatus(status)
            except ValueError:
                raise HTTPException(
                    status_code=400, detail={"error": f"invalid status '{status}'"}
                )
        prescriptions = service.list_by_patient(patient_id, status=status_filter)
        return [PrescriptionResponse(**p.to_dict()) for p in prescriptions]

    @router.patch(
        "/prescriptions/{prescription_id}/complete", response_model=PrescriptionResponse
    )
    def complete_prescription(prescription_id: str):
        try:
            prescription = service.complete(prescription_id)
        except PrescriptionNotFoundError:
            raise HTTPException(status_code=404, detail={"error": "prescription not found"})
        except ValueError as e:
            raise HTTPException(status_code=409, detail={"error": str(e)})
        return PrescriptionResponse(**prescription.to_dict())

    @router.patch(
        "/prescriptions/{prescription_id}/discontinue", response_model=PrescriptionResponse
    )
    def discontinue_prescription(prescription_id: str, data: DiscontinueRequest):
        try:
            prescription = service.discontinue(prescription_id, data.reason)
        except PrescriptionNotFoundError:
            raise HTTPException(status_code=404, detail={"error": "prescription not found"})
        except ValueError as e:
            if "reason" in str(e).lower():
                raise HTTPException(status_code=400, detail={"error": str(e)})
            raise HTTPException(status_code=409, detail={"error": str(e)})
        return PrescriptionResponse(**prescription.to_dict())

    @router.get(
        "/prescriptions/{prescription_id}/status-history",
        response_model=List[StatusTransitionResponse],
    )
    def get_status_history(prescription_id: str):
        try:
            service.get_prescription(prescription_id)
        except PrescriptionNotFoundError:
            raise HTTPException(status_code=404, detail={"error": "prescription not found"})
        transitions = service.get_status_history(prescription_id)
        return [StatusTransitionResponse(**t.to_dict()) for t in transitions]

    return router