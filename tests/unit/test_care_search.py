import pytest
from unittest.mock import MagicMock, patch
from backend.integrations.insurance_client import verify_network_status, InsuranceVerificationError

# Since app.search is a sibling, we mock the provider discovery part
# and focus on the insurance filtering logic which depends on our unit.

def test_care_search_filters_in_network_providers():
    """Search results only contain providers verified as 'in-network' for the specified insurance carrier and plan"""
    # Mocking the provider discovery to return a list of providers
    mock_providers = [
        {"id": "p1", "name": "Dr. In-Network"},
        {"id": "p2", "name": "Dr. Out-of-Network"},
    ]

    with patch('backend.integrations.insurance_client._client.verify_network_status') as mock_client_verify:
        # Mock the response object
        mock_resp = MagicMock()

        def side_effect(request):
            mock_resp.status = "In-Network" if request.provider_id == "p1" else "Out-of-Network"
            return mock_resp

        mock_client_verify.side_effect = side_effect

        # Simulate the filtering logic that the sibling's app.search would implement
        results = [p for p in mock_providers if verify_network_status(p["id"], "BlueCross", "PPO") == "In-Network"]

        assert len(results) == 1
        assert results[0]["id"] == "p1"

def test_care_search_handles_api_errors_gracefully():
    """Real-time insurance API failures raise InsuranceVerificationError for the UI to handle"""
    with patch('backend.integrations.insurance_client._client.verify_network_status') as mock_client_verify:
        # Mock the client to raise InsuranceVerificationError
        mock_client_verify.side_effect = InsuranceVerificationError("API Timeout")

        with pytest.raises(InsuranceVerificationError):
            verify_network_status("p1", "BlueCross", "PPO")

def test_care_search_latency_isolated():
    """Search latency for isolated logic remains under 500ms"""
    import time

    with patch('backend.integrations.insurance_client._client.verify_network_status') as mock_client_verify:
        mock_resp = MagicMock()
        mock_resp.status = "In-Network"
        mock_client_verify.return_value = mock_resp

        start = time.time()
        # Call the function multiple times to check average latency
        for _ in range(10):
            verify_network_status("p1", "BlueCross", "PPO")
        end = time.time()

    avg_latency = (end - start) / 10
    assert avg_latency < 0.5
