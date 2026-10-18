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
    If the verification API is unreachable, the error is propagated so the UI can
    display a graceful error message (Workflow 3).
    """
    filtered = []
    for provider in providers:
        # We do not catch InsuranceVerificationError here because it must propagate
        # to the API layer to trigger the 'Unable to verify' UI notification.
        status = verify_network_status(provider['id'], insurance_plan)
        if status.lower() == 'in-network':
            filtered.append(provider)

    return filtered
