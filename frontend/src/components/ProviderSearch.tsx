import React, { useState, useEffect } from 'react';
import { fetchProviders, Provider, SearchFilters } from '../api/provider_api';
import { NetworkStatusBadge } from './NetworkStatusBadge';

interface ProviderSearchProps {
  insuranceCarrier: string;
  planType: string;
}

export const ProviderSearch: React.FC<ProviderSearchProps> = ({ insuranceCarrier, planType }) => {
  const [filters, setFilters] = useState<SearchFilters>({
    specialty: '',
    location: '',
    providerName: '',
    distanceMax: 50,
    minRating: 0,
  });
  const [results, setResults] = useState<Provider[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState<'distance' | 'rating' | 'availability'>('rating');

  const handleSearch = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await fetchProviders(filters, insuranceCarrier, planType);
      setResults(data);
    } catch (err: any) {
      if (err.message?.includes('insurance network status') || err.status === 500) {
        setError('Unable to verify insurance network status. Please try again later.');
      } else {
        setError('Failed to search for providers. Please try again.');
      }
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    handleSearch();
  }, [insuranceCarrier, planType]);

  const sortedResults = [...results].sort((a, b) => {
    if (sortBy === 'distance') return a.distance - b.distance;
    if (sortBy === 'rating') return b.rating - a.rating;
    return 0; // Availability sorting logic would go here
  });

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <h1 className="text-2xl font-bold mb-6">Find Care</h1>

      {/* Search Form */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8 p-4 bg-gray-50 rounded-lg border">
        <input
          placeholder="Specialty (e.g. Cardiology)"
          className="p-2 border rounded"
          value={filters.specialty}
          onChange={e => setFilters({...filters, specialty: e.target.value})}
        />
        <input
          placeholder="Location (City or Zip)"
          className="p-2 border rounded"
          value={filters.location}
          onChange={e => setFilters({...filters, location: e.target.value})}
        />
        <input
          placeholder="Provider Name"
          className="p-2 border rounded"
          value={filters.providerName}
          onChange={e => setFilters({...filters, providerName: e.target.value})}
        />
        <div className="flex items-center gap-2">
          <label className="text-sm">Max Distance: {filters.distanceMax}mi</label>
          <input
            type="range" min="1" max="100"
            className="flex-1"
            value={filters.distanceMax}
            onChange={e => setFilters({...filters, distanceMax: parseInt(e.target.value)})}
          />
        </div>
        <div className="flex items-center gap-2">
          <label className="text-sm">Min Rating: {filters.minRating}+</label>
          <input
            type="range" min="0" max="5" step="0.5"
            className="flex-1"
            value={filters.minRating}
            onChange={e => setFilters({...filters, minRating: parseFloat(e.target.value)})}
          />
        </div>
        <button
          onClick={handleSearch}
          className="bg-blue-600 text-white p-2 rounded hover:bg-blue-700 font-semibold"
        >
          Search
        </button>
      </div>

      {/* Sorting */}
      <div className="flex justify-end gap-4 mb-4">
        <span className="text-sm text-gray-600 self-center">Sort by:</span>
        <select
          value={sortBy}
          onChange={e => setSortBy(e.target.value as any)}
          className="text-sm border rounded p-1"
        >
          <option value="rating">Highest Rating</option>
          <option value="distance">Nearest</option>
          <option value="availability">Availability</option>
        </select>
      </div>

      {/* Results */}
      {isLoading ? (
        <div className="space-y-4">
          {[1, 2, 3].map(i => (
            <div key={i} className="h-24 bg-gray-200 animate-pulse rounded-lg" />
          ))}
        </div>
      ) : error ? (
        <div className="text-red-600 p-4 bg-red-50 rounded border border-red-200">{error}</div>
      ) : results.length === 0 ? (
        <div className="text-center p-12 text-gray-500">
          <p>No in-network providers found for your plan in this area.</p>
          <p className="text-sm mt-2">Try expanding your search radius to find more providers.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4">
          {sortedResults.map(provider => (
            <div key={provider.id} className="p-4 border rounded-lg flex justify-between items-center hover:shadow-md transition-shadow">
              <div>
                <h3 className="font-bold text-lg">{provider.name}</h3>
                <p className="text-gray-600">{provider.specialty} • {provider.distance} miles away</p>
                <p className="text-sm text-yellow-600">⭐ {provider.rating} / 5</p>
              </div>
              <div className="flex flex-col items-end gap-2">
                <NetworkStatusBadge status={provider.networkStatus} />
                <span className="text-xs text-gray-500">{provider.availability}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
