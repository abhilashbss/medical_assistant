"""Route definitions for the prescription tracker."""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from . import state
from .db import seed_reference_data
from .models import (
    DoseLogCreate,
    PrescriptionCreate,
    ValidationError,
)
from .repository import NotFoundError


router = APIRouter()


# ---------------------------------------------------------------- request schemas
class PrescriptionIn(BaseModel):
    doctor_id: str
    medicine_name: str
    dosage_amount: float
    dosage_unit: str
    frequency: str
    start_date: str
    end_date: Optional[str] = None


class DoseLogIn(BaseModel):
    event: str
    timestamp: str
    notes: Optional[str] = None


class DiscontinueIn(BaseModel):
    reason: str


def _build_rx_create(patient_id: str, body: PrescriptionIn) -> PrescriptionCreate:
    return PrescriptionCreate(
        patient_id=patient_id,
        doctor_id=body.doctor_id,
        medicine_name=body.medicine_name,
        dosage_amount=body.dosage_amount,
        dosage_unit=body.dosage_unit,
        frequency=body.frequency,
        start_date=body.start_date,
        end_date=body.end_date,
    )


@router.post("/patients/{patient_id}/prescriptions")
def create_prescription(patient_id: str, body: PrescriptionIn):
    seed_reference_data(state.conn, patient_id, body.doctor_id)
    try:
        rx = state.repo.create_prescription(_build_rx_create(patient_id, body))
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors)
    return rx


@router.get("/prescriptions/{rx_id}")
def get_prescription(rx_id: str):
    try:
        return state.repo.get_prescription(rx_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="not found")


@router.get("/patients/{patient_id}/prescriptions")
def list_prescriptions(patient_id: str):
    return state.repo.list_by_patient(patient_id)


@router.patch("/prescriptions/{rx_id}/complete")
def complete_prescription(rx_id: str):
    try:
        return state.repo.complete(rx_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="not found")
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors)


@router.patch("/prescriptions/{rx_id}/discontinue")
def discontinue_prescription(rx_id: str, body: DiscontinueIn):
    try:
        return state.repo.discontinue(rx_id, body.reason)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="not found")
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors)


@router.post("/prescriptions/{rx_id}/dose-logs")
def add_dose_log(rx_id: str, body: DoseLogIn):
    try:
        log = state.repo.add_dose_log(
            DoseLogCreate(
                prescription_id=rx_id,
                event=body.event,
                timestamp=body.timestamp,
                notes=body.notes,
            )
        )
    except NotFoundError:
        raise HTTPException(status_code=404, detail="not found")
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors)
    return log


@router.get("/prescriptions/{rx_id}/dose-logs")
def get_dose_logs(rx_id: str, start: Optional[str] = None, end: Optional[str] = None):
    return state.repo.get_dose_logs(rx_id, start_ts=start, end_ts=end)
