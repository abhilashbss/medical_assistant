import pytest
import time
from backend.api.search import app

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_geospatial_search_radius(client):
    """Geospatial search returns providers within requested radius under 500ms"""
    start_time = time.time()
    # Center: LA (34.0522, -118.2437)
    # Radius: 5km should find Dr. Smith, Dr. Jones, Dr. Lee
    response = client.get('/providers/search?lat=34.0522&lng=-118.2437&radius=5')
    duration_ms = (time.time() - start_time) * 1000

    assert response.status_code == 200
    data = response.get_json()
    assert data['count'] == 3
    assert duration_ms < 500

def test_provider_specialty_filtering(client):
    """Providers are filtered correctly by medical specialty"""
    # Cardiology in LA
    response = client.get('/providers/search?lat=34.0522&lng=-118.2437&radius=5&specialty=Cardiology')

    assert response.status_code == 200
    data = response.get_json()
    assert data['count'] == 2
    for p in data['results']:
        assert p['specialty'] == 'Cardiology'

def test_provider_name_search(client):
    """Providers are filtered correctly by name"""
    # Search for "Lee" in LA
    response = client.get('/providers/search?lat=34.0522&lng=-118.2437&radius=5&query=Lee')

    assert response.status_code == 200
    data = response.get_json()
    assert data['count'] == 1
    assert data['results'][0]['name'] == 'Dr. Lee'

def test_search_performance_standard_query(client):
    """Search results load in under 2 seconds for a standard query"""
    start_time = time.time()
    # Mixed query: Cardiology in LA within 10km
    response = client.get('/providers/search?lat=34.0522&lng=-118.2437&radius=10&specialty=Cardiology')
    duration = time.time() - start_time

    assert response.status_code == 200
    assert duration < 2.0

def test_insurance_network_filtering(client):
    """Providers are filtered correctly by insurance carrier and plan type"""
    response = client.get('/providers/search?lat=34.0522&lng=-118.2437&radius=5')
    data = response.get_json()

    # Filter for BlueCross
    blue_cross = [p for p in data['results'] if p['insurance_network'] == 'BlueCross']
    assert len(blue_cross) == 2
    assert any(p['name'] == 'Dr. Smith' for p in blue_cross)
    assert any(p['name'] == 'Dr. Lee' for p in blue_cross)

def test_realtime_network_status(client):
    """Results accurately reflect real-time 'In-Network' or 'Out-of-Network' status"""
    response = client.get('/providers/search?lat=34.0522&lng=-118.2437&radius=5')
    data = response.get_json()

    # Dr. Jones is Aetna
    jones = next(p for p in data['results'] if p['name'] == 'Dr. Jones')
    assert jones['insurance_network'] == 'Aetna'
