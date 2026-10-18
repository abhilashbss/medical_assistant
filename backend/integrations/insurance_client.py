import os
import logging
import time
from dataclasses import dataclass
from typing import Dict, Optional, Set
from collections import OrderedDict
from backend.integrations.hipaa_transport import HIPAATransport

# Configure logging
logger = logging.getLogger(__name__)

@dataclass
class InsuranceVerificationRequest:
    provider_id: str
    insurance_carrier: str
    plan_type: str

@dataclass
class InsuranceVerificationResponse:
    provider_id: str
    status: str  # 'In-Network' or 'Out-of-Network'
    verified_at: float

class InsuranceClient:
    """
    Client for verifying insurance network status via third-party carrier APIs.
    """
    def __init__(self, transport: HIPAATransport, cache_ttl: int = 3600, max_cache_size: int = 1000):
        self.transport = transport
        self.cache_ttl = cache_ttl
        self.max_cache_size = max_cache_size
        self._cache: OrderedDict[str, InsuranceVerificationResponse] = OrderedDict()

    def _generate_cache_key(self, request: InsuranceVerificationRequest) -> str:
        return f"{request.provider_id}:{request.insurance_carrier}:{request.plan_type}"

    def verify_network_status(self, request: InsuranceVerificationRequest) -> InsuranceVerificationResponse:
        """
        Verifies if a provider is in-network for a specific insurance carrier and plan.
        """
        cache_key = self._generate_cache_key(request)

        # Check cache
        if cache_key in self._cache:
            cached_resp = self._cache[cache_key]
            if time.time() - cached_resp.verified_at < self.cache_ttl:
                self._cache.move_to_end(cache_key)
                return cached_resp
            else:
                del self._cache[cache_key]

        # Get carrier endpoint and API key from environment
        endpoint = os.environ.get("CARRIER_ENDPOINT", "https://api.insurance-carrier.com/verify")
        api_key = os.environ.get("CARRIER_API_KEY", "default_api_key")

        payload = {
            "provider_id": request.provider_id,
            "carrier": request.insurance_carrier,
            "plan": request.plan_type
        }

        headers = {"Authorization": f"Bearer {api_key}"}

        try:
            response = self.transport.safe_request(
                method="POST",
                url=endpoint,
                payload=payload,
                headers=headers
            )

            data = response.json()
            # Standardize response format from different carriers
            status = data.get("status", "Out-of-Network").strip().title()
            if status not in ["In-Network", "Out-of-Network"]:
                status = "Out-of-Network"

            verification_resp = InsuranceVerificationResponse(
                provider_id=request.provider_id,
                status=status,
                verified_at=time.time()
            )

            # Update cache with eviction
            self._cache[cache_key] = verification_resp
            if len(self._cache) > self.max_cache_size:
                self._cache.popitem(last=False)

            return verification_resp

        except Exception:
            logger.error("Network verification failed due to an internal or external error")
            return InsuranceVerificationResponse(
                provider_id=request.provider_id,
                status="Out-of-Network",
                verified_at=time.time()
            )

# Singleton instance for easy import by siblings
_default_transport = HIPAATransport(allowed_domains={"api.insurance-carrier.com"})
_client = InsuranceClient(_default_transport)

def verify_network_status(provider_id: str, insurance_carrier: str, plan_type: str) -> str:
    """
    Exported function to verify network status.
    Returns 'In-Network' or 'Out-of-Network'.
    """
    try:
        request = InsuranceVerificationRequest(
            provider_id=provider_id,
            insurance_carrier=insurance_carrier,
            plan_type=plan_type
        )
        response = _client.verify_network_status(request)
        return response.status
    except Exception:
        logger.error("Unexpected error in verify_network_status: internal verification failure")
        return "Out-of-Network"
