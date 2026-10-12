import math
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

class ProviderRepository:
    """Simulation of a geospatial-enabled provider repository."""
    def __init__(self):
        self._providers = {}

    def add(self, provider: Provider):
        self._providers[provider.id] = provider

    def get_by_id(self, provider_id: str) -> Optional[Provider]:
        return self._providers.get(provider_id)

    def find_nearby(self, lat: float, lon: float, radius_km: float, specialty: Optional[str] = None) -> List[Provider]:
        results = []
        for p in self._providers.values():
            if specialty and p.specialty != specialty:
                continue
            if self._haversine_distance(lat, lon, p.latitude, p.longitude) <= radius_km:
                results.append(p)
        return results

    def _haversine_distance(self, lat1, lon1, lat2, lon2):
        R = 6371  # Earth radius in km
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (math.sin(dlat / 2)**2 +
             math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
             math.sin(dlon / 2)**2)
        c = 2 * math.asin(math.sqrt(a))
        return R * c
