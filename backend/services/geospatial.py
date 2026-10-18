from geopy.distance import geodesic
from typing import List, Tuple

try:
    from backend.db.schema import Provider, get_db_session
except ImportError:
    import sys
    import os
    # Add root to path to allow importing from .see.mocks
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    if root not in sys.path:
        sys.path.insert(0, root)

    # Use absolute import from .see.mocks
    try:
        from .see.mocks.backend.db.schema import Provider, get_db_session
    except ImportError:
        # Fallback to importing via the root path
        import importlib.util
        mock_path = os.path.join(root, ".see/mocks/backend/db/schema.py")
        spec = importlib.util.spec_from_file_location("backend.db.schema", mock_path)
        mock_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mock_module)
        Provider = mock_module.Provider
        get_db_session = mock_module.get_db_session

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
            # Filter by specialty (case-insensitive)
            if specialty and specialty.lower() not in provider.specialty.lower():
                continue

            # Filter by name/query (case-insensitive)
            if query and query.lower() not in provider.name.lower():
                continue

            # Geospatial filter
            dist = geodesic(user_location, provider.location).km
            if dist <= radius_km:
                results.append((provider, dist))

        # Sort by proximity
        results.sort(key=lambda x: x[1])
        return results

geospatial_service = GeospatialService()
