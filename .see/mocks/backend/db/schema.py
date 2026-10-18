# runctl:mock-of backend.db.schema
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class Provider:
    id: int
    name: str
    specialty: str
    location: tuple[float, float]  # (lat, lng)
    insurance_network: str

class MockSession:
    def __init__(self):
        self.providers = [
            Provider(1, "Dr. Smith", "Cardiology", (34.0522, -118.2437), "BlueCross"),
            Provider(2, "Dr. Jones", "Pediatrics", (34.0522, -118.2437), "Aetna"),
            Provider(3, "Dr. Lee", "Cardiology", (34.0600, -118.2500), "BlueCross"),
            Provider(4, "Dr. Brown", "Dermatology", (40.7128, -74.0060), "UnitedHealth"),
        ]

    def query(self, model):
        return self

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return self.providers

def get_db_session():
    return MockSession()
