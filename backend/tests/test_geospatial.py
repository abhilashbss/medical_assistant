import pytest
from backend.services.geospatial import find_providers_in_radius
try:
    from backend.db.models import Provider
except ImportError:
    try:
        from .see.mocks.backend.db.models import Provider
    except ImportError:
        from dataclasses import dataclass
        @dataclass
        class Provider:
            id: int
            name: str
            specialty: str
            location: tuple[float, float]
            insurance_plans: list[str]

def test_find_providers_within_radius():
    center_lat, center_lng = 34.0522, -118.2437
    radius = 10.0
    providers = [
        Provider(1, "Near Provider", "GP", (34.0530, -118.2440), []),
        Provider(2, "Far Provider", "GP", (34.1500, -118.3500), []),
        Provider(3, "Edge Provider", "GP", (34.0600, -118.2500), []),
    ]
    results = find_providers_in_radius(center_lat, center_lng, radius, providers_list=providers)
    assert len(results) == 2
    assert results[0][0].name == "Near Provider"
    assert results[1][0].name == "Edge Provider"

def test_specialty_filter():
    center_lat, center_lng = 34.0522, -118.2437
    radius = 10.0
    providers = [
        Provider(1, "Cardio 1", "Cardiology", (34.0530, -118.2440), []),
        Provider(2, "Derm 1", "Dermatology", (34.0540, -118.2450), []),
    ]
    results = find_providers_in_radius(center_lat, center_lng, radius, specialty="Cardiology", providers_list=providers)
    assert len(results) == 1
    assert results[0][0].specialty == "Cardiology"

def test_name_query_filter():
    center_lat, center_lng = 34.0522, -118.2437
    radius = 10.0
    providers = [
        Provider(1, "Dr. Smith", "GP", (34.0530, -118.2440), []),
        Provider(2, "Dr. Jones", "GP", (34.0540, -118.2450), []),
    ]
    results = find_providers_in_radius(center_lat, center_lng, radius, query="Smith", providers_list=providers)
    assert len(results) == 1
    assert "Smith" in results[0][0].name
