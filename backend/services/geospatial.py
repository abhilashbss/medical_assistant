from geopy.distance import geodesic
from typing import List, Tuple, Optional
import logging

try:
    from backend.db.models import Provider
except ImportError:
    try:
        from .see.mocks.backend.db.models import Provider
    except ImportError:
        from dataclasses import dataclass
        @dataclass
        class Provider:
            id: int
            name: str
            specialty: str
            location: tuple[float, float]
            insurance_plans: list[str]

logger = logging.getLogger(__name__)

def find_providers_in_radius(
    lat: float,
    lng: float,
    radius_km: float,
    specialty: Optional[str] = None,
    query: Optional[str] = None,
    providers_list: Optional[List[Provider]] = None
) -> List[Tuple[Provider, float]]:
    """
    Finds providers within a specified radius, filtered by specialty and name query.
    Returns a list of (Provider, distance_km) tuples sorted by proximity.
    """
    if providers_list is None:
        return []

    results = []
    center = (lat, lng)

    for provider in providers_list:
        if specialty and provider.specialty.lower() != specialty.lower():
            continue

        if query and query.lower() not in provider.name.lower():
            continue

        dist = geodesic(center, provider.location).kilometers

        if dist <= radius_km:
            results.append((provider, dist))

    results.sort(key=lambda x: x[1])

    return results
