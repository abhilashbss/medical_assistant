from typing import Optional, List, Dict
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

class InsuranceRepository:
    """Simulation of an insurance network repository."""
    def __init__(self):
        self._plans = {}
        self._networks = {} # (provider_id, plan_id) -> NetworkStatus

    def add_plan(self, plan: InsurancePlan):
        self._plans[plan.id] = plan

    def set_network_status(self, provider_id: str, plan_id: str, is_in_network: bool):
        self._networks[(provider_id, plan_id)] = NetworkStatus(
            provider_id=provider_id,
            plan_id=plan_id,
            is_in_network=is_in_network
        )

    def is_in_network(self, provider_id: str, plan_id: str) -> bool:
        status = self._networks.get((provider_id, plan_id))
        return status.is_in_network if status else False

    def get_plan(self, plan_id: str) -> Optional[InsurancePlan]:
        return self._plans.get(plan_id)
