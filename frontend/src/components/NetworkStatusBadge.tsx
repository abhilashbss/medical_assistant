import React from 'react';

interface NetworkStatusBadgeProps {
  status: 'In-Network' | 'Out-of-Network' | 'Unknown';
}

export const NetworkStatusBadge: React.FC<NetworkStatusBadgeProps> = ({ status }) => {
  const colors = {
    'In-Network': 'bg-green-100 text-green-800 border-green-200',
    'Out-of-Network': 'bg-red-100 text-red-800 border-red-200',
    'Unknown': 'bg-gray-100 text-gray-800 border-gray-200',
  };

  return (
    <span className={`px-2 py-1 rounded-full text-xs font-semibold border ${colors[status]}`}>
      {status}
    </span>
  );
};
