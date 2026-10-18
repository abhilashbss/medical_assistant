import os
import logging
import time
from typing import Dict, Optional, TypedDict
from dataclasses import dataclass
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# HIPAA compliance: No PHI in logs
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

try:
    from backend.db.encryption import encrypt_phi, decrypt_phi
except ImportError:
    try:
        from .see.mocks.backend.db.encryption import encrypt_phi, decrypt_phi
    except ImportError:
        # Fallback for local testing if structure differs
        def encrypt_phi(d): return f"enc_{d}"
        def decrypt_phi(d): return d[4:] if d.startswith("enc_") else d

@dataclass
class InsuranceVerificationRequest:
    provider_id: str
    insurance_carrier: str
    plan_type: str
    member_id: str  # PHI

@dataclass
class InsuranceVerificationResponse:
    status: str  # 'In-Network', 'Out-of-Network', 'Error'
    verification_id: str
    latency_ms: float

class CarrierAdapter:
    """Base class for insurance carrier adapters to normalize API responses."""
    def verify(self, request: InsuranceVerificationRequest) -> InsuranceVerificationResponse:
        raise NotImplementedError

class GenericCarrierAdapter(CarrierAdapter):
    """Example adapter for a generic carrier API."""
    def __init__(self, api_key: str, endpoint: str):
        self.api_key = api_key
        self.endpoint = endpoint

    def verify(self, request: InsuranceVerificationRequest) -> InsuranceVerificationResponse:
        start_time = time.time()
        try:
            # Use TLS 1.3 is handled by requests/urllib3/openssl defaults in modern Python
            payload = {
                "provider": request.provider_id,
                "carrier": request.insurance_carrier,
                "plan": request.plan_type,
                "member": encrypt_phi(request.member_id) # Encrypt PHI for transit if required by API
            }
            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

            response = requests.post(self.endpoint, json=payload, headers=headers, timeout=0.4) # Strict timeout for 500ms target
            response.raise_for_status()

            data = response.json()
            status = "In-Network" if data.get("is_in_network") else "Out-of-Network"

            return InsuranceVerificationResponse(
                status=status,
                verification_id=data.get("tx_id", "unknown"),
                latency_ms=(time.time() - start_time) * 1000
            )
        except Exception as e:
            logger.error("Verification API error") # No PHI in log
            return InsuranceVerificationResponse(status="Error", verification_id="error", latency_ms=(time.time() - start_time) * 1000)

class VerificationGateway:
    """Synchronous API gateway for insurance network verification."""
    def __init__(self):
        self.cache: Dict[str, tuple[float, InsuranceVerificationResponse]] = {}
        self.cache_ttl = 3600  # 1 hour cache for network status

        # Setup retries
        self.session = requests.Session()
        retries = Retry(total=2, backoff_factor=0.1, status_forcelist=[500, 502, 503, 504])
        self.session.mount('https://', HTTPAdapter(max_retries=retries))

    def _get_cache_key(self, request: InsuranceVerificationRequest) -> str:
        return f"{request.provider_id}:{request.insurance_carrier}:{request.plan_type}"

    def verify_network_status(self, request: InsuranceVerificationRequest) -> InsuranceVerificationResponse:
        cache_key = self._get_cache_key(request)
        now = time.time()

        if cache_key in self.cache:
            timestamp, cached_res = self.cache[cache_key]
            if now - timestamp < self.cache_ttl:
                return cached_res

        # Initialize adapter from env
        api_key = os.getenv("CARRIER_API_KEY", "test_key")
        endpoint = os.getenv("CARRIER_ENDPOINT", "https://api.carrier.com/verify")
        adapter = GenericCarrierAdapter(api_key, endpoint)

        result = adapter.verify(request)

        # Only cache successful responses
        if result.status != "Error":
            self.cache[cache_key] = (now, result)

        return result

# Singleton instance for the integration layer
_gateway = VerificationGateway()

def verify_network_status(request: InsuranceVerificationRequest) -> InsuranceVerificationResponse:
    """
    Exported function to verify if a provider is in-network for a given insurance plan.
    """
    return _gateway.verify_network_status(request)
