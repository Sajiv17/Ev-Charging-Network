import React from 'react';

const COLORS = {
  available: 'green',
  occupied: 'yellow',
  faulted: 'red',
  maintenance: 'gray',
};

function ChargerStatusBadge({ status }) {
  const color = COLORS[status] || 'gray';
  return <span className={`badge badge-${color}`}>{status || 'unknown'}</span>;
}

export default ChargerStatusBadge;
