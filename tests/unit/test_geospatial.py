import pytest
from backend.services.geospatial import geospatial_service
from dataclasses import dataclass

@dataclass
class MockProvider:
    id: int
    name: str
    specialty: str
    location: tuple
    insurance_networks: list

def test_find_nearby_providers_radius_filtering(monkeypatch):
    # Mock providers: one inside radius, one outside
    mock_providers = [
        MockProvider(1, "Nearby Doc", "GP", (34.0522, -118.2437), ["Aetna"]), # LA
        MockProvider(2, "Far Doc", "GP", (40.7128, -74.0060), ["Aetna"]),    # NY
    ]

    def mock_get_db_session():
        class Session:
            def query(self, model): return self
            def all(self): return mock_providers
        return Session()

    monkeypatch.setattr("backend.services.geospatial.get_db_session", mock_get_db_session)

    # Search in LA with 10km radius
    results = geospatial_service.find_nearby_providers(
        lat=34.0522, lng=-118.2437, radius_km=10
    )

    assert len(results) == 1
    assert results[0][0].name == "Nearby Doc"

def test_find_nearby_providers_specialty_filter(monkeypatch):
    mock_providers = [
        MockProvider(1, "Cardio Doc", "Cardiology", (34.0522, -118.2437), ["Aetna"]),
        MockProvider(2, "GP Doc", "General Practice", (34.0522, -118.2437), ["Aetna"]),
    ]

    def mock_get_db_session():
        class Session:
            def query(self, model): return self
            def all(self): return mock_providers
        return Session()

    monkeypatch.setattr("backend.services.geospatial.get_db_session", mock_get_db_session)

    results = geospatial_service.find_nearby_providers(
        lat=34.0522, lng=-118.2437, radius_km=10, specialty="Cardiology"
    )

    assert len(results) == 1
    assert results[0][0].specialty == "Cardiology"

def test_find_nearby_providers_query_filter(monkeypatch):
    mock_providers = [
        MockProvider(1, "Dr. Smith", "GP", (34.0522, -118.2437), ["Aetna"]),
        MockProvider(2, "Dr. Jones", "GP", (34.0522, -118.2437), ["Aetna"]),
    ]

    def mock_get_db_session():
        class Session:
            def query(self, model): return self
            def all(self): return mock_providers
        return Session()

    monkeypatch.setattr("backend.services.geospatial.get_db_session", mock_get_db_session)

    results = geospatial_service.find_nearby_providers(
        lat=34.0522, lng=-118.2437, radius_km=10, query="Smith"
    )

    assert len(results) == 1
    assert "Smith" in results[0][0].name

def test_find_nearby_providers_sorting(monkeypatch):
    mock_providers = [
        MockProvider(1, "Mid Doc", "GP", (34.0600, -118.2500), ["Aetna"]), # Closer
        MockProvider(2, "Far Doc", "GP", (34.0700, -118.2600), ["Aetna"]), # Farther
    ]

    def mock_get_db_session():
        class Session:
            def query(self, model): return self
            def all(self): return mock_providers
        return Session()

    monkeypatch.setattr("backend.services.geospatial.get_db_session", mock_get_db_session)

    results = geospatial_service.find_nearby_providers(
        lat=34.0522, lng=-118.2437, radius_km=50
    )

    assert results[0][1] < results[1][1]
    assert results[0][0].name == "Mid Doc"
