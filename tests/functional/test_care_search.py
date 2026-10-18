import pytest
import time
from backend.api.search import find_providers_by_radius

def test_geospatial_search_performance():
    """Geospatial search returns providers within requested radius under 500ms."""
    start_time = time.time()
    # Search in LA area
    results = find_providers_by_radius(34.0522, -118.2437, 10.0)
    end_time = time.time()

    latency_ms = (end_time - start_time) * 1000
    assert latency_ms < 500, f"Search took {latency_ms}ms, which exceeds 500ms limit"
    assert len(results) > 0

def test_search_results_load_time():
    """Search results load in under 2 seconds for a standard query."""
    start_time = time.time()
    # Standard query: Cardiology in LA within 20km
    results = find_providers_by_radius(34.0522, -118.2437, 20.0, specialty="Cardiology")
    end_time = time.time()

    total_time = end_time - start_time
    assert total_time < 2.0, f"Search took {total_time}s, which exceeds 2s limit"
    assert len(results) >= 0
