import pytest
from backend.services.ranking_engine import rank_and_filter_providers as rank_providers

def test_rank_providers_sorting():
    """Verify that providers are sorted by score in descending order."""
    providers = [
        {"id": "p1", "rating": 4.0, "distance": 10.0}, # Mid rating, far
        {"id": "p2", "rating": 5.0, "distance": 1.0},  # High rating, near
        {"id": "p3", "rating": 2.0, "distance": 0.1},  # Low rating, very near
    ]

    ranked = rank_providers(providers)

    assert ranked[0]["id"] == "p2" # High rating + Near should win
    assert ranked[-1]["id"] == "p3" # Low rating should likely lose despite distance
    assert ranked[0]["rank_score"] > ranked[1]["rank_score"] > ranked[2]["rank_score"]

def test_rank_providers_distance_impact():
    """Verify that distance influences ranking when ratings are identical."""
    providers = [
        {"id": "p1", "rating": 4.5, "distance": 5.0},
        {"id": "p2", "rating": 4.5, "distance": 1.0},
    ]

    ranked = rank_providers(providers)

    assert ranked[0]["id"] == "p2"
    assert ranked[0]["rank_score"] > ranked[1]["rank_score"]

def test_rank_providers_rating_impact():
    """Verify that rating influences ranking when distance is identical."""
    providers = [
        {"id": "p1", "rating": 3.0, "distance": 2.0},
        {"id": "p2", "rating": 5.0, "distance": 2.0},
    ]

    ranked = rank_providers(providers)

    assert ranked[0]["id"] == "p2"
    assert ranked[0]["rank_score"] > ranked[1]["rank_score"]
