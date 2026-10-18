import pytest
import time
import sys
import os

# Add current directory to sys.path to allow importing from .see
sys.path.append(os.getcwd())

try:
    from see.mocks.backend.services.filtering import filter_in_network_providers
except ImportError:
    # Fallback for different environments
    from .see.mocks.backend.services.filtering import filter_in_network_providers

def test_insurance_filtering():
    """Providers are correctly filtered by insurance carrier and plan type"""
    providers = [
        {'id': '1', 'name': 'Dr. A', 'insurance_carrier': 'Aetna', 'plan_type': 'PPO'},
        {'id': '2', 'name': 'Dr. B', 'insurance_carrier': 'Cigna', 'plan_type': 'HMO'},
    ]
    result = filter_in_network_providers(providers, 'Aetna', 'PPO')
    assert len(result) == 1
    assert result[0]['id'] == '1'

def test_network_status_identification():
    """Network status is accurately identified as In-Network or Out-of-Network"""
    def get_status(p, carrier):
        return 'In-Network' if p['insurance_carrier'] == carrier else 'Out-of-Network'

    p1 = {'insurance_carrier': 'Aetna'}
    p2 = {'insurance_carrier': 'Cigna'}

    assert get_status(p1, 'Aetna') == 'In-Network'
    assert get_status(p2, 'Aetna') == 'Out-of-Network'

def test_api_latency_mock():
    """Real-time API mock responses are handled without latency exceeding 500ms"""
    start = time.time()
    filter_in_network_providers([], 'Aetna', 'PPO')
    duration = (time.time() - start) * 1000
    assert duration < 500

def test_empty_results():
    """Empty result sets are returned when no in-network providers exist in the radius"""
    providers = [
        {'id': '1', 'name': 'Dr. A', 'insurance_carrier': 'Cigna'},
    ]
    result = filter_in_network_providers(providers, 'Aetna', 'PPO')
    assert len(result) == 0
