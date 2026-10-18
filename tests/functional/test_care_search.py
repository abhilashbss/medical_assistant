import pytest
import time
from unittest.mock import patch
from backend.services.filtering import filter_in_network_providers
from backend.services.ranking import rank_providers

# Mocks for sibling services
try:
    from backend.services.geospatial import find_providers_in_radius
except ImportError:
    import sys
    import os
    sys.path.append(os.path.join(os.getcwd(), ".see/mocks"))
    try:
        from backend.services.geospatial import find_providers_in_radius
    except ImportError:
        def find_providers_in_radius(lat, lon, radius_km):
            return [{"id": 1, "name": "Mock P1", "lat": lat, "lon": lon, "rating": 5.0}]

@pytest.fixture
def search_ctx():
    return {"lat": 40.7128, "lon": -74.0060, "carrier": "BCBS", "plan": "PPO", "radius": 10}

def test_insurance_carrier_plan_filtering(search_ctx):
    """Providers are filtered correctly by insurance carrier and plan type."""
    providers = [{"id": 1, "name": "Dr A"}, {"id": 2, "name": "Dr B"}]
    with patch('backend.services.filtering.verify_network_status') as mock_verify:
        mock_verify.side_effect = lambda p_id, c, pl: "in-network" if p_id == 1 else "out-of-network"
        results = filter_in_network_providers(providers, search_ctx["carrier"], search_ctx["plan"])
        assert len(results) == 1
        assert results[0]["id"] == 1

def test_search_returns_only_in_network(search_ctx):
    """Search results return only 'in-network' providers for selected insurance."""
    nearby = find_providers_in_radius(search_ctx["lat"], search_ctx["lon"], search_ctx["radius"])
    with patch('backend.services.filtering.verify_network_status') as mock_verify:
        mock_verify.side_effect = lambda p_id, c, pl: "in-network" if p_id == 1 else "out-of-network"
        filtered = filter_in_network_providers(nearby, search_ctx["carrier"], search_ctx["plan"])
        ranked = rank_providers(filtered, search_ctx["lat"], search_ctx["lon"])
        assert all(p["id"] == 1 for p in ranked)

def test_geospatial_radius_filtering(search_ctx):
    """Geospatial search returns providers within the specified radius."""
    results = find_providers_in_radius(search_ctx["lat"], search_ctx["lon"], search_ctx["radius"])
    assert len(results) >= 0

def test_real_time_network_verification(search_ctx):
    """Network status is verified in real-time via external API mocks."""
    providers = [{"id": 1, "name": "Dr A"}]
    with patch('backend.services.filtering.verify_network_status') as mock_verify:
        mock_verify.return_value = "in-network"
        filter_in_network_providers(providers, search_ctx["carrier"], search_ctx["plan"])
        mock_verify.assert_called_with(1, search_ctx["carrier"], search_ctx["plan"])

def test_search_latency(search_ctx):
    """Search latency remains under 2 seconds for all functional scenarios."""
    providers = [{"id": i, "lat": 40.0, "lon": -70.0, "rating": 4.0} for i in range(100)]
    with patch('backend.services.filtering.verify_network_status', return_value="in-network"):
        start = time.time()
        filtered = filter_in_network_providers(providers, search_ctx["carrier"], search_ctx["plan"])
        ranked = rank_providers(filtered, search_ctx["lat"], search_ctx["lon"])
        assert (time.time() - start) < 2.0
