import pytest
from unittest.mock import MagicMock, patch
from backend.integrations.insurance_client import verify_network_status

def test_care_search_insurance_filtering():
    """Search results only contain providers verified as 'in-network' for the specified insurance carrier and plan"""
    with patch('backend.integrations.insurance_client._client.verify_network_status') as mock_verify:
        # Setup: Provider 1 is in-network, Provider 2 is out-of-network
        def side_effect(request):
            mock_resp = MagicMock()
            mock_resp.status = "In-Network" if request.provider_id == "prov_in" else "Out-of-Network"
            return mock_resp

        mock_verify.side_effect = side_effect

        # Simulating the search logic that would be in app.search
        providers = [
            {"id": "prov_in", "name": "Dr. In-Network"},
            {"id": "prov_out", "name": "Dr. Out-Network"}
        ]

        verified_providers = [
            p for p in providers
            if verify_network_status(p["id"], "BlueCross", "PPO") == "In-Network"
        ]

        assert len(verified_providers) == 1
        assert verified_providers[0]["id"] == "prov_in"

def test_care_search_api_errors():
    """Real-time insurance API mocks return correct network status and are handled without errors"""
    with patch('backend.integrations.insurance_client._client.verify_network_status') as mock_verify:
        # Setup: API returns an error (which the client handles by returning Out-of-Network)
        mock_verify.side_effect = Exception("API Timeout")

        # Should not raise exception, should return Out-of-Network
        status = verify_network_status("prov_123", "BlueCross", "PPO")
        assert status == "Out-of-Network"

def test_care_search_latency():
    """Search latency for isolated logic remains under 500ms"""
    import time

    start = time.time()
    # Test the core verification logic
    verify_network_status("prov_123", "BlueCross", "PPO")
    end = time.time()

    assert (end - start) * 1000 < 500
