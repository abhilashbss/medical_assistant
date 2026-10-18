import logging

try:
    from backend.integrations.insurance_client import verify_network_status
except ImportError:
    from .see.mocks.backend.integrations.insurance_client import verify_network_status

logger = logging.getLogger(__name__)

def filter_in_network_providers(providers, carrier, plan):
    """
    Filters a list of providers to only those confirmed as 'in-network' for the given insurance.

    Providers that are 'out-of-network', 'unverified', or where the API call fails
    are excluded from the results.
    """
    in_network_providers = []

    for provider in providers:
        provider_id = provider.get("id")
        if not provider_id:
            continue

        try:
            # Real-time insurance verification
            status = verify_network_status(provider_id, carrier, plan)
            if status == "in-network":
                in_network_providers.append(provider)
        except Exception as e:
            # HIPAA Compliance: Log the error but NOT the patient's insurance details (carrier/plan)
            # or the provider's PHI.
            logger.error(f"Insurance verification failed for provider {provider_id}: {str(e)}")
            # Fallback: Treat as out-of-network if API is unreachable or fails
            continue

    return in_network_providers
