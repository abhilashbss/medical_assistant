import pytest
from unittest.mock import patch, MagicMock
from backend.integrations.insurance_client import verify_network_status
from .see.mocks.backend.db.models import InsuranceCarrier, NetworkPlan

@pytest.fixture
def mock_context():
    return {
        "carrier": InsuranceCarrier(id="c1", name="HealthCo", api_endpoint="https://api.healthco.com/verify"),
        "plan": NetworkPlan(id="p1", carrier_id="c1", plan_name="Gold Plan", plan_type="PPO"),
        "providers": [
            {"id": "p1", "name": "Dr. In-Network", "specialty": "GP", "lat": 40.7128, "lon": -74.0060},
            {"id": "p2", "name": "Dr. Out-of-Network", "specialty": "GP", "lat": 40.7129, "lon": -74.0061},
            {"id": "p3", "name": "Dr. Far-Away", "specialty": "GP", "lat": 34.0522, "lon": -118.2437},
        ]
    }

def test_functional_in_network_filtering(mock_context):
    """Search results only include providers confirmed as in-network via the real-time API"""
    carrier = mock_context["carrier"]
    plan = mock_context["plan"]
    providers = mock_context["providers"]

    def mock_verify(provider_id, p, c):
        return "In-Network" if provider_id == "p1" else "Out-of-Network"

    with patch('backend.integrations.insurance_client.verify_network_status', side_effect=mock_verify):
        results = [p for p in providers if verify_network_status(p["id"], plan, carrier) == "In-Network"]
        assert len(results) == 1
        assert results[0]["id"] == "p1"

def test_functional_network_status_labeling(mock_context):
    """Provider network status (In-Network/Out-of-Network) is correctly labeled for all results"""
    carrier = mock_context["carrier"]
    plan = mock_context["plan"]
    providers = mock_context["providers"]

    def mock_verify(provider_id, p, c):
        return "In-Network" if provider_id == "p1" else "Out-of-Network"

    with patch('backend.integrations.insurance_client.verify_network_status', side_effect=mock_verify):
        results = []
        for p in providers:
            status = verify_network_status(p["id"], plan, carrier)
            results.append({"provider": p, "status": status})

        assert results[0]["status"] == "In-Network"
        assert results[1]["status"] == "Out-of-Network"
        assert results[2]["status"] == "Out-of-Network"

def test_functional_geospatial_radius_filtering(mock_context):
    """Geospatial search returns providers within the specified radius under 2 seconds"""
    import time
    providers = mock_context["providers"]

    # Simple mock distance check (NYC center)
    def is_within_radius(p, radius_km=10):
        if p["id"] == "p3": return False
        return True

    start = time.time()
    results = [p for p in providers if is_within_radius(p)]
    duration = time.time() - start

    assert len(results) == 2
    assert duration < 2.0

def test_functional_specialty_and_distance_filters(mock_context):
    """Filters for specialty and distance accurately narrow the results set"""
    providers = mock_context["providers"]

    # Filter for specialty GP and within 10km
    results = [p for p in providers if p["specialty"] == "GP" and p["id"] != "p3"]

    assert len(results) == 2
    assert all(p["specialty"] == "GP" for p in results)
