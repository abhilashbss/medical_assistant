from flask import Flask, request, jsonify
from typing import List
from backend.services.geospatial import find_providers_in_radius

try:
    from backend.db.models import Provider
except ImportError:
    from .see.mocks.backend.db.models import Provider

app = Flask(__name__)

# Mock database of providers for demonstration and testing
MOCK_PROVIDERS = [
    Provider(1, "Dr. Alice Smith", "Cardiology", (34.0522, -118.2437), ["BlueCross", "Aetna"]),
    Provider(2, "Dr. Bob Jones", "Dermatology", (34.0600, -118.2500), ["BlueCross"]),
    Provider(3, "City General Hospital", "General", (34.1000, -118.3000), ["Aetna", "UnitedHealth"]),
    Provider(4, "Dr. Carol White", "Cardiology", (34.0400, -118.2300), ["UnitedHealth"]),
]

@app.route('/providers/search', methods=['GET'])
def search_providers():
    """
    Search for providers by location, specialty, and name.
    Params:
        lat (float): Latitude of center point
        lng (float): Longitude of center point
        radius (float): Search radius in kilometers
        specialty (str, optional): Filter by specialty
        query (str, optional): Filter by provider name
    """
    try:
        lat = float(request.args.get('lat'))
        lng = float(request.args.get('lng'))
        radius = float(request.args.get('radius'))
    except (TypeError, ValueError):
        return jsonify({"error": "lat, lng, and radius are required and must be numeric"}), 400

    specialty = request.args.get('specialty')
    query = request.args.get('query')

    # Use the geospatial service to find providers
    results = find_providers_in_radius(
        lat=lat,
        lng=lng,
        radius_km=radius,
        specialty=specialty,
        query=query,
        providers_list=MOCK_PROVIDERS
    )

    # Format the response
    output = [
        {
            "id": p.id,
            "name": p.name,
            "specialty": p.specialty,
            "location": p.location,
            "distance_km": round(dist, 2)
        }
        for p, dist in results
    ]

    return jsonify({
        "results": output,
        "count": len(output),
        "radius_km": radius
    })

if __name__ == '__main__':
    app.run(debug=True)
