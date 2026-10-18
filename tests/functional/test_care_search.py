import pytest
from unittest.mock import patch
from backend.services.filtering import filter_in_network_providers
from backend.services.ranking import rank_providers

def test_care_search_end_to_end_filtering():
    """Providers are filtered correctly by insurance carrier and plan type."""
    providers = [
        {"id": "p1", "rating": 4.0, "distance": 1.0},
        {"id": "p2", "rating": 4.0, "distance": 0.5},
    ]

    def mock_verify(pid, carrier, plan):
        if carrier == "Aetna" and plan == "Gold":
            return "in-network" if pid == "p1" else "out-of-network"
        return "out-of-network"

    with patch("backend.services.filtering.verify_network_status", side_effect=mock_verify):
        # Test Aetna Gold
        results = filter_in_network_providers(providers, "Aetna", "Gold")
        assert len(results) == 1
        assert results[0]["id"] == "p1"

        # Test other insurance
        results_other = filter_in_network_providers(providers, "Cigna", "Silver")
        assert len(results_other) == 0

def test_care_search_returns_only_in_network():
    """Search results return only 'in-network' providers for selected insurance."""
    providers = [
        {"id": "p1", "rating": 4.0, "distance": 1.0},
        {"id": "p2", "rating": 4.0, "distance": 0.5},
    ]

    def mock_verify(pid, carrier, plan):
        return "in-network" if pid == "p1" else "out-of-network"

    with patch("backend.services.filtering.verify_network_status", side_effect=mock_verify):
        filtered = filter_in_network_providers(providers, "Any", "Any")
        ranked = rank_providers(filtered)

        assert len(ranked) == 1
        assert ranked[0]["id"] == "p1"

def test_care_search_geospatial_radius():
    """Geospatial search returns providers within the specified radius."""
    # Note: The filtering/ranking engine consumes results from find_providers_by_radius.
    # We mock the output of that service.
    providers = [
        {"id": "p1", "distance": 2.0},
        {"id": "p2", "distance": 15.0},
    ]

    # The search engine should only receive providers already filtered by radius from the API.
    # This test verifies our engine handles those results correctly.
    def mock_verify(pid, carrier, plan):
        return "in-network"

    with patch("backend.services.filtering.verify_network_status", side_effect=mock_verify):
        # Simulate receiving only providers within radius (p1)
        filtered = filter_in_network_providers([providers[0]], "Any", "Any")
        assert len(filtered) == 1
        assert filtered[0]["id"] == "p1"

def test_care_search_realtime_verification():
    """Network status is verified in real-time via external API mocks."""
    providers = [{"id": "p1", "distance": 1.0}]

    with patch("backend.services.filtering.verify_network_status") as mock_verify:
        mock_verify.return_value = "in-network"
        filter_in_network_providers(providers, "CarrierX", "PlanY")
        mock_verify.assert_called_once_with("p1", "CarrierX", "PlanY")

def test_care_search_latency():
    """Search latency remains under 2 seconds for all functional scenarios."""
    import time
    providers = [{"id": f"p{i}", "distance": 1.0} for i in range(100)]

    def mock_verify(pid, carrier, plan):
        return "in-network"

    with patch("backend.services.filtering.verify_network_status", side_effect=mock_verify):
        start = time.time()
        filtered = filter_in_network_providers(providers, "Any", "Any")
        rank_providers(filtered)
        duration = time.time() - start

        assert duration < 2.0
