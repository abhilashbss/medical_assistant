from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime

class InsuranceSchema(BaseModel):
    """Schema for insurance plan data."""
    id: str
    carrier_name: str
    payer_id: str
    plan_type: str  # e.g., HMO, PPO, EPO
    tier: str       # e.g., Gold, Silver, Bronze
    created_at: datetime = Field(default_factory=datetime.utcnow)

class InsurancePlan(InsuranceSchema):
    """Domain model for an Insurance Plan."""
    def __init__(self, **data):
        super().__init__(**data)

class NetworkStatus(BaseModel):
    """Relationship between a provider and an insurance plan."""
    provider_id: str
    plan_id: str
    is_in_network: bool
    last_verified: datetime = Field(default_factory=datetime.utcnow)
