"""FastAPI application for medication tracker API."""

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from typing import Optional, List

from medication_tracker import get_database, MedicationRepository
from api.routes.medications import (
    MedicationAPI,
    MedicationCreate,
    MedicationUpdate,
    MedicationResponse,
    ErrorResponse,
)


def create_app(db_path: Optional[str] = None) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        db_path: Optional path to database file

    Returns:
        Configured FastAPI application
    """
    app = FastAPI(
        title="Medication Tracker API",
        description="API for managing prescribed medications with dosage schedules",
        version="1.0.0",
    )

    # Initialize database and repository
    db = get_database(db_path)
    db.init_schema()
    repository = MedicationRepository(db)
    api = MedicationAPI(repository)

    @app.post(
        "/medications",
        response_model=MedicationResponse,
        status_code=201,
        responses={
            201: {"description": "Medication created successfully"},
            400: {"model": ErrorResponse, "description": "Validation error"},
        },
    )
    def create_medication(data: MedicationCreate):
        """Create a new medication entry.

        Required fields:
        - **name**: Medication name (non-empty string)
        - **dosage**: Dosage amount and unit, e.g., "500mg" (non-empty string)
        - **frequency**: How often to take, e.g., "twice daily" (non-empty string)

        Optional fields:
        - **start_date**: Treatment start date (ISO format: YYYY-MM-DD)
        - **end_date**: Treatment end date (ISO format: YYYY-MM-DD)
        - **status**: Status, either "active" or "completed" (default: "active")

        Returns 201 with the created medication on success.
        Returns 400 with error details if validation fails.
        """
        try:
            response, status_code = api.create(data)
            return JSONResponse(status_code=status_code, content=response.model_dump())
        except ValueError as e:
            raise HTTPException(status_code=400, detail={"error": str(e)})

    @app.get(
        "/medications",
        response_model=List[MedicationResponse],
        responses={
            200: {"description": "List of medications retrieved successfully"},
        },
    )
    def get_medications(status: Optional[str] = Query(None, description="Filter by status (active/completed)")):
        """Get all medications sorted by created_at descending.

        Optional query parameters:
        - **status**: Filter by status ("active" or "completed")

        Returns 200 with an array of medications.
        """
        try:
            responses, status_code = api.get_all(status=status)
            return JSONResponse(status_code=status_code, content=[r.model_dump() for r in responses])
        except ValueError as e:
            raise HTTPException(status_code=400, detail={"error": str(e)})

    @app.get(
        "/medications/{medication_id}",
        response_model=MedicationResponse,
        responses={
            200: {"description": "Medication retrieved successfully"},
            404: {"model": ErrorResponse, "description": "Medication not found"},
        },
    )
    def get_medication(medication_id: str):
        """Get a specific medication by ID.

        Path parameters:
        - **medication_id**: UUID of the medication

        Returns 200 with the medication on success.
        Returns 404 if the medication is not found.
        """
        try:
            response, status_code = api.get_by_id(medication_id)
            return JSONResponse(status_code=status_code, content=response.model_dump())
        except ValueError as e:
            if "not found" in str(e).lower():
                raise HTTPException(status_code=404, detail={"error": str(e)})
            raise HTTPException(status_code=400, detail={"error": str(e)})

    @app.put(
        "/medications/{medication_id}",
        response_model=MedicationResponse,
        responses={
            200: {"description": "Medication updated successfully"},
            400: {"model": ErrorResponse, "description": "Validation error"},
            404: {"model": ErrorResponse, "description": "Medication not found"},
        },
    )
    def update_medication(medication_id: str, data: MedicationUpdate):
        """Update an existing medication.

        Path parameters:
        - **medication_id**: UUID of the medication to update

        Request body fields (all optional):
        - **name**: Medication name (non-empty string)
        - **dosage**: Dosage amount and unit
        - **frequency**: How often to take
        - **start_date**: Treatment start date
        - **end_date**: Treatment end date
        - **status**: Status, either "active" or "completed"

        Returns 200 with the updated medication on success.
        Returns 404 if the medication is not found.
        Returns 400 with error details if validation fails.
        """
        try:
            response, status_code = api.update(medication_id, data)
            return JSONResponse(status_code=status_code, content=response.model_dump())
        except ValueError as e:
            if "not found" in str(e).lower():
                raise HTTPException(status_code=404, detail={"error": str(e)})
            raise HTTPException(status_code=400, detail={"error": str(e)})

    @app.delete(
        "/medications/{medication_id}",
        status_code=204,
        responses={
            204: {"description": "Medication deleted successfully"},
            404: {"model": ErrorResponse, "description": "Medication not found"},
        },
    )
    def delete_medication(medication_id: str):
        """Delete a medication.

        Path parameters:
        - **medication_id**: UUID of the medication to delete

        Returns 204 on success (no content).
        Returns 404 if the medication is not found.
        """
        try:
            _, status_code = api.delete(medication_id)
            return JSONResponse(status_code=status_code, content={})
        except ValueError as e:
            if "not found" in str(e).lower():
                raise HTTPException(status_code=404, detail={"error": str(e)})
            raise HTTPException(status_code=400, detail={"error": str(e)})

    @app.on_event("shutdown")
    def shutdown_db():
        """Close database connection on shutdown."""
        db.close()

    return app


# Create default app instance
app = create_app()
