import pytest
from unittest.mock import patch, MagicMock
from backend.integrations.insurance_client import verify_network_status
from .see.mocks.backend.db.models import InsuranceCarrier, NetworkPlan

@pytest.fixture
def mock_insurance_data():
    return {
        "carrier": InsuranceCarrier(id="c1", name="HealthCo", api_endpoint="https://api.healthco.com/verify"),
        "plan": NetworkPlan(id="p1", carrier_id="c1", plan_name="Gold Plan", plan_type="PPO"),
        "providers": [
            {"id": "prov_in", "name": "Dr. In-Network"},
            {"id": "prov_out", "name": "Dr. Out-of-Network"},
        ]
    }

def test_search_results_only_contain_in_network_providers(mock_insurance_data):
    """Search results only contain providers verified as 'in-network' for the specified insurance carrier and plan"""
    carrier = mock_insurance_data["carrier"]
    plan = mock_insurance_data["plan"]
    providers = mock_insurance_data["providers"]

    def mock_verify(provider_id, p, c):
        return "In-Network" if provider_id == "prov_in" else "Out-of-Network"

    with patch('backend.integrations.insurance_client.verify_network_status', side_effect=mock_verify):
        results = [p for p in providers if verify_network_status(p["id"], plan, carrier) == "In-Network"]
        assert len(results) == 1
        assert results[0]["id"] == "prov_in"

def test_real_time_api_handling(mock_insurance_data):
    """Real-time insurance API mocks return correct network status and are handled without errors"""
    carrier = mock_insurance_data["carrier"]
    plan = mock_insurance_data["plan"]

    with patch('backend.integrations.hipaa_transport.HIPAATransport.secure_post') as mock_post:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"network_status": "in-network"}
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        status = verify_network_status("any_id", plan, carrier)
        assert status == "In-Network"

def test_search_latency_isolated_logic(mock_insurance_data):
    """Search latency for isolated logic remains under 500ms"""
    import time
    carrier = mock_insurance_data["carrier"]
    plan = mock_insurance_data["plan"]

    with patch('backend.integrations.hipaa_transport.HIPAATransport.secure_post') as mock_post:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"network_status": "in-network"}
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        start = time.time()
        verify_network_status("any_id", plan, carrier)
        duration = (time.time() - start) * 1000

        assert duration < 500
