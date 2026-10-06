"""FastAPI application for the prescription tracker."""

from typing import Optional

from fastapi import FastAPI

from medication_tracker import (
    DoseLogService,
    PrescriptionDoseLogRepository,
    PrescriptionRepository,
    PrescriptionService,
    get_database,
)
from api.routes.prescriptions import create_prescription_router
from api.routes.dose_logs import create_dose_log_router


def create_app(db_path: Optional[str] = None) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        db_path: Optional path to the SQLite database file.

    Returns:
        Configured FastAPI application.
    """
    app = FastAPI(
        title="Prescription Tracker API",
        description="Track medicine prescriptions and dose adherence",
        version="1.0.0",
    )

    db = get_database(db_path)
    db.init_schema()

    prescription_repo = PrescriptionRepository(db)
    prescription_service = PrescriptionService(prescription_repo)
    dose_log_repo = PrescriptionDoseLogRepository(db)
    dose_log_service = DoseLogService(dose_log_repo, prescription_service)

    app.include_router(create_prescription_router(prescription_service))
    app.include_router(create_dose_log_router(dose_log_service))

    @app.on_event("shutdown")
    def shutdown_db():
        db.close()

    return app


# Default app instance for uvicorn
app = create_app()