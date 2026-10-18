# runctl:mock-of backend.services.ranking
def rank_providers(providers, sort_by='rating'):
    """
    Mock implementation of ranking providers.
    """
    if sort_by == 'distance':
        return sorted(providers, key=lambda x: x.get('distance', 100))
    if sort_by == 'rating':
        return sorted(providers, key=lambda x: x.get('rating', 0), reverse=True)
    return providers
