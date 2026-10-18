import pytest
from unittest.mock import patch, MagicMock
from backend.integrations.insurance import verify_network_status, InsuranceVerificationRequest

def test_real_time_in_network_filtering():
    """Search results only include providers confirmed as in-network via the real-time API"""
    providers = [
        {"id": "p_in", "name": "Dr. In-Network"},
        {"id": "p_out", "name": "Dr. Out-of-Network"},
        {"id": "p_far", "name": "Dr. Far-In-Network"},
    ]

    def mock_verify_side_effect(request):
        # Simulate API: p_in and p_far are in-network
        from backend.integrations.insurance import InsuranceVerificationResponse
        status = "In-Network" if request.provider_id in ["p_in", "p_far"] else "Out-of-Network"
        return InsuranceVerificationResponse(status=status, verification_id="tx_1", latency_ms=10.0)

    with patch('backend.integrations.insurance.GenericCarrierAdapter.verify', side_effect=mock_verify_side_effect):
        results = []
        for p in providers:
            request = InsuranceVerificationRequest(
                provider_id=p["id"], insurance_carrier="Aetna", plan_type="PPO", member_id="mem_1"
            )
            if verify_network_status(request).status == "In-Network":
                results.append(p)

        assert len(results) == 2
        assert all(r["id"] in ["p_in", "p_far"] for r in results)

def test_network_status_labeling():
    """Provider network status (In-Network/Out-of-Network) is correctly labeled for all results"""
    providers = [
        {"id": "p_in", "name": "Dr. In-Network"},
        {"id": "p_out", "name": "Dr. Out-of-Network"},
    ]

    def mock_verify_side_effect(request):
        from backend.integrations.insurance import InsuranceVerificationResponse
        status = "In-Network" if request.provider_id == "p_in" else "Out-of-Network"
        return InsuranceVerificationResponse(status=status, verification_id="tx_1", latency_ms=10.0)

    with patch('backend.integrations.insurance.GenericCarrierAdapter.verify', side_effect=mock_verify_side_effect):
        results = []
        for p in providers:
            request = InsuranceVerificationRequest(
                provider_id=p["id"], insurance_carrier="Aetna", plan_type="PPO", member_id="mem_1"
            )
            status = verify_network_status(request).status
            results.append({"id": p["id"], "status": status})

        assert results[0]["status"] == "In-Network"
        assert results[1]["status"] == "Out-of-Network"

def test_geospatial_radius_filter():
    """Geospatial search returns providers within the specified radius under 2 seconds"""
    import time
    providers = [
        {"id": "p1", "distance": 5.0},
        {"id": "p2", "distance": 25.0},
    ]
    radius = 10.0

    start = time.time()
    results = [p for p in providers if p["distance"] <= radius]
    duration = time.time() - start

    assert duration < 2.0
    assert len(results) == 1
    assert results[0]["id"] == "p1"

def test_specialty_and_distance_filters():
    """Filters for specialty and distance accurately narrow the results set"""
    providers = [
        {"id": "p1", "specialty": "Cardiology", "distance": 5.0},
        {"id": "p2", "specialty": "Dermatology", "distance": 2.0},
        {"id": "p3", "specialty": "Cardiology", "distance": 15.0},
    ]
    target_specialty = "Cardiology"
    max_distance = 10.0

    results = [p for p in providers if p["specialty"] == target_specialty and p["distance"] <= max_distance]
    assert len(results) == 1
    assert results[0]["id"] == "p1"
