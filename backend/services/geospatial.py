from geopy.distance import geodesic
from typing import List, Tuple
import shapely.wkb

from backend.db.schema import Provider, get_db_session

class GeospatialService:
    def find_nearby_providers(
        self,
        lat: float,
        lng: float,
        radius_km: float,
        specialty: str = None,
        query: str = None
    ) -> List[Tuple[Provider, float]]:
        session = get_db_session()
        providers = session.query(Provider).all()

        results = []
        user_location = (lat, lng)

        for provider in providers:
            # Filter by specialty
            if specialty and provider.specialty.lower() != specialty.lower():
                continue

            # Filter by name/query
            if query and query.lower() not in provider.name.lower():
                continue

            # Geospatial filter
            # Convert GeoAlchemy2/WKB location to (lat, lon)
            loc = provider.location
            if isinstance(loc, str):
                point = shapely.wkb.loads(loc)
                provider_location = (point.y, point.x)
            else:
                # Assume it's a shapely-like object or already a tuple
                try:
                    provider_location = (loc.y, loc.x)
                except AttributeError:
                    provider_location = loc

            dist = geodesic(user_location, provider_location).km
            if dist <= radius_km:
                results.append((provider, dist))

        # Sort by proximity
        results.sort(key=lambda x: x[1])
        return results

geospatial_service = GeospatialService()
