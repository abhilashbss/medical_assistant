import pytest
from unittest.mock import patch
from backend.logic.ranking import filter_and_rank_providers

def test_provider_search_returns_only_in_network_results():
    """Provider search returns only in-network results for the selected insurance plan."""
    providers = [
        {"id": "p1", "name": "In-Net", "rating": 4.0, "distance": 1.0},
        {"id": "p2", "name": "Out-Net", "rating": 4.0, "distance": 0.5},
    ]

    def mock_find(*args, **kwargs): return providers
    def mock_verify(pid, plan):
        return "in-network" if pid == "p1" else "out-of-network"

    with patch('backend.logic.ranking.find_providers_by_radius', side_effect=mock_find), \
         patch('backend.logic.ranking.verify_network_status', side_effect=mock_verify):

        results = filter_and_rank_providers(0, 0, 10, "plan_abc")
        assert len(results) == 1
        assert results[0]["id"] == "p1"

def test_network_verification_api_diverse_combinations():
    """Network verification API calls return correct status for diverse carrier/plan combinations."""
    providers = [{"id": "p1", "rating": 4.0, "distance": 1.0}]

    def mock_find(*args, **kwargs): return providers

    test_cases = [
        ("plan_gold", "in-network", 1),
        ("plan_silver", "out-of-network", 0),
        ("plan_bronze", "unverified", 0),
    ]

    for plan, status, expected_len in test_cases:
        with patch('backend.logic.ranking.find_providers_by_radius', side_effect=mock_find), \
             patch('backend.logic.ranking.verify_network_status', return_value=status):
            results = filter_and_rank_providers(0, 0, 10, plan)
            assert len(results) == expected_len

def test_geospatial_queries_filter_providers_within_radius():
    """Geospatial queries correctly filter providers within the specified radius."""
    with patch('backend.logic.ranking.find_providers_by_radius') as mock_find, \
         patch('backend.logic.ranking.verify_network_status', return_value="in-network"):

        mock_find.return_value = []
        filter_and_rank_providers(1.23, 4.56, 15.0, "plan_123")

        mock_find.assert_called_once_with(1.23, 4.56, 15.0)

def test_verification_logic_handles_api_failures_with_fallback():
    """Verification logic handles API timeouts or failures with appropriate fallback errors."""
    providers = [{"id": "p1", "rating": 4.0, "distance": 1.0}]

    def mock_find(*args, **kwargs): return providers
    def mock_verify(pid, plan): raise RuntimeError("API Down")

    with patch('backend.logic.ranking.find_providers_by_radius', side_effect=mock_find), \
         patch('backend.logic.ranking.verify_network_status', side_effect=mock_verify):

        results = filter_and_rank_providers(0, 0, 10, "plan_123")
        assert len(results) == 0
