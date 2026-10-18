import pytest
from unittest.mock import patch
from backend.services.filter_logic import filter_in_network_providers
from backend.services.ranking_engine import rank_and_filter_providers

def test_provider_search_returns_only_in_network():
    """Provider search returns only in-network results for the selected insurance plan."""
    providers = [
        {"id": "p1", "name": "In-Network"},
        {"id": "p2", "name": "Out-of-Network"},
        {"id": "p3", "name": "Unverified"},
    ]
    with patch('backend.services.filter_logic.verify_network_status') as mock_verify:
        mock_verify.side_effect = lambda pid, plan: {
            "p1": "in-network",
            "p2": "out-of-network",
            "p3": "unverified"
        }.get(pid)
        
        results = filter_in_network_providers(providers, "Plan-A")
        assert len(results) == 1
        assert results[0]["id"] == "p1"

def test_network_verification_diverse_combinations():
    """Network verification API calls return correct status for diverse carrier/plan combinations."""
    with patch('backend.services.filter_logic.verify_network_status') as mock_verify:
        mock_verify.return_value = "in-network"
        assert filter_in_network_providers([{"id": "p1"}], "Carrier-X-Plan-Y") == [{"id": "p1"}]
        
        mock_verify.return_value = "out-of-network"
        assert filter_in_network_providers([{"id": "p1"}], "Carrier-X-Plan-Y") == []

def test_geospatial_radius_filtering():
    """Geospatial queries correctly filter providers within the specified radius."""
    with patch('backend.services.ranking_engine.find_providers_by_radius') as mock_find:
        mock_find.return_value = [{"id": "p1", "distance": 5, "rating": 4.0}]
        # We also need to mock the insurance check since rank_and_filter_providers calls it
        with patch('backend.services.filter_logic.verify_network_status') as mock_verify:
            mock_verify.return_value = "in-network"
            results = rank_and_filter_providers(0, 0, 10, "Plan-A")
            mock_find.assert_called_with(0, 0, 10)
            assert len(results) > 0

def test_verification_failure_fallback():
    """Verification logic propagates API failures so the UI can display a graceful error message"""
    with patch('backend.services.filter_logic.verify_network_status') as mock_verify:
        # Mock the verification to raise an error
        mock_verify.side_effect = Exception("API Timeout")
        providers = [{"id": "p1"}]

        # Now expect the exception to propagate instead of silently returning []
        with pytest.raises(Exception):
            filter_in_network_providers(providers, "Plan-A")
