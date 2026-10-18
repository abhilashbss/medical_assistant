import pytest
from backend.api.search import find_providers_by_radius

def test_find_providers_by_radius_basic():
    # Center at (34.0522, -118.2437) - Dr. Alice Smith
    # Radius 10km should find Alice and Bob, and Charlie
    results = find_providers_by_radius(34.0522, -118.2437, 10.0)

    # Mock data:
    # Alice: 34.0522, -118.2437 (0km)
    # Bob: 34.0600, -118.2500 (~1km)
    # Charlie: 34.1000, -118.3000 (~8km)
    # Diana: 40.7128, -74.0060 (~3900km)

    assert len(results) == 3
    assert results[0]['name'] == "Dr. Alice Smith"
    assert results[0]['distance_km'] == 0.0
    assert any(r['name'] == "Dr. Bob Jones" for r in results)
    assert not any(r['name'] == "Dr. Diana Prince" for r in results)

def test_find_providers_by_radius_specialty():
    # Only Cardiology in LA
    results = find_providers_by_radius(34.0522, -118.2437, 10.0, specialty="Cardiology")

    assert len(results) == 2
    assert all(r['specialty'] == "Cardiology" for r in results)
    assert not any(r['specialty'] == "Dermatology" for r in results)

def test_find_providers_by_radius_query():
    # Only "Alice" in LA
    results = find_providers_by_radius(34.0522, -118.2437, 10.0, query="Alice")

    assert len(results) == 1
    assert results[0]['name'] == "Dr. Alice Smith"

def test_find_providers_by_radius_empty():
    # Search in the middle of the ocean
    results = find_providers_by_radius(0.0, 0.0, 10.0)
    assert len(results) == 0
