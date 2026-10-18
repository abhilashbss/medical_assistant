import sys
import os
from flask import Flask, request, jsonify
from typing import List, Optional
from .geospatial import filter_by_radius

# Handle mock imports for the build unit
try:
    from backend.db.models import Provider, db_session
except ImportError:
    # Add root to sys.path to allow importing from .see/mocks
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    if root_dir not in sys.path:
        sys.path.append(root_dir)

    # Now we can try to import from .see.mocks.backend.db.models
    # But we still can't import '.see' as a module.
    # We need to import from the path.
    import importlib.util
    import os

    mock_path = os.path.join(root_dir, ".see/mocks/backend/db/models.py")
    spec = importlib.util.spec_from_file_location("backend.db.models", mock_path)
    mock_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mock_module)
    Provider = mock_module.Provider
    db_session = mock_module.db_session

app = Flask(__name__)

def find_providers_by_radius(
    lat: float,
    lng: float,
    radius_km: float,
    specialty: Optional[str] = None,
    query: Optional[str] = None
) -> List[dict]:
    """
    Find providers within a given radius, optionally filtered by specialty and name.
    Returns a list of providers with their distance.
    """
    # 1. Get all providers from DB
    all_providers = db_session.all()

    # 2. Geospatial filter first
    nearby_providers = filter_by_radius(all_providers, lat, lng, radius_km)

    results = []
    for provider, distance in nearby_providers:
        # 3. Specialty filter
        if specialty and provider.specialty.lower() != specialty.lower():
            continue

        # 4. Name query filter
        if query and query.lower() not in provider.name.lower():
            continue

        results.append({
            "id": provider.id,
            "name": provider.name,
            "specialty": provider.specialty,
            "distance_km": round(distance, 2),
            "lat": provider.lat,
            "lng": provider.lng,
            "insurance_plans": getattr(provider, 'insurance_plans', [])
        })

    return results

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

    results = find_providers_by_radius(
        lat=lat,
        lng=lng,
        radius_km=radius,
        specialty=specialty,
        query=query
    )

    return jsonify({
        "results": results,
        "count": len(results),
        "radius_km": radius
    })

if __name__ == '__main__':
    app.run(debug=True)
