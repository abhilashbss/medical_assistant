import logging

try:
    from backend.integrations.insurance_client import verify_network_status
except ImportError:
    from .see.mocks.backend.integrations.insurance_client import verify_network_status

logger = logging.getLogger(__name__)

def filter_in_network_providers(providers, carrier, plan):
    """
    Filters providers to only show those confirmed 'in-network' for the user's plan.

    Providers returning 'out-of-network' or 'unverified' are discarded.
    API failures are treated as out-of-network.
    """
    filtered = []
    for provider in providers:
        try:
            status = verify_network_status(provider["id"], carrier, plan)
            if status == "in-network":
                filtered.append(provider)
        except Exception as e:
            # Fallback: treat as out-of-network if API is unreachable/fails
            logger.error(f"Insurance verification failed for provider {provider['id']}: {e}")
            continue

    return filtered
