"""FastAPI endpoints for prescription tracking.

Endpoints:
  POST   /patients/{patient_id}/prescriptions
  GET    /prescriptions/{rx_id}
  GET    /patients/{patient_id}/prescriptions           (history, active separated)
  PATCH  /prescriptions/{rx_id}/complete
  PATCH  /prescriptions/{rx_id}/discontinue
  POST   /prescriptions/{rx_id}/dose-logs
  GET    /prescriptions/{rx_id}/dose-logs
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .db import init_db
from .models import (
    DoseLogCreate,
    PrescriptionCreate,
    StatusTransition,
    ValidationError,
)
from .repository import NotFoundError, PrescriptionRepository

DB_PATH = os.environ.get("PRESCRIPTION_DB_PATH", ":memory:")

app = FastAPI(title="Prescription Tracker")
_conn = init_db(DB_PATH)
_repo = PrescriptionRepository(_conn)


@app.exception_handler(__import__("sqlite3").IntegrityError)
async def _integrity_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": "integrity constraint violated", "error": str(exc)},
    )


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


@app.post("/patients/{patient_id}/prescriptions")
def create_prescription(patient_id: str, body: PrescriptionIn):
    from .db import seed_reference_data
    seed_reference_data(_conn, patient_id, body.doctor_id)
    try:
        rx = _repo.create_prescription(_build_rx_create(patient_id, body))
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors)
    return rx


@app.get("/prescriptions/{rx_id}")
def get_prescription(rx_id: str):
    try:
        return _repo.get_prescription(rx_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="not found")


@app.get("/patients/{patient_id}/prescriptions")
def list_prescriptions(patient_id: str):
    return _repo.list_by_patient(patient_id)


@app.patch("/prescriptions/{rx_id}/complete")
def complete_prescription(rx_id: str):
    try:
        return _repo.complete_dict(rx_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="not found")
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors)


@app.patch("/prescriptions/{rx_id}/discontinue")
def discontinue_prescription(rx_id: str, body: DiscontinueIn):
    try:
        return _repo.discontinue_dict(rx_id, body.reason)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="not found")
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors)


@app.post("/prescriptions/{rx_id}/dose-logs")
def add_dose_log(rx_id: str, body: DoseLogIn):
    try:
        log = _repo.add_dose_log(
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


@app.get("/prescriptions/{rx_id}/dose-logs")
def get_dose_logs(rx_id: str, start: Optional[str] = None, end: Optional[str] = None):
    return _repo.get_dose_logs(rx_id, start_ts=start, end_ts=end)