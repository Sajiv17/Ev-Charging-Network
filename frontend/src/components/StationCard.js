import React from 'react';
import { Link } from 'react-router-dom';

function StationCard({ station }) {
  const available = station.available_chargers ?? 0;
  const total = station.total_chargers;
  return (
    <div className="card station-card">
      <div className="card-top">
        <h3>{station.station_name}</h3>
        <span className={`badge ${available > 0 ? 'badge-green' : 'badge-red'}`}>
          {available > 0 ? `${available}${total ? `/${total}` : ''} available` : 'Full'}
        </span>
      </div>
      <p className="muted">{station.address}</p>
      <p className="muted small">{station.city}</p>
      <Link className="btn" to={`/stations/${station.city}/${station.station_id}`}>
        View chargers
      </Link>
    </div>
  );
}

export default StationCard;
