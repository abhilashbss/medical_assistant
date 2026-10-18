from geopy.distance import geodesic
from typing import List, Tuple

def get_distance(coord1: Tuple[float, float], coord2: Tuple[float, float]) -> float:
    """
    Calculate the distance between two points in kilometers.
    coords: (lat, lng)
    """
    return geodesic(coord1, coord2).kilometers

def filter_by_radius(providers: List, center_lat: float, center_lng: float, radius_km: float) -> List:
    """
    Filter providers that are within the specified radius.
    Returns a list of (provider, distance).
    """
    center = (center_lat, center_lng)
    results = []
    for provider in providers:
        # Use the lat/lng attributes from the Provider model
        provider_coord = (provider.lat, provider.lng)
        dist = get_distance(center, provider_coord)
        if dist <= radius_km:
            results.append((provider, dist))

    # Sort by proximity
    results.sort(key=lambda x: x[1])
    return results
