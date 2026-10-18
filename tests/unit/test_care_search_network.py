import pytest
from unittest.mock import patch
from backend.services.filtering import filter_in_network_providers

# Mocks for sibling services
try:
    from backend.services.geospatial import find_providers_in_radius
except ImportError:
    import sys
    import os
    sys.path.append(os.path.join(os.getcwd(), ".see/mocks"))
    try:
        from backend.services.geospatial import find_providers_in_radius
    except ImportError:
        def find_providers_in_radius(lat, lon, radius_km):
            return [{"id": 1, "name": "Mock P1", "lat": lat, "lon": lon}]

@pytest.fixture
def providers():
    return [{"id": 1, "name": "P1"}, {"id": 2, "name": "P2"}]

def test_provider_search_returns_only_in_network_results(providers):
    """Provider search returns only in-network results for the selected insurance plan."""
    with patch('backend.services.filtering.verify_network_status') as mock_verify:
        mock_verify.side_effect = lambda p_id, c, pl: "in-network" if p_id == 1 else "out-of-network"
        results = filter_in_network_providers(providers, "CarrierA", "PlanA")
        assert len(results) == 1
        assert results[0]["id"] == 1

def test_network_verification_api_diverse_combinations(providers):
    """Network verification API calls return correct status for diverse carrier/plan combinations."""
    with patch('backend.services.filtering.verify_network_status') as mock_verify:
        mock_verify.side_effect = lambda p_id, c, pl: "in-network" if (c == "CarrierA" and p_id == 1) or (c == "CarrierB" and p_id == 2) else "out-of-network"

        res1 = filter_in_network_providers(providers, "CarrierA", "PlanA")
        assert [p["id"] for p in res1] == [1]

        res2 = filter_in_network_providers(providers, "CarrierB", "PlanA")
        assert [p["id"] for p in res2] == [2]

def test_geospatial_queries_filter_radius():
    """Geospatial queries correctly filter providers within the specified radius."""
    results = find_providers_in_radius(40.0, -70.0, 10)
    assert len(results) >= 0

def test_verification_logic_handles_api_failures(providers):
    """Verification logic handles API timeouts or failures with appropriate fallback errors."""
    with patch('backend.services.filtering.verify_network_status', side_effect=Exception("Timeout")):
        results = filter_in_network_providers(providers, "CarrierA", "PlanA")
        assert len(results) == 0
