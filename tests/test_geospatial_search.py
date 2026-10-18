import pytest
from backend.api.search import find_providers_by_radius
from backend.services.geospatial import GeospatialService
from geopy.distance import geodesic

# Mock coordinates
# LA coordinates: 34.0522, -118.2437
LA_LAT = 34.0522
LA_LNG = -118.2437

# A point roughly 5km away from LA
NEARBY_LAT = 34.0600
NEARBY_LNG = -118.2500

# A point far away (NY)
FAR_LAT = 40.7128
FAR_LNG = -74.0060

def test_find_providers_within_radius():
    """Verify providers within the specified radius are returned."""
    # Using the mock data from .see/mocks/backend/db/schema.py
    # Dr. Smith and Dr. Jones are at (34.0522, -118.2437)
    # Dr. Lee is at (34.0600, -118.2500)

    results = find_providers_by_radius(LA_LAT, LA_LNG, radius_km=10)
    # Should find Smith, Jones, and Lee
    assert len(results) >= 3
    assert any(p.name == "Dr. Smith" for p in results)
    assert any(p.name == "Dr. Lee" for p in results)

def test_find_providers_outside_radius():
    """Verify providers outside the specified radius are not returned."""
    # Only search with a very small radius
    results = find_providers_by_radius(LA_LAT, LA_LNG, radius_km=0.1)
    # Should only find Smith and Jones (at the exact coordinate)
    assert len(results) == 2
    assert not any(p.name == "Dr. Lee" for p in results)

def test_specialty_filter():
    """Verify that specialty filters correctly narrow the results."""
    results = find_providers_by_radius(LA_LAT, LA_LNG, radius_km=10, specialty="Cardiology")
    # Smith and Lee are Cardiology
    assert len(results) == 2
    for p in results:
        assert p.specialty == "Cardiology"

def test_name_query_filter():
    """Verify that name query filters correctly narrow the results."""
    results = find_providers_by_radius(LA_LAT, LA_LNG, radius_km=10, query="Smith")
    assert len(results) == 1
    assert results[0].name == "Dr. Smith"

def test_combined_filters():
    """Verify combined radius, specialty, and name filters."""
    results = find_providers_by_radius(LA_LAT, LA_LNG, radius_km=10, specialty="Cardiology", query="Lee")
    assert len(results) == 1
    assert results[0].name == "Dr. Lee"

def test_no_results():
    """Verify behavior when no providers match the criteria."""
    results = find_providers_by_radius(FAR_LAT, FAR_LNG, radius_km=1)
    # In the mock data, only Dr. Brown is in NY (40.7128, -74.0060)
    # But if we search far away from him, we should get 0.
    results = find_providers_by_radius(0, 0, radius_km=1)
    assert len(results) == 0
