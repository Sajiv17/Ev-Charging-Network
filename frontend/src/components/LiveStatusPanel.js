import React, { useEffect, useState } from 'react';
import { getLiveStatus, errorMessage } from '../services/api';
import ChargerStatusBadge from './ChargerStatusBadge';

const POLL_MS = 5000;

// Polls live charger status every 5 seconds for one station.
function LiveStatusPanel({ city, stationId, onSelect }) {
  const [chargers, setChargers] = useState([]);
  const [updatedAt, setUpdatedAt] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const data = await getLiveStatus(city, stationId);
        if (!cancelled) {
          setChargers(data);
          setUpdatedAt(new Date());
          setError('');
        }
      } catch (e) {
        if (!cancelled) setError(errorMessage(e));
      }
    };

    load(); // first load immediately, then every 5s
    const id = setInterval(load, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id); // stop polling when the component unmounts
    };
  }, [city, stationId]);

  return (
    <div className="card">
      <div className="card-top">
        <h3>Live charger status</h3>
        <span className="muted small">
          {updatedAt ? `Updated ${updatedAt.toLocaleTimeString('en-IN')}` : 'Loading…'} · refreshes every 5s
        </span>
      </div>
      {error && <p className="error">{error}</p>}
      <div className="charger-grid">
        {chargers.map((c) => (
          <button
            key={c.charger_id}
            className="charger-tile"
            onClick={() => onSelect && onSelect(c)}
            type="button"
          >
            <strong>{c.label || `Charger ${c.charger_id}`}</strong>
            <span className="muted small">{c.charger_type} · {c.power_kw} kW</span>
            <ChargerStatusBadge status={c.status} />
          </button>
        ))}
      </div>
    </div>
  );
}

export default LiveStatusPanel;
