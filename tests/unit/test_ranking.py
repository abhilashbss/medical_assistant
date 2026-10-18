import pytest
from backend.services.ranking_engine import rank_and_filter_providers

def test_rank_providers_sorting():
    """Verify that providers are sorted by score in descending order."""
    # Mock dependencies: We need to mock find_providers_by_radius and filter_in_network_providers
    # Since we are testing the ranking logic, we can mock the internal calls.
    with pytest.MonkeyPatch().context() as mp:
        # Mock find_providers_by_radius
        import backend.services.ranking_engine
        mp.setattr(backend.services.ranking_engine, "find_providers_by_radius", lambda *args: [
            {"id": "p1", "rating": 4.0, "distance": 10.0},
            {"id": "p2", "rating": 5.0, "distance": 1.0},
            {"id": "p3", "rating": 2.0, "distance": 0.1},
        ])
        # Mock filter_in_network_providers to return everything
        mp.setattr(backend.services.ranking_engine, "filter_in_network_providers", lambda p, plan: p)

        ranked = rank_and_filter_providers(0, 0, 10, "PlanA")

        assert ranked[0]["id"] == "p2" # High rating + Near should win
        assert ranked[-1]["id"] == "p3" # Low rating should likely lose despite distance
        assert ranked[0]["score"] > ranked[1]["score"] > ranked[2]["score"]

def test_rank_providers_distance_impact():
    """Verify that distance influences ranking when ratings are identical."""
    with pytest.MonkeyPatch().context() as mp:
        import backend.services.ranking_engine
        mp.setattr(backend.services.ranking_engine, "find_providers_by_radius", lambda *args: [
            {"id": "p1", "rating": 4.5, "distance": 5.0},
            {"id": "p2", "rating": 4.5, "distance": 1.0},
        ])
        mp.setattr(backend.services.ranking_engine, "filter_in_network_providers", lambda p, plan: p)

        ranked = rank_and_filter_providers(0, 0, 10, "PlanA")

        assert ranked[0]["id"] == "p2"
        assert ranked[0]["score"] > ranked[1]["score"]

def test_rank_providers_rating_impact():
    """Verify that rating influences ranking when distance is identical."""
    with pytest.MonkeyPatch().context() as mp:
        import backend.services.ranking_engine
        mp.setattr(backend.services.ranking_engine, "find_providers_by_radius", lambda *args: [
            {"id": "p1", "rating": 3.0, "distance": 2.0},
            {"id": "p2", "rating": 5.0, "distance": 2.0},
        ])
        mp.setattr(backend.services.ranking_engine, "filter_in_network_providers", lambda p, plan: p)

        ranked = rank_and_filter_providers(0, 0, 10, "PlanA")

        assert ranked[0]["id"] == "p2"
        assert ranked[0]["score"] > ranked[1]["score"]
