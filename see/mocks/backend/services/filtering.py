# runctl:mock-of backend.services.filtering
def filter_in_network_providers(providers, insurance_carrier, plan_type):
    """
    Mock implementation of filtering providers by insurance.
    In a real scenario, this would hit the API gateway.
    """
    return [p for p in providers if p.get('insurance_carrier') == insurance_carrier]
