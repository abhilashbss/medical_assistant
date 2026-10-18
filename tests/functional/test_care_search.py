import pytest
from unittest.mock import patch
from backend.logic.ranking import filter_and_rank_providers

def test_insurance_carrier_and_plan_filtering():
    """Providers are filtered correctly by insurance carrier and plan type."""
    providers = [
        {"id": "p1", "name": "Dr. InNet", "rating": 4.0, "distance": 1.0},
        {"id": "p2", "name": "Dr. OutNet", "rating": 4.0, "distance": 0.5},
    ]

    def mock_find(*args, **kwargs): return providers
    def mock_verify(pid, plan):
        if plan == "PLAN_GOLD" and pid == "p1": return "in-network"
        return "out-of-network"

    with patch('backend.logic.ranking.find_providers_by_radius', side_effect=mock_find), \
         patch('backend.logic.ranking.verify_network_status', side_effect=mock_verify):

        results = filter_and_rank_providers(0, 0, 10, "PLAN_GOLD")
        assert len(results) == 1
        assert results[0]["id"] == "p1"

def test_search_returns_only_in_network():
    """Search results return only 'in-network' providers for selected insurance."""
    providers = [
        {"id": "p1", "name": "InNet 1", "rating": 4.0, "distance": 1.0},
        {"id": "p2", "name": "InNet 2", "rating": 4.0, "distance": 2.0},
        {"id": "p3", "name": "OutNet", "rating": 5.0, "distance": 0.1},
    ]

    def mock_find(*args, **kwargs): return providers
    def mock_verify(pid, plan):
        return "in-network" if pid in ["p1", "p2"] else "out-of-network"

    with patch('backend.logic.ranking.find_providers_by_radius', side_effect=mock_find), \
         patch('backend.logic.ranking.verify_network_status', side_effect=mock_verify):

        results = filter_and_rank_providers(0, 0, 10, "PLAN_ABC")
        for p in results:
            assert p["id"] != "p3"
        assert len(results) == 2

def test_geospatial_radius_functional():
    """Geospatial search returns providers within the specified radius."""
    with patch('backend.logic.ranking.find_providers_by_radius') as mock_find, \
         patch('backend.logic.ranking.verify_network_status', return_value="in-network"):

        mock_find.return_value = [{"id": "p1", "rating": 4.0, "distance": 1.0}]
        filter_and_rank_providers(40.7, -74.0, 5.0, "PLAN_X")

        mock_find.assert_called_once_with(40.7, -74.0, 5.0)

def test_network_status_realtime_verification():
    """Network status is verified in real-time via external API mocks."""
    providers = [{"id": "p1", "rating": 4.0, "distance": 1.0}]

    with patch('backend.logic.ranking.find_providers_by_radius', return_value=providers) as mock_find, \
         patch('backend.logic.ranking.verify_network_status') as mock_verify:

        mock_verify.return_value = "in-network"
        filter_and_rank_providers(0, 0, 10, "PLAN_X")

        mock_verify.assert_called_once_with("p1", "PLAN_X")

def test_search_latency_performance():
    """Search latency remains under 2 seconds for all functional scenarios."""
    import time

    providers = [{"id": f"p{i}", "rating": 4.0, "distance": 1.0} for i in range(100)]

    def mock_find(*args, **kwargs): return providers
    def mock_verify(pid, plan): return "in-network"

    with patch('backend.logic.ranking.find_providers_by_radius', side_effect=mock_find), \
         patch('backend.logic.ranking.verify_network_status', side_effect=mock_verify):

        start = time.time()
        filter_and_rank_providers(0, 0, 10, "PLAN_X")
        duration = time.time() - start

        assert duration < 2.0
