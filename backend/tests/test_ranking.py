import pytest
from backend.logic.ranking import calculate_score, rank_providers

def test_calculate_score_distance():
    # Closer provider should have higher score
    score_near = calculate_score(0.1, 4.0)
    score_far = calculate_score(10.0, 4.0)
    assert score_near > score_far

def test_calculate_score_rating():
    # Higher rated provider should have higher score
    score_high = calculate_score(1.0, 5.0)
    score_low = calculate_score(1.0, 2.0)
    assert score_high > score_low

def test_rank_providers():
    providers = [
        {"id": 1, "distance": 5.0, "rating": 3.0}, # Low score
        {"id": 2, "distance": 0.1, "rating": 5.0}, # High score
        {"id": 3, "distance": 1.0, "rating": 4.0}, # Mid score
    ]
    ranked = rank_providers(providers)
    assert ranked[0]["id"] == 2
    assert ranked[1]["id"] == 3
    assert ranked[2]["id"] == 1
