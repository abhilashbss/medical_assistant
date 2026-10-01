"""Minimal FastAPI surface for the prescription tracker.

This is the thin HTTP layer over :mod:`medication_tracker.repository`.
It exposes the endpoints the functional gate exercises:

  POST   /patients/{patient_id}/prescriptions   create
  GET    /prescriptions/{rx_id}                  retrieve
  GET    /patients/{patient_id}/prescriptions    history (start_date DESC)
  PATCH  /prescriptions/{rx_id}/discontinue      discontinue (reason required)
  PATCH  /prescriptions/{rx_id}/complete         complete

Each request opens its own connection via :func:`medication_tracker.db.connect`
so foreign_keys = ON is guaranteed per connection.
"""

from __future__ import annotations

import os
import sqlite3
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .db import connect
from .migrations.runner import run_migrations
from . import repository as repo


class PrescriptionCreate(BaseModel):
    doctor_id: str
    doctor_name: Optional[str] = "Unknown"
    medicine_name: str
    dosage_amount: float
    dosage_unit: str
    frequency: str
    start_date: str
    end_date: Optional[str] = None


class DiscontinueBody(BaseModel):
    reason: str = Field(..., min_length=1)


def _db_path() -> Optional[str]:
    return os.environ.get("MEDICATION_TRACKER_DB")


def _conn() -> sqlite3.Connection:
    conn = connect(_db_path())
    # Make sure the schema exists on the configured database.
    run_migrations(conn)
    return conn


def create_app() -> FastAPI:
    app = FastAPI(title="Medication Tracker")

    # --- internal helpers ------------------------------------------------- #

    def _integrity_to_http(exc: sqlite3.IntegrityError):
        msg = str(exc).upper()
        if "UNIQUE" in msg:
            detail = "A prescription for this medicine already exists for the patient"
            return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
        if "FOREIGN KEY" in msg:
            return HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Referenced patient or doctor does not exist",
            )
        if "CHECK" in msg:
            return HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            )
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        )

    # --- endpoints -------------------------------------------------------- #

    @app.post(
        "/patients/{patient_id}/prescriptions",
        status_code=status.HTTP_201_CREATED,
    )
    def create_prescription(patient_id: str, body: PrescriptionCreate) -> Dict[str, Any]:
        conn = _conn()
        try:
            repo.ensure_patient(conn, patient_id)
            repo.ensure_doctor(conn, body.doctor_id, body.doctor_name or "Unknown")
            data = body.model_dump()
            data["patient_id"] = patient_id
            return repo.create_prescription(conn, data)
        except repo.ValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{exc.field}: {exc.message}",
            )
        except sqlite3.IntegrityError as exc:
            raise _integrity_to_http(exc)
        finally:
            conn.close()

    @app.get("/prescriptions/{rx_id}")
    def get_prescription(rx_id: str) -> Dict[str, Any]:
        conn = _conn()
        try:
            row = repo.get_prescription(conn, rx_id)
            if row is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Not found"
                )
            return row
        finally:
            conn.close()

    @app.get("/patients/{patient_id}/prescriptions")
    def list_prescriptions(patient_id: str) -> List[Dict[str, Any]]:
        conn = _conn()
        try:
            return repo.list_by_patient(conn, patient_id)
        finally:
            conn.close()

    @app.patch("/prescriptions/{rx_id}/discontinue")
    def discontinue(rx_id: str, body: DiscontinueBody) -> Dict[str, Any]:
        conn = _conn()
        try:
            return repo.discontinue_prescription(conn, rx_id, body.reason)
        except repo.ValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{exc.field}: {exc.message}",
            )
        except KeyError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Not found"
            )
        finally:
            conn.close()

    @app.patch("/prescriptions/{rx_id}/complete")
    def complete(rx_id: str) -> Dict[str, Any]:
        conn = _conn()
        try:
            return repo.complete_prescription(conn, rx_id)
        except repo.ValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{exc.field}: {exc.message}",
            )
        except KeyError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Not found"
            )
        finally:
            conn.close()

    @app.get("/health")
    def health() -> Dict[str, str]:
        return {"status": "ok"}

    @app.exception_handler(RequestValidationError)
    async def _validation_exception_handler(request, exc):  # noqa: ANN001
        # Surface request validation failures as 400 to match the API
        # contract ("400-level error"), preserving the detail payload.
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": exc.errors()},
        )

    return app


app = create_app()