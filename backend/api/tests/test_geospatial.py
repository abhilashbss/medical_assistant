import pytest
from backend.api.search import find_providers_by_radius
from .see.mocks.backend.db.schema import Provider

def test_find_providers_by_radius_basic():
    """Test that providers within the radius are found and sorted by distance."""
    # Center: (34.0522, -118.2437) - Los Angeles
    # Provider 1: (34.0522, -118.2437) - 0km
    # Provider 3: (34.0600, -118.2500) - ~1.1km
    # Provider 4: (40.7128, -74.0060) - ~3900km

    results = find_providers_by_radius(34.0522, -118.2437, radius_km=5.0)

    assert len(results) == 3 # Dr Smith, Dr Jones, Dr Lee
    assert results[0].name == "Dr. Smith" # 0km
    assert results[-1].name == "Dr. Lee" # ~1.1km

def test_find_providers_by_radius_out_of_range():
    """Test that providers outside the radius are excluded."""
    # Very small radius
    results = find_providers_by_radius(34.0522, -118.2437, radius_km=0.1)

    assert len(results) == 2 # Only Smith and Jones (both at 0km)
    assert all(p.name in ["Dr. Smith", "Dr. Jones"] for p in results)

def test_find_providers_specialty_filter():
    """Test that specialty filter correctly narrows results."""
    results = find_providers_by_radius(34.0522, -118.2437, radius_km=5.0, specialty="Cardiology")

    assert len(results) == 2
    assert all(p.specialty == "Cardiology" for p in results)

def test_find_providers_query_filter():
    """Test that name query filter correctly narrows results."""
    results = find_providers_by_radius(34.0522, -118.2437, radius_km=5.0, query="Lee")

    assert len(results) == 1
    assert results[0].name == "Dr. Lee"

def test_find_providers_combined_filters():
    """Test that multiple filters work together."""
    results = find_providers_by_radius(
        34.0522, -118.2437, radius_km=5.0, specialty="Cardiology", query="Smith"
    )

    assert len(results) == 1
    assert results[0].name == "Dr. Smith"
