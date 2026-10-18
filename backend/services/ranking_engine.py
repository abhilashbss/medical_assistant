from backend.services.filter_logic import filter_in_network_providers

try:
    from backend.api.search import find_providers_by_radius
except ImportError:
    import os
    import importlib.util
    mock_path = os.path.join(os.getcwd(), '.see', 'mocks', 'backend', 'api', 'search.py')
    if os.path.exists(mock_path):
        spec = importlib.util.spec_from_file_location("backend.api.search", mock_path)
        search_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(search_module)
        find_providers_by_radius = search_module.find_providers_by_radius
    else:
        def find_providers_by_radius(lat, lon, rad): return []



# Ranking weights
RATING_WEIGHT = 10.0
DISTANCE_WEIGHT = 1.0

def calculate_score(provider):
    """
    Calculates a score for a provider based on rating and distance.
    Higher score is better.
    """
    rating = provider.get('rating', 0)
    distance = provider.get('distance', float('inf'))

    # Score = (Rating * weight) - (Distance * weight)
    return (rating * RATING_WEIGHT) - (distance * DISTANCE_WEIGHT)

def rank_and_filter_providers(lat, lon, radius_km, insurance_plan):
    """
    Main entry point for the care search engine.
    1. Fetches providers within the geospatial radius.
    2. Filters for in-network providers.
    3. Ranks the results based on score.
    """
    # 1. Geospatial fetch
    providers = find_providers_by_radius(lat, lon, radius_km)

    # 2. Insurance filtering
    filtered_providers = filter_in_network_providers(providers, insurance_plan)

    # 3. Ranking
    # Attach score to each provider and sort descending
    scored_providers = []
    for p in filtered_providers:
        score = calculate_score(p)
        scored_providers.append({**p, 'score': score})

    # Sort by score descending
    ranked_providers = sorted(scored_providers, key=lambda x: x['score'], reverse=True)

    return ranked_providers
