import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import requests

try:
    from backend.db.models import InsuranceCarrier, NetworkPlan
except ImportError:
    from .see.mocks.backend.db.models import InsuranceCarrier, NetworkPlan

from .hipaa_transport import HIPAATransport

logger = logging.getLogger("insurance_client")

class InsuranceClient:
    """
    Integration layer for verifying insurance network status in real-time.
    """

    def __init__(self):
        self.transport = HIPAATransport()
        self._cache: Dict[str, Dict[str, Any]] = {}
        self.cache_ttl = timedelta(minutes=15)
        self.timeout = float(os.getenv("INSURANCE_API_TIMEOUT", "0.5"))

    def _get_cache_key(self, provider_id: str, plan_id: str) -> str:
        return f"{provider_id}:{plan_id}"

    def verify_network_status(self, provider_id: str, plan: NetworkPlan, carrier: InsuranceCarrier) -> str:
        """
        Verify if a provider is in-network for a specific insurance plan.

        Returns: 'In-Network', 'Out-of-Network', or 'Error'
        """
        cache_key = self._get_cache_key(provider_id, plan.id)

        # Check cache
        if cache_key in self._cache:
            entry = self._cache[cache_key]
            if datetime.now() < entry['expiry']:
                return entry['status']

        # Request payload - minimized to avoid excessive PHI
        payload = {
            "provider_id": provider_id,
            "plan_id": plan.id,
            "plan_type": plan.plan_type
        }

        try:
            # Synchronous API call via secure transport
            response = self.transport.secure_post(
                carrier.api_endpoint,
                payload,
                timeout=self.timeout
            )

            data = response.json()
            status = data.get("network_status", "Out-of-Network")

            # Normalize response
            normalized_status = "In-Network" if status.lower() == "in-network" else "Out-of-Network"

            # Cache result
            self._cache[cache_key] = {
                "status": normalized_status,
                "expiry": datetime.now() + self.cache_ttl
            }

            return normalized_status

        except Exception as e:
            logger.error(f"Verification failed for provider {provider_id}: {str(e)}")
            return "Error"

# Export the function as required by the contract
def verify_network_status(provider_id: str, plan: NetworkPlan, carrier: InsuranceCarrier) -> str:
    client = InsuranceClient()
    return client.verify_network_status(provider_id, plan, carrier)
