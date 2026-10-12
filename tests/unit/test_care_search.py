import pytest
from app.models.provider import Provider, ProviderRepository, ProviderPHIVault

def test_geospatial_radius_search():
    repo = ProviderRepository()
    p1 = Provider(id="p1", npi="123", name="Dr. SF", specialty="GP", address="SF", latitude=37.7749, longitude=-122.4194)
    p2 = Provider(id="p2", npi="456", name="Dr. SJ", specialty="GP", address="SJ", latitude=37.3382, longitude=-121.8863)
    repo.add(p1)
    repo.add(p2)
    results = repo.find_nearby(37.7749, -122.4194, 20)
    assert p1 in results
    assert p2 not in results
    results_large = repo.find_nearby(37.7749, -122.4194, 100)
    assert p1 in results_large
    assert p2 in results_large

def test_specialty_filtering():
    repo = ProviderRepository()
    p1 = Provider(id="p1", npi="123", name="Dr. A", specialty="Cardiology", address="A", latitude=37.7, longitude=-122.4)
    p2 = Provider(id="p2", npi="456", name="Dr. B", specialty="Dermatology", address="B", latitude=37.7, longitude=-122.4)
    repo.add(p1)
    repo.add(p2)
    results = repo.find_nearby(37.7, -122.4, 10, specialty="Cardiology")
    assert p1 in results
    assert p2 not in results

def test_phi_separation():
    provider = Provider(id="p1", npi="123", name="Dr. X", specialty="GP", address="Addr", latitude=0, longitude=0)
    phi = ProviderPHIVault(provider_id="p1", phone_number="ENCRYPTED_PHONE", email="ENCRYPTED_EMAIL")
    assert not hasattr(provider, 'phone_number')
    assert phi.provider_id == provider.id
