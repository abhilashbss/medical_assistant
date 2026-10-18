export interface Provider {
  id: string;
  name: string;
  specialty: string;
  distance: number;
  rating: number;
  availability: string;
  networkStatus: 'In-Network' | 'Out-of-Network' | 'Unknown';
}

export interface SearchFilters {
  specialty: string;
  location: string;
  providerName: string;
  distanceMax: number;
  minRating: number;
}

export async function fetchProviders(filters: SearchFilters, insuranceCarrier: string, planType: string): Promise<Provider[]> {
  // This simulates the synchronous API gateway call.
  // In reality, this would be a fetch() to the backend.

  const response = await fetch('/api/providers/search', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...filters, insuranceCarrier, planType }),
  });

  if (!response.ok) {
    throw new Error('Failed to fetch providers');
  }

  return response.json();
}
