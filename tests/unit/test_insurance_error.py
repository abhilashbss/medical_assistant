import pytest
from unittest.mock import MagicMock
from backend.integrations.insurance_client import InsuranceClient, InsuranceVerificationRequest, InsuranceVerificationError

def test_verify_network_status_raises_error_on_transport_failure():
    # Mock transport that raises an exception
    mock_transport = MagicMock()
    mock_transport.safe_request.side_effect = Exception("API 500 Internal Server Error")
    
    client = InsuranceClient(transport=mock_transport)
    request = InsuranceVerificationRequest(
        provider_id="P1", 
        insurance_carrier="CarrierA", 
        plan_type="PPO"
    )
    
    with pytest.raises(InsuranceVerificationError) as excinfo:
        client.verify_network_status(request)
    
    assert "Failed to verify network status" in str(excinfo.value)

def test_exported_verify_network_status_propagates_error():
    # Mock the internal client
    import backend.integrations.insurance_client as ic
    original_client = ic._client
    
    mock_client = MagicMock()
    mock_client.verify_network_status.side_effect = InsuranceVerificationError("Verification failed")
    ic._client = mock_client
    
    with pytest.raises(InsuranceVerificationError):
        ic.verify_network_status("P1", "CarrierA", "PPO")
    
    # Restore original client
    ic._client = original_client
