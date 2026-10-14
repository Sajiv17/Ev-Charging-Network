import React, { useEffect, useState } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { getStation, getStationChargers, getChargerSlots, errorMessage } from '../services/api';
import ChargerStatusBadge from '../components/ChargerStatusBadge';
import { formatRange } from '../utils/dateUtils';
import { estimateCost, formatINR } from '../utils/priceCalculator';

function StationDetail() {
  const { city, stationId } = useParams();
  const navigate = useNavigate();
  const [station, setStation] = useState(null);
  const [chargers, setChargers] = useState([]);
  const [selected, setSelected] = useState(null);
  const [slots, setSlots] = useState([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([getStation(city, stationId), getStationChargers(city, stationId)])
      .then(([s, c]) => {
        if (cancelled) return;
        setStation(s);
        setChargers(c);
      })
      .catch((e) => !cancelled && setError(errorMessage(e)))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [city, stationId]);

  useEffect(() => {
    if (!selected) return;
    let cancelled = false;
    setSlots([]);
    getChargerSlots(city, selected.charger_id)
      .then((s) => !cancelled && setSlots(s))
      .catch((e) => !cancelled && setError(errorMessage(e)));
    return () => {
      cancelled = true;
    };
  }, [city, selected]);

  if (loading) return <p className="muted">Loading station…</p>;
  if (error && !station) return <p className="error">{error}</p>;
  if (!station) return <p>Station not found. <Link to="/search">Back to search</Link></p>;

  return (
    <div>
      <Link to={`/search?city=${city}`} className="muted">← Back to {city} stations</Link>
      <h1>{station.station_name}</h1>
      <p className="muted">{station.address}, {city}</p>
      {error && <p className="error">{error}</p>}

      <h2>Chargers</h2>
      <div className="charger-grid">
        {chargers.map((c) => (
          <button
            key={c.charger_id}
            type="button"
            className={`charger-tile ${selected && selected.charger_id === c.charger_id ? 'selected' : ''}`}
            onClick={() => setSelected(c)}
          >
            <strong>{c.label || `Charger ${c.charger_id}`}</strong>
            <span className="muted small">{c.charger_type} · {c.power_kw} kW</span>
            <span className="muted small">{formatINR(c.price_per_kwh)}/kWh</span>
            <ChargerStatusBadge status={c.status} />
          </button>
        ))}
      </div>

      {selected && (
        <>
          <h2>Pick a slot on {selected.label || `Charger ${selected.charger_id}`}</h2>
          <p className="muted small">Estimated cost for 1 hour: {formatINR(estimateCost(selected, 1))}</p>
          <div className="slot-grid">
            {slots.map((s) => (
              <button
                key={s.slot_id}
                type="button"
                className="slot"
                disabled={!s.is_available}
                onClick={() =>
                  navigate(`/book/${city}/${stationId}?charger=${selected.charger_id}&slot=${s.slot_id}`)
                }
              >
                {formatRange(s.start_time, s.end_time)}
                <span className="small">{s.is_available ? 'Book' : 'Taken'}</span>
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

export default StationDetail;
