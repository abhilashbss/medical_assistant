try:
    from backend.api.search import find_providers_by_radius
except ImportError:
    from .see.mocks.backend.api.search import find_providers_by_radius

try:
    from backend.integrations.verification import verify_network_status
except ImportError:
    from .see.mocks.backend.integrations.verification import verify_network_status

from backend.logic.ranking import rank_providers

def filter_and_rank_providers(lat, lon, radius_km, insurance_plan):
    """
    Filters providers by geospatial radius and real-time insurance network status,
    then ranks the results.
    """
    # 1. Fetch providers within radius
    providers = find_providers_by_radius(lat, lon, radius_km)

    # 2. Filter by insurance network status
    in_network_providers = []
    for p in providers:
        try:
            status = verify_network_status(p['id'], insurance_plan)
            if status == 'in-network':
                in_network_providers.append(p)
        except Exception:
            # Fallback: Treat API failures as out-of-network to avoid financial surprises
            continue

    # 3. Rank the filtered results
    return rank_providers(in_network_providers)
