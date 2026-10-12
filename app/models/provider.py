from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime

class ProviderSchema(BaseModel):
    """Schema for medical provider data."""
    id: str
    npi: str = Field(..., description="National Provider Identifier")
    name: str
    specialty: str
    address: str
    latitude: float
    longitude: float
    created_at: datetime = Field(default_factory=datetime.utcnow)

class Provider(ProviderSchema):
    """Domain model for a Medical Provider."""
    def __init__(self, **data):
        super().__init__(**data)

class ProviderPHIVault(BaseModel):
    """
    HIPAA-compliant vault for Provider PHI.
    In a real implementation, this would be stored in an encrypted
    table or external vault service.
    """
    provider_id: str
    phone_number: str  # Encrypted
    email: str         # Encrypted
    private_notes: Optional[str] = None # Encrypted
