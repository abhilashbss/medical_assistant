import math

def calculate_distance(lat1, lon1, lat2, lon2):
    """Haversine distance in km."""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    a = max(0, min(1, a))
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def rank_providers(providers, user_lat, user_lon):
    """
    Ranks providers based on distance and rating.

    Lower distance is better.
    Higher rating is better.

    Score = (Rating * 10) - Distance
    """
    ranked = []
    for provider in providers:
        dist = calculate_distance(user_lat, user_lon, provider["lat"], provider["lon"])
        # Simple scoring: Rating weight (10) vs Distance
        score = (provider.get("rating", 0) * 10) - dist

        # Attach distance and score for transparency/sorting
        provider_data = provider.copy()
        provider_data["distance_km"] = dist
        provider_data["rank_score"] = score
        ranked.append(provider_data)

    # Sort by score descending
    return sorted(ranked, key=lambda x: x["rank_score"], reverse=True)
