import os
import logging
import time
from dataclasses import dataclass
from typing import Dict, Optional, Set
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
    def __init__(self, transport: HIPAATransport, cache_ttl: int = 3600):
        self.transport = transport
        self.cache_ttl = cache_ttl
        self._cache: Dict[str, InsuranceVerificationResponse] = {}

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
                return cached_resp

        # Get carrier endpoint and API key from environment
        # In a real scenario, these would be mapped based on request.insurance_carrier
        endpoint = os.environ.get("CARRIER_ENDPOINT", "https://api.insurance-carrier.com/verify")
        api_key = os.environ.get("CARRIER_API_KEY", "default_api_key")

        payload = {
            "provider_id": request.provider_id,
            "carrier": request.insurance_carrier,
            "plan": request.plan_type
        }

        headers = {"Authorization": f"Bearer {api_key}"}

        try:
            # Execute secure request
            response = self.transport.safe_request(
                method="POST",
                url=endpoint,
                payload=payload,
                headers=headers
            )

            data = response.json()
            status = data.get("status", "Out-of-Network")

            verification_resp = InsuranceVerificationResponse(
                provider_id=request.provider_id,
                status=status,
                verified_at=time.time()
            )

            # Update cache
            self._cache[cache_key] = verification_resp
            return verification_resp

        except Exception as e:
            logger.error(f"Network verification failed for provider {request.provider_id}: {str(e)}")
            # Fallback to 'Out-of-Network' on API error to be safe, or raise depending on policy
            return InsuranceVerificationResponse(
                provider_id=request.provider_id,
                status="Out-of-Network",
                verified_at=time.time()
            )

# Singleton instance for easy import by siblings
# Siblings will import verify_network_status from backend.integrations.insurance_client
_default_transport = HIPAATransport(allowed_domains={"api.insurance-carrier.com"})
_client = InsuranceClient(_default_transport)

def verify_network_status(provider_id: str, insurance_carrier: str, plan_type: str) -> str:
    """
    Exported function to verify network status.
    Returns 'In-Network' or 'Out-of-Network'.
    """
    request = InsuranceVerificationRequest(
        provider_id=provider_id,
        insurance_carrier=insurance_carrier,
        plan_type=plan_type
    )
    response = _client.verify_network_status(request)
    return response.status
