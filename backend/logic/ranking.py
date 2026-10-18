import logging
from typing import List, Dict, Any

try:
    from backend.api.search import find_providers_by_radius
    from backend.integrations.insurance import verify_network_status
except ImportError:
    # Fallback to mocks for standalone testing/development
    try:
        from .see.mocks.backend.api.search import find_providers_by_radius
        from .see.mocks.backend.integrations.insurance import verify_network_status
    except ImportError:
        # This case should be handled by the build system or tests providing mocks
        def find_providers_by_radius(*args, **kwargs): return []
        def verify_network_status(*args, **kwargs): return "unverified"

logger = logging.getLogger(__name__)

def filter_and_rank_providers(
    lat: float,
    lon: float,
    radius_km: float,
    insurance_plan_id: str
) -> List[Dict[str, Any]]:
    """
    Finds providers within radius, filters for in-network status, and ranks them.

    Filtering:
    - Only providers confirmed as 'in-network' by verify_network_status are kept.
    - Providers returning 'out-of-network', 'unverified', or causing API errors
      are treated as out-of-network and excluded.

    Ranking:
    - Score = (Rating * 10) - Distance
    - Higher ratings and lower distances increase the score.
    - Results are sorted in descending order of score.
    """
    # 1. Fetch providers within radius
    providers = find_providers_by_radius(lat, lon, radius_km)

    in_network_providers = []

    # 2. Filtering Logic
    for provider in providers:
        try:
            # Real-time insurance verification
            status = verify_network_status(provider["id"], insurance_plan_id)
            if status == "in-network":
                in_network_providers.append(provider)
        except Exception as e:
            # Insurance API failure fallback: treat as out-of-network to avoid false positives
            # HIPAA Note: Do not log provider or user PHI in the error message
            logger.error(f"Insurance verification failed for provider ID {provider.get('id')}: {str(e)}")
            continue

    # 3. Ranking Algorithm
    def calculate_score(p):
        # Weights: Rating (0-5) * 10, Distance (km) * 1
        return (p.get("rating", 0) * 10) - p.get("distance", 0)

    ranked_providers = sorted(
        in_network_providers,
        key=calculate_score,
        reverse=True
    )

    return ranked_providers
