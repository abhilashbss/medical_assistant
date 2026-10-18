def rank_providers(providers):
    """
    Ranks providers based on distance and rating.

    Scoring formula:
    Score = (Rating * 0.7) + ((1 / (1 + Distance)) * 0.3)

    Higher score is better.
    """
    ranked_providers = []

    for provider in providers:
        rating = provider.get("rating", 0)
        distance = provider.get("distance", float('inf'))

        # Normalizing distance: smaller distance gives a higher value between 0 and 1
        distance_score = 1 / (1 + distance)

        # Weights: Rating 70%, Distance 30%
        score = (rating * 0.7) + (distance_score * 0.3)

        # Create a copy of provider with the calculated score
        provider_with_score = provider.copy()
        provider_with_score["rank_score"] = score
        ranked_providers.append(provider_with_score)

    # Sort by score in descending order
    ranked_providers.sort(key=lambda x: x["rank_score"], reverse=True)

    return ranked_providers
