"""FastAPI application factory for prescription tracking."""
from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from .routes import router

app = FastAPI(title="Prescription Tracker")
app.include_router(router)


@app.exception_handler(__import__("sqlite3").IntegrityError)
async def _integrity_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": "integrity constraint violated", "error": str(exc)},
    )
