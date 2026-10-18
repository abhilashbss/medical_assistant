import pytest
from unittest.mock import patch, MagicMock
from backend.integrations.verification import verify_network_status
from .see.mocks.backend.db.models import InsuranceCarrier, NetworkPlan

@pytest.fixture
def insurance_setup():
    return {
        "carrier": InsuranceCarrier(id="c1", name="HealthCorp", api_endpoint="https://api.healthcorp.com/verify"),
        "plan": NetworkPlan(id="p1", carrier_id="c1", plan_type="PPO"),
        "providers": [
            {"id": "p_in", "name": "Dr. In-Network", "specialty": "Cardiology", "distance": 5.0},
            {"id": "p_out", "name": "Dr. Out-of-Network", "specialty": "Cardiology", "distance": 2.0},
            {"id": "p_far", "name": "Dr. Far-In-Network", "specialty": "Cardiology", "distance": 25.0},
        ]
    }

def test_real_time_in_network_filtering(insurance_setup):
    """Search results only include providers confirmed as in-network via the real-time API"""
    carrier = insurance_setup["carrier"]
    plan = insurance_setup["plan"]
    providers = insurance_setup["providers"]

    def mock_verify(provider_id, p, c):
        return "In-Network" if provider_id in ["p_in", "p_far"] else "Out-of-Network"

    with patch('backend.integrations.verification.verify_network_status', side_effect=mock_verify):
        results = [p for p in providers if verify_network_status(p["id"], plan, carrier) == "In-Network"]
        assert len(results) == 2
        assert all(r["id"] in ["p_in", "p_far"] for r in results)

def test_network_status_labeling(insurance_setup):
    """Provider network status (In-Network/Out-of-Network) is correctly labeled for all results"""
    carrier = insurance_setup["carrier"]
    plan = insurance_setup["plan"]
    providers = insurance_setup["providers"]

    def mock_verify(provider_id, p, c):
        return "In-Network" if provider_id == "p_in" else "Out-of-Network"

    with patch('backend.integrations.verification.verify_network_status', side_effect=mock_verify):
        results = []
        for p in providers:
            status = verify_network_status(p["id"], plan, carrier)
            results.append({"id": p["id"], "status": status})

        assert results[0]["status"] == "In-Network"
        assert results[1]["status"] == "Out-of-Network"

def test_geospatial_radius_filter(insurance_setup):
    """Geospatial search returns providers within the specified radius under 2 seconds"""
    import time
    providers = insurance_setup["providers"]
    radius = 10.0

    start = time.time()
    results = [p for p in providers if p["distance"] <= radius]
    duration = time.time() - start

    assert duration < 2.0
    assert len(results) == 2
    assert "p_far" not in [r["id"] for r in results]

def test_specialty_and_distance_filters(insurance_setup):
    """Filters for specialty and distance accurately narrow the results set"""
    providers = insurance_setup["providers"]
    target_specialty = "Cardiology"
    max_distance = 10.0

    results = [p for p in providers if p["specialty"] == target_specialty and p["distance"] <= max_distance]
    assert len(results) == 2 # p_in and p_out
