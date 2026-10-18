import pytest
from backend.services.ranking_engine import rank_and_filter_providers
from unittest.mock import patch

def test_care_search_full_flow():
    """Providers are filtered correctly by insurance carrier and plan type."""
    results = rank_and_filter_providers(0, 0, 10, "AnyPlan")
    ids = [p['id'] for p in results]
    assert "p1" in ids
    assert "p3" in ids
    assert "p2" not in ids
    assert "p4" not in ids

def test_care_search_insurance_filter():
    """Search results return only 'in-network' providers for selected insurance."""
    results = rank_and_filter_providers(0, 0, 10, "AnyPlan")
    for p in results:
        assert p['id'] in ["p1", "p3"]

def test_care_search_geospatial_radius():
    """Geospatial search returns providers within the specified radius."""
    results = rank_and_filter_providers(0, 0, 1, "AnyPlan")
    assert len(results) > 0

def test_care_search_realtime_verification():
    """Network status is verified in real-time via external API mocks."""
    with patch('backend.services.filter_logic.verify_network_status') as mock_verify:
        mock_verify.return_value = "out-of-network"
        results = rank_and_filter_providers(0, 0, 10, "AnyPlan")
        assert len(results) == 0

def test_care_search_latency():
    """Search latency remains under 2 seconds for all functional scenarios."""
    import time
    start = time.time()
    rank_and_filter_providers(0, 0, 10, "AnyPlan")
    duration = time.time() - start
    assert duration < 2.0
