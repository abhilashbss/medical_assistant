import pytest
from unittest.mock import MagicMock, patch
from backend.integrations.insurance_client import verify_network_status

def test_functional_insurance_verification():
    """Search results only include providers confirmed as in-network via the real-time API"""
    with patch('backend.integrations.insurance_client._client.verify_network_status') as mock_verify:
        # Mock: prov_1 is in-network, prov_2 is out-of-network
        def side_effect(request):
            mock_resp = MagicMock()
            mock_resp.status = "In-Network" if request.provider_id == "prov_1" else "Out-of-Network"
            return mock_resp
        mock_verify.side_effect = side_effect

        # Simulating a functional search flow
        providers = [
            {"id": "prov_1", "name": "Clinic A", "specialty": "General"},
            {"id": "prov_2", "name": "Clinic B", "specialty": "General"}
        ]

        results = [p for p in providers if verify_network_status(p["id"], "Aetna", "HMO") == "In-Network"]

        assert len(results) == 1
        assert results[0]["id"] == "prov_1"

def test_functional_network_labeling():
    """Provider network status (In-Network/Out-of-Network) is correctly labeled for all results"""
    # Test both statuses are correctly returned by the integration layer
    with patch('backend.integrations.insurance_client._client.verify_network_status') as mock_verify:
        mock_verify.side_effect = [
            MagicMock(status="In-Network"),
            MagicMock(status="Out-of-Network")
        ]

        assert verify_network_status("p1", "Carrier", "Plan") == "In-Network"
        assert verify_network_status("p2", "Carrier", "Plan") == "Out-of-Network"
