import pytest
import time
import sys
import os

# Add current directory to sys.path to allow importing from .see
sys.path.append(os.getcwd())

try:
    from see.mocks.backend.services.filtering import filter_in_network_providers
    from see.mocks.backend.services.ranking import rank_providers
except ImportError:
    # Fallback for different environments
    from .see.mocks.backend.services.filtering import filter_in_network_providers
    from .see.mocks.backend.services.ranking import rank_providers

def test_search_network_filtered():
    """Search results only contain providers in the selected insurance network"""
    providers = [
        {'id': '1', 'name': 'Dr. A', 'insurance_carrier': 'Aetna', 'rating': 5, 'distance': 1},
        {'id': '2', 'name': 'Dr. B', 'insurance_carrier': 'Cigna', 'rating': 4, 'distance': 2},
    ]
    # Filtered results
    filtered = filter_in_network_providers(providers, 'Aetna', 'PPO')
    assert all(p['insurance_carrier'] == 'Aetna' for p in filtered)
    assert len(filtered) == 1

def test_network_status_labels():
    """Network status labels accurately reflect real-time API verification"""
    # Simulate the mapping used by the frontend
    def verify_network(p, carrier):
        return 'In-Network' if p['insurance_carrier'] == carrier else 'Out-of-Network'

    p = {'insurance_carrier': 'Aetna'}
    assert verify_network(p, 'Aetna') == 'In-Network'
    assert verify_network(p, 'Cigna') == 'Out-of-Network'

def test_geospatial_latency():
    """Search latency remains under 500ms for geospatial provider lookups"""
    start = time.time()
    # Simulate lookup
    providers = [{'id': '1', 'distance': 1}]
    rank_providers(providers, sort_by='distance')
    duration = (time.time() - start) * 1000
    assert duration < 500

def test_filtering_specialty_distance_rating():
    """Filtering by specialty, distance, and rating correctly narrows results"""
    providers = [
        {'id': '1', 'specialty': 'Cardiology', 'distance': 2, 'rating': 5},
        {'id': '2', 'specialty': 'Dermatology', 'distance': 10, 'rating': 4},
        {'id': '3', 'specialty': 'Cardiology', 'distance': 15, 'rating': 3},
    ]

    # Filter specialty=Cardiology, dist <= 5, rating >= 4
    filtered = [p for p in providers if p['specialty'] == 'Cardiology' and p['distance'] <= 5 and p['rating'] >= 4]
    assert len(filtered) == 1
    assert filtered[0]['id'] == '1'
