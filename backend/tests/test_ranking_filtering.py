import pytest
import time
from unittest.mock import patch
from backend.services.filtering import filter_in_network_providers
from backend.services.ranking import rank_providers

# Mocks for sibling services
try:
    from backend.services.geospatial import find_providers_in_radius
except ImportError:
    from .see.mocks.backend.services.geospatial import find_providers_in_radius

@pytest.fixture
def sample_providers():
    return [
        {"id": 1, "name": "Dr. In1", "lat": 40.7128, "lon": -74.0060, "rating": 5.0},
        {"id": 2, "name": "Dr. Out1", "lat": 40.7130, "lon": -74.0062, "rating": 4.0},
        {"id": 3, "name": "Dr. In2", "lat": 40.7150, "lon": -74.0080, "rating": 3.0},
        {"id": 4, "name": "Dr. Out2", "lat": 40.7200, "lon": -74.0100, "rating": 4.5},
    ]

def test_filter_in_network_providers_excludes_out_of_network(sample_providers):
    """Providers with 'out-of-network' status are strictly excluded from results."""
    # Mock verify_network_status: 1 and 3 are in, 2 and 4 are out
    with patch('backend.services.filtering.verify_network_status') as mock_verify:
        mock_verify.side_effect = lambda p_id, c, pl: "in-network" if p_id in [1, 3] else "out-of-network"

        results = filter_in_network_providers(sample_providers, "Aetna", "PPO")

        assert len(results) == 2
        assert all(p["id"] in [1, 3] for p in results)
        assert not any(p["id"] in [2, 4] for p in results)

def test_filter_in_network_providers_handles_api_failure(sample_providers):
    """Insurance API failures are treated as out-of-network (fail-closed)."""
    with patch('backend.services.filtering.verify_network_status') as mock_verify:
        mock_verify.side_effect = Exception("API Timeout")

        results = filter_in_network_providers(sample_providers, "Aetna", "PPO")

        assert len(results) == 0

def test_rank_providers_sorting(sample_providers):
    """Ranking algorithm prioritizes providers by distance and user rating."""
    user_lat, user_lon = 40.7128, -74.0060 # Matches Dr. In1

    ranked = rank_providers(sample_providers, user_lat, user_lon)

    # Dr. In1: dist=0, rating=5.0 -> score = 50 - 0 = 50
    # Dr. Out1: dist~0.02, rating=4.0 -> score = 40 - 0.02 = 39.98
    # Dr. In2: dist~0.2, rating=3.0 -> score = 30 - 0.2 = 29.8
    # Dr. Out2: dist~1, rating=4.5 -> score = 45 - 1 = 44

    # Expected order: In1 (50), Out2 (44), Out1 (39.98), In2 (29.8)
    assert ranked[0]["id"] == 1
    assert ranked[1]["id"] == 4
    assert ranked[2]["id"] == 2
    assert ranked[3]["id"] == 3

def test_filtering_and_ranking_latency():
    """Filtering and ranking latency for 1,000 providers is under 500ms."""
    # Create 1,000 providers
    providers = [{"id": i, "name": f"Dr.{i}", "lat": 40.0 + (i*0.001), "lon": -70.0 + (i*0.001), "rating": 4.0} for i in range(1000)]

    with patch('backend.services.filtering.verify_network_status') as mock_verify:
        mock_verify.return_value = "in-network"

        start = time.time()
        filtered = filter_in_network_providers(providers, "Aetna", "PPO")
        ranked = rank_providers(filtered, 40.0, -70.0)
        end = time.time()

        duration_ms = (end - start) * 1000
        assert duration_ms < 500, f"Latency too high: {duration_ms}ms"

def test_phi_not_logged():
    """Validate that PHI is not logged during the filtering process."""
    # This is a conceptual test. In a real scenario, we'd capture logs.
    # For this build unit, we ensure we don't log provider names or user details.
    with patch('backend.services.filtering.logger') as mock_logger:
        providers = [{"id": 1, "name": "SECRET PATIENT NAME", "lat": 0, "lon": 0}]
        with patch('backend.services.filtering.verify_network_status', side_effect=Exception("Fail")):
            filter_in_network_providers(providers, "Aetna", "PPO")

            # Check that the error log only contains the ID, not the name
            log_call = mock_logger.error.call_args[0][0]
            assert "SECRET PATIENT NAME" not in log_call
            assert "provider 1" in log_call
