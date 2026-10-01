"""Dose tracking API request/response schemas.

Documents the request and response shapes for the dose endpoints exposed under
/medications/<id>/doses (and the /dose alias).
"""

from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class DoseCreateRequest(BaseModel):
    """Request body for POST /medications/<id>/doses."""

    date: Optional[date] = Field(
        None,
        description="ISO date (YYYY-MM-DD) for the dose. Defaults to today.",
    )
    status: str = Field(
        "taken",
        description="Dose status: 'taken' or 'skipped'.",
    )

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in ("taken", "skipped"):
            raise ValueError("status must be 'taken' or 'skipped'")
        return v


class DoseRecordResponse(BaseModel):
    """Response schema for a single dose record."""

    id: str
    medication_id: str
    date: str
    timestamp: Optional[str] = None
    status: str


class DoseHistoryResponse(BaseModel):
    """Response schema for a dose history list."""

    doses: List[DoseRecordResponse]


class DoseQueryParams(BaseModel):
    """Query parameters for GET /medications/<id>/doses."""

    start: Optional[date] = Field(None, description="Start date filter (inclusive, ISO).")
    end: Optional[date] = Field(None, description="End date filter (inclusive, ISO).")