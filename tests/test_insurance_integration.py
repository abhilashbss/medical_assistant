import pytest
from unittest.mock import MagicMock, patch
from backend.integrations.insurance_client import verify_network_status, InsuranceVerificationRequest, InsuranceClient
from backend.integrations.hipaa_transport import HIPAATransport
import time
import os

@pytest.fixture
def mock_transport():
    return MagicMock(spec=HIPAATransport)

@pytest.fixture
def client(mock_transport):
    return InsuranceClient(transport=mock_transport)

def test_verify_network_status_in_network(client, mock_transport):
    # Mock API response
    mock_response = MagicMock()
    mock_response.json.return_value = {"status": "In-Network"}
    mock_transport.safe_request.return_value = mock_response

    request = InsuranceVerificationRequest(
        provider_id="prov_123",
        insurance_carrier="BlueCross",
        plan_type="PPO"
    )

    response = client.verify_network_status(request)
    assert response.status == "In-Network"
    assert mock_transport.safe_request.call_count == 1

def test_verify_network_status_out_of_network(client, mock_transport):
    # Mock API response
    mock_response = MagicMock()
    mock_response.json.return_value = {"status": "Out-of-Network"}
    mock_transport.safe_request.return_value = mock_response

    request = InsuranceVerificationRequest(
        provider_id="prov_456",
        insurance_carrier="Aetna",
        plan_type="HMO"
    )

    response = client.verify_network_status(request)
    assert response.status == "Out-of-Network"

def test_verify_network_status_api_error(client, mock_transport):
    # Mock API failure
    mock_transport.safe_request.side_effect = Exception("API Timeout")

    request = InsuranceVerificationRequest(
        provider_id="prov_789",
        insurance_carrier="Cigna",
        plan_type="PPO"
    )

    response = client.verify_network_status(request)
    # Should fail-safe to Out-of-Network
    assert response.status == "Out-of-Network"

def test_verify_network_status_caching(client, mock_transport):
    # Mock API response
    mock_response = MagicMock()
    mock_response.json.return_value = {"status": "In-Network"}
    mock_transport.safe_request.return_value = mock_response

    request = InsuranceVerificationRequest(
        provider_id="prov_cache",
        insurance_carrier="Kaiser",
        plan_type="PPO"
    )

    # First call - should hit API
    client.verify_network_status(request)
    # Second call - should hit cache
    client.verify_network_status(request)

    assert mock_transport.safe_request.call_count == 1

def test_exported_verify_network_status_function():
    with patch('backend.integrations.insurance_client._client') as mock_client:
        mock_resp = MagicMock()
        mock_resp.status = "In-Network"
        mock_client.verify_network_status.return_value = mock_resp

        status = verify_network_status("p1", "c1", "t1")
        assert status == "In-Network"
        mock_client.verify_network_status.assert_called_once()
