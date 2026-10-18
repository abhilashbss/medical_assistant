import pytest
import os
from unittest.mock import patch, MagicMock
from backend.integrations.insurance import (
    verify_network_status,
    InsuranceVerificationRequest,
    InsuranceVerificationResponse
)
import logging

def test_verify_network_status_in_network():
    """Verify that an in-network provider is correctly identified."""
    request = InsuranceVerificationRequest(
        provider_id="prov_123",
        insurance_carrier="Aetna",
        plan_type="PPO",
        member_id="mem_456"
    )

    with patch('requests.post') as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"is_in_network": True, "tx_id": "tx_abc"}
        mock_post.return_value = mock_response

        result = verify_network_status(request)

        assert result.status == "In-Network"
        assert result.verification_id == "tx_abc"

def test_verify_network_status_out_of_network():
    """Verify that an out-of-network provider is correctly identified."""
    request = InsuranceVerificationRequest(
        provider_id="prov_123",
        insurance_carrier="Aetna",
        plan_type="PPO",
        member_id="mem_456"
    )

    with patch('requests.post') as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"is_in_network": False, "tx_id": "tx_def"}
        mock_post.return_value = mock_response

        result = verify_network_status(request)

        assert result.status == "Out-of-Network"
        assert result.verification_id == "tx_def"

def test_verify_network_status_api_error():
    """Verify that API errors are handled gracefully and return 'Error' status."""
    request = InsuranceVerificationRequest(
        provider_id="prov_123",
        insurance_carrier="Aetna",
        plan_type="PPO",
        member_id="mem_456"
    )

    with patch('requests.post') as mock_post:
        mock_post.side_effect = Exception("API Down")

        result = verify_network_status(request)

        assert result.status == "Error"
        assert result.verification_id == "error"

def test_verify_network_status_timeout():
    """Verify that timeouts are handled and return 'Error' status."""
    request = InsuranceVerificationRequest(
        provider_id="prov_123",
        insurance_carrier="Aetna",
        plan_type="PPO",
        member_id="mem_456"
    )

    with patch('requests.post') as mock_post:
        import requests
        mock_post.side_effect = requests.exceptions.Timeout()

        result = verify_network_status(request)

        assert result.status == "Error"

def test_phi_no_leakage_in_logs():
    """Verify that no PHI (member_id) appears in the application logs."""
    request = InsuranceVerificationRequest(
        provider_id="prov_123",
        insurance_carrier="Aetna",
        plan_type="PPO",
        member_id="SECRET_PHI_123"
    )

    with patch('logging.Logger.error') as mock_log:
        with patch('requests.post') as mock_post:
            mock_post.side_effect = Exception("API Failure")
            verify_network_status(request)

            # Check all log calls to ensure PHI isn't there
            for call in mock_log.call_args_list:
                log_msg = str(call[0][0])
                assert "SECRET_PHI_123" not in log_msg

def test_caching_mechanism():
    """Verify that redundant API calls are reduced via caching."""
    request = InsuranceVerificationRequest(
        provider_id="prov_123",
        insurance_carrier="Aetna",
        plan_type="PPO",
        member_id="mem_456"
    )

    with patch('requests.post') as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"is_in_network": True, "tx_id": "tx_abc"}
        mock_post.return_value = mock_response

        # First call - should hit API
        verify_network_status(request)
        # Second call - should hit cache
        verify_network_status(request)

        assert mock_post.call_count == 1
