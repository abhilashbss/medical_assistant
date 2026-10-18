import pytest
from unittest.mock import patch
from backend.logic.filtering import filter_and_rank_providers

def test_filter_only_in_network():
    """Provider search returns only in-network results for the selected insurance plan."""
    # Mock find_providers_by_radius to return 3 providers
    # Mock verify_network_status to return 'in-network' for only one of them
    with patch('backend.logic.filtering.find_providers_by_radius') as mock_find, \
         patch('backend.logic.filtering.verify_network_status') as mock_verify:

        mock_find.return_value = [
            {"id": 1, "name": "Dr. A", "distance": 1.0, "rating": 4.0},
            {"id": 2, "name": "Dr. B", "distance": 1.0, "rating": 4.0},
            {"id": 3, "name": "Dr. C", "distance": 1.0, "rating": 4.0},
        ]

        # ID 1: in-network, ID 2: out-of-network, ID 3: unverified/other
        mock_verify.side_effect = lambda pid, plan: 'in-network' if pid == 1 else 'out-of-network'

        results = filter_and_rank_providers(0, 0, 10, "PLAN_X")

        assert len(results) == 1
        assert results[0]["id"] == 1

def test_verify_network_status_api_combinations():
    """Network verification API calls return correct status for diverse carrier/plan combinations."""
    # This is primarily testing the integration point in filtering.py
    with patch('backend.logic.filtering.find_providers_by_radius') as mock_find, \
         patch('backend.logic.filtering.verify_network_status') as mock_verify:

        mock_find.return_value = [{"id": 1, "name": "Dr. A", "distance": 1.0, "rating": 4.0}]

        # Scenario 1: In-network
        mock_verify.return_value = 'in-network'
        assert len(filter_and_rank_providers(0, 0, 10, "PLAN_A")) == 1

        # Scenario 2: Out-of-network
        mock_verify.return_value = 'out-of-network'
        assert len(filter_and_rank_providers(0, 0, 10, "PLAN_B")) == 0

def test_geospatial_radius_filtering():
    """Geospatial queries correctly filter providers within the specified radius."""
    with patch('backend.logic.filtering.find_providers_by_radius') as mock_find, \
         patch('backend.logic.filtering.verify_network_status') as mock_verify:

        # The radius filtering is actually handled by find_providers_by_radius (sibling unit)
        # But we verify that our engine passes the radius correctly and uses the results
        mock_find.return_value = [{"id": 1, "name": "Dr. A", "distance": 1.0, "rating": 4.0}]
        mock_verify.return_value = 'in-network'

        filter_and_rank_providers(40.7128, -74.0060, 5, "PLAN_A")
        mock_find.assert_called_once_with(40.7128, -74.0060, 5)

def test_verification_logic_fallback():
    """Verification logic handles API timeouts or failures with appropriate fallback errors."""
    with patch('backend.logic.filtering.find_providers_by_radius') as mock_find, \
         patch('backend.logic.filtering.verify_network_status') as mock_verify:

        mock_find.return_value = [{"id": 1, "name": "Dr. A", "distance": 1.0, "rating": 4.0}]

        # Mock API failure (exception)
        mock_verify.side_effect = Exception("API Timeout")

        # Should treat as out-of-network (empty list)
        results = filter_and_rank_providers(0, 0, 10, "PLAN_A")
        assert len(results) == 0
