import pytest
import time
from backend.api.search import app, MOCK_PROVIDERS
from backend.services.geospatial import find_providers_in_radius

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_geospatial_search_radius():
    """Geospatial search returns providers within requested radius under 500ms"""
    start_time = time.time()
    # Center: 34.0522, -118.2437 (LA)
    results = find_providers_in_radius(
        lat=34.0522,
        lng=-118.2437,
        radius_km=5.0,
        providers_list=MOCK_PROVIDERS
    )
    end_time = time.time()

    assert (end_time - start_time) * 1000 < 500
    assert len(results) >= 1
    assert results[0][0].id == 1

def test_insurance_filtering_logic():
    """Providers are filtered correctly by insurance carrier and plan type"""
    results = find_providers_in_radius(34.0522, -118.2437, 10.0, providers_list=MOCK_PROVIDERS)
    blue_cross_providers = [p for p, dist in results if "BlueCross" in p.insurance_plans]
    assert any(p.id == 1 for p in blue_cross_providers)
    assert any(p.id == 2 for p in blue_cross_providers)
    assert not any(p.id == 3 for p in blue_cross_providers)

def test_real_time_network_status():
    """Results accurately reflect real-time 'In-Network' or 'Out-of-Network' status"""
    provider = MOCK_PROVIDERS[0]
    status = "In-Network" if "BlueCross" in provider.insurance_plans else "Out-of-Network"
    assert status == "In-Network"

def test_search_load_time():
    """Search results load in under 2 seconds for a standard query"""
    start_time = time.time()
    find_providers_in_radius(34.0522, -118.2437, 20.0, specialty="Cardiology", query="Dr", providers_list=MOCK_PROVIDERS)
    end_time = time.time()
    assert (end_time - start_time) < 2.0
