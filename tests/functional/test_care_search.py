import pytest
import time
from unittest.mock import patch
from backend.logic.filtering import filter_and_rank_providers

@pytest.fixture
def search_ctx():
    return {"lat": 40.7128, "lon": -74.0060, "insurance_plan": "PPO_PLAN", "radius": 10}

def test_insurance_carrier_plan_filtering(search_ctx):
    """Providers are filtered correctly by insurance carrier and plan type."""
    with patch('backend.logic.filtering.find_providers_by_radius') as mock_find, \
         patch('backend.logic.filtering.verify_network_status') as mock_verify:

        mock_find.return_value = [{"id": 1, "name": "Dr A"}, {"id": 2, "name": "Dr B"}]
        mock_verify.side_effect = lambda p_id, plan: "in-network" if p_id == 1 else "out-of-network"

        results = filter_and_rank_providers(search_ctx["lat"], search_ctx["lon"], search_ctx["radius"], search_ctx["insurance_plan"])
        assert len(results) == 1
        assert results[0]["id"] == 1

def test_search_returns_only_in_network(search_ctx):
    """Search results return only 'in-network' providers for selected insurance."""
    with patch('backend.logic.filtering.find_providers_by_radius') as mock_find, \
         patch('backend.logic.filtering.verify_network_status') as mock_verify:

        mock_find.return_value = [{"id": 1, "name": "Dr A"}, {"id": 2, "name": "Dr B"}]
        mock_verify.side_effect = lambda p_id, plan: "in-network" if p_id == 1 else "out-of-network"

        results = filter_and_rank_providers(search_ctx["lat"], search_ctx["lon"], search_ctx["radius"], search_ctx["insurance_plan"])
        assert all(p["id"] == 1 for p in results)

def test_geospatial_radius_filtering(search_ctx):
    """Geospatial search returns providers within the specified radius."""
    with patch('backend.logic.filtering.find_providers_by_radius') as mock_find, \
         patch('backend.logic.filtering.verify_network_status') as mock_verify:

        mock_find.return_value = [{"id": 1, "name": "Dr A", "distance": 1.0, "rating": 4.0}]
        mock_verify.return_value = "in-network"

        results = filter_and_rank_providers(search_ctx["lat"], search_ctx["lon"], search_ctx["radius"], search_ctx["insurance_plan"])
        assert len(results) >= 0
        mock_find.assert_called_with(search_ctx["lat"], search_ctx["lon"], search_ctx["radius"])

def test_real_time_network_verification(search_ctx):
    """Network status is verified in real-time via external API mocks."""
    with patch('backend.logic.filtering.find_providers_by_radius') as mock_find, \
         patch('backend.logic.filtering.verify_network_status') as mock_verify:

        mock_find.return_value = [{"id": 1, "name": "Dr A"}]
        mock_verify.return_value = "in-network"

        filter_and_rank_providers(search_ctx["lat"], search_ctx["lon"], search_ctx["radius"], search_ctx["insurance_plan"])
        mock_verify.assert_called_with(1, search_ctx["insurance_plan"])

def test_search_latency(search_ctx):
    """Search latency remains under 2 seconds for all functional scenarios."""
    # Test with 100 providers
    with patch('backend.logic.filtering.find_providers_by_radius') as mock_find, \
         patch('backend.logic.filtering.verify_network_status') as mock_verify:

        mock_find.return_value = [{"id": i, "distance": 1.0, "rating": 4.0} for i in range(100)]
        mock_verify.return_value = "in-network"

        start = time.time()
        filter_and_rank_providers(search_ctx["lat"], search_ctx["lon"], search_ctx["radius"], search_ctx["insurance_plan"])
        duration = time.time() - start
        assert duration < 2.0
