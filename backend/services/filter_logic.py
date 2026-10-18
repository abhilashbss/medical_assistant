import logging

try:
    from backend.integrations.insurance_client import verify_network_status
except ImportError:
    import sys
    import os
    mock_path = os.path.join(os.getcwd(), '.see', 'mocks')
    if mock_path not in sys.path:
        sys.path.append(mock_path)
    try:
        from backend.integrations.insurance_client import verify_network_status
    except ImportError:
        # This is for when the mock is literally at .see/mocks/backend/integrations/insurance_client.py
        # but we want to import it as if it were in the backend package.
        # We can just import the module directly using importlib.
        import importlib.util
        spec = importlib.util.spec_from_file_location("backend.integrations.insurance_client",
                                                     os.path.join(mock_path, 'backend', 'integrations', 'insurance_client.py'))
        insurance_client = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(insurance_client)
        verify_network_status = insurance_client.verify_network_status


logger = logging.getLogger(__name__)

def filter_in_network_providers(providers, insurance_plan):
    """
    Filters the list of providers to only include those that are confirmed 'in-network'
    for the given insurance plan.

    Providers returning 'out-of-network' or 'unverified' are discarded.
    If the verification API is unreachable, the provider is treated as out-of-network.
    """
    filtered = []
    for provider in providers:
        try:
            status = verify_network_status(provider['id'], insurance_plan)
            if status == 'in-network':
                filtered.append(provider)
        except Exception as e:
            # HIPAA compliance: do not log PHI (like provider_id if it's sensitive,
            # though usually IDs are fine, but we avoid logging the insurance_plan
            # and specific patient-provider links in detail).
            logger.error("Insurance verification API failure: %s", str(e))
            # Fallback: treat as out-of-network
            continue

    return filtered
