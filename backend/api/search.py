from typing import List, Optional
from flask import Flask, request, jsonify
from geopy.distance import geodesic

try:
    from backend.db.schema import Provider, get_db_session
except ImportError:
    try:
        from .see.mocks.backend.db.schema import Provider, get_db_session
    except (ImportError, ValueError):
        # Absolute path fallback for mock imports in this environment
        import importlib.util
        import os

        root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        mock_path = os.path.join(root_dir, ".see/mocks/backend/db/schema.py")
        spec = importlib.util.spec_from_file_location("backend.db.schema", mock_path)
        mock_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mock_module)
        Provider = mock_module.Provider
        get_db_session = mock_module.get_db_session

app = Flask(__name__)

def find_providers_by_radius(
    lat: float,
    lng: float,
    radius_km: float,
    specialty: Optional[str] = None,
    query: Optional[str] = None
) -> List[Provider]:
    """
    Finds providers within a specified radius, filtered by specialty and name query.
    Returns providers sorted by proximity.
    """
    session = get_db_session()
    all_providers = session.query(Provider).all()

    results = []
    center = (lat, lng)

    for provider in all_providers:
        # Geospatial distance check
        dist = geodesic(center, provider.location).km
        if dist <= radius_km:
            # Specialty filter
            if specialty and provider.specialty.lower() != specialty.lower():
                continue

            # Name query filter
            if query and query.lower() not in provider.name.lower():
                continue

            results.append((dist, provider))

    # Sort by distance (ascending)
    results.sort(key=lambda x: x[0])

    return [p for dist, p in results]

@app.route('/providers/search', methods=['GET'])
def search_providers():
    """
    Search for providers by location, specialty, and name.
    """
    try:
        lat = float(request.args.get('lat'))
        lng = float(request.args.get('lng'))
        radius = float(request.args.get('radius'))
    except (TypeError, ValueError):
        return jsonify({"error": "lat, lng, and radius are required and must be numeric"}), 400

    specialty = request.args.get('specialty')
    query = request.args.get('query')

    providers = find_providers_by_radius(
        lat=lat,
        lng=lng,
        radius_km=radius,
        specialty=specialty,
        query=query
    )

    # Transform Provider objects to dicts for JSON response
    results = [
        {
            "id": p.id,
            "name": p.name,
            "specialty": p.specialty,
            "location": p.location,
            "insurance_network": p.insurance_network
        }
        for p in providers
    ]

    return jsonify({
        "results": results,
        "count": len(results),
        "radius_km": radius
    })

if __name__ == '__main__':
    app.run(debug=True)
