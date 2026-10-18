import pytest
from unittest.mock import patch
from backend.logic.ranking import filter_and_rank_providers

def test_filter_out_of_network():
    """Verify that providers with 'out-of-network' status are strictly excluded."""
    providers = [
        {"id": "p1", "name": "In Network", "rating": 5.0, "distance": 1.0},
        {"id": "p2", "name": "Out Network", "rating": 5.0, "distance": 0.5},
        {"id": "p3", "name": "Unverified", "rating": 5.0, "distance": 0.1},
    ]

    def mock_find(*args, **kwargs): return providers
    def mock_verify(pid, plan):
        mapping = {"p1": "in-network", "p2": "out-of-network", "p3": "unverified"}
        return mapping.get(pid, "unverified")

    with patch('backend.logic.ranking.find_providers_by_radius', side_effect=mock_find), \
         patch('backend.logic.ranking.verify_network_status', side_effect=mock_verify):

        results = filter_and_rank_providers(0, 0, 10, "plan_123")

        assert len(results) == 1
        assert results[0]["id"] == "p1"

def test_ranking_logic():
    """Verify that providers are ranked by rating and distance correctly."""
    providers = [
        {"id": "p1", "rating": 4.0, "distance": 5.0}, # Score: 40 - 5 = 35
        {"id": "p2", "rating": 5.0, "distance": 10.0}, # Score: 50 - 10 = 40
        {"id": "p3", "rating": 4.5, "distance": 2.0}, # Score: 45 - 2 = 43
    ]

    def mock_find(*args, **kwargs): return providers
    def mock_verify(pid, plan): return "in-network"

    with patch('backend.logic.ranking.find_providers_by_radius', side_effect=mock_find), \
         patch('backend.logic.ranking.verify_network_status', side_effect=mock_verify):

        results = filter_and_rank_providers(0, 0, 10, "plan_123")

        assert results[0]["id"] == "p3" # 43
        assert results[1]["id"] == "p2" # 40
        assert results[2]["id"] == "p1" # 35

def test_insurance_api_failure_fallback():
    """Verify that API timeouts or failures treat provider as out-of-network."""
    providers = [{"id": "p1", "rating": 5.0, "distance": 1.0}]

    def mock_find(*args, **kwargs): return providers
    def mock_verify(pid, plan): raise Exception("API Timeout")

    with patch('backend.logic.ranking.find_providers_by_radius', side_effect=mock_find), \
         patch('backend.logic.ranking.verify_network_status', side_effect=mock_verify):

        results = filter_and_rank_providers(0, 0, 10, "plan_123")

        assert len(results) == 0

def test_phi_not_logged():
    """Validate that PHI is not logged during filtering process."""
    providers = [{"id": "p1", "name": "Patient Private Name", "rating": 5.0, "distance": 1.0}]

    def mock_find(*args, **kwargs): return providers
    def mock_verify(pid, plan): raise Exception("Critical Error")

    with patch('backend.logic.ranking.find_providers_by_radius', side_effect=mock_find), \
         patch('backend.logic.ranking.verify_network_status', side_effect=mock_verify), \
         patch('backend.logic.ranking.logger') as mock_logger:

        filter_and_rank_providers(0, 0, 10, "plan_123")

        log_call = mock_logger.error.call_args[0][0]
        assert "Patient Private Name" not in log_call
