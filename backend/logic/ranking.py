def calculate_score(distance: float, rating: float) -> float:
    """
    Calculate a provider score where higher is better.
    Weights:
    - Distance (lower is better): Inverse relation.
    - Rating (higher is better): Direct relation.
    """
    # Avoid division by zero for distance
    dist_score = 1.0 / (distance + 0.1)
    # Normalize rating (assuming 0-5 scale)
    rating_score = rating / 5.0

    # Score = (Weight_Dist * Dist_Score) + (Weight_Rating * Rating_Score)
    # Using 0.6 for distance and 0.4 for rating as a default balance
    return (0.6 * dist_score) + (0.4 * rating_score)

def rank_providers(providers: list) -> list:
    """Sort providers by calculated score in descending order."""
    return sorted(
        providers,
        key=lambda p: calculate_score(p.get('distance', 10.0), p.get('rating', 0.0)),
        reverse=True
    )
