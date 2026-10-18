from typing import List, Optional
from flask import Flask, request, jsonify
from backend.services.geospatial import geospatial_service

app = Flask(__name__)

def find_providers_by_radius(
    lat: float,
    lng: float,
    radius_km: float,
    specialty: Optional[str] = None,
    query: Optional[str] = None
) -> List[Any]:
    """
    Finds providers within a specified radius, filtered by specialty and name query.
    Returns providers sorted by proximity.
    """
    results = geospatial_service.find_nearby_providers(
        lat=lat,
        lng=lng,
        radius_km=radius_km,
        specialty=specialty,
        query=query
    )
    return [p for p, dist in results]

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
