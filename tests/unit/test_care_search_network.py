import pytest
from backend.services.filtering import filter_in_network_providers
from unittest.mock import patch

def test_filter_only_in_network():
    """Verify that providers with 'out-of-network' status are strictly excluded."""
    providers = [
        {"id": "p1", "name": "Dr. In"},
        {"id": "p2", "name": "Dr. Out"},
        {"id": "p3", "name": "Dr. In2"},
    ]

    # Mock verify_network_status to return 'in-network' for p1, p3 and 'out-of-network' for p2
    def mock_verify(provider_id, carrier, plan):
        return "in-network" if provider_id in ["p1", "p3"] else "out-of-network"

    with patch("backend.services.filtering.verify_network_status", side_effect=mock_verify):
        results = filter_in_network_providers(providers, "BlueCross", "PPO")

        assert len(results) == 2
        ids = [p["id"] for p in results]
        assert "p1" in ids
        assert "p3" in ids
        assert "p2" not in ids

def test_filter_api_failure_fallback():
    """Verify that API timeouts or failures are treated as out-of-network."""
    providers = [
        {"id": "p1", "name": "Dr. Fail"},
    ]

    def mock_verify_fail(provider_id, carrier, plan):
        raise Exception("API Timeout")

    with patch("backend.services.filtering.verify_network_status", side_effect=mock_verify_fail):
        results = filter_in_network_providers(providers, "BlueCross", "PPO")

        assert len(results) == 0

def test_filter_unverified_status():
    """Verify that 'unverified' status is treated as out-of-network."""
    providers = [
        {"id": "p1", "name": "Dr. Unverified"},
    ]

    def mock_verify_unverified(provider_id, carrier, plan):
        return "unverified"

    with patch("backend.services.filtering.verify_network_status", side_effect=mock_verify_unverified):
        results = filter_in_network_providers(providers, "BlueCross", "PPO")

        assert len(results) == 0
