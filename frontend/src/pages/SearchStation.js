import React, { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { searchStations, getCities, errorMessage } from '../services/api';
import StationCard from '../components/StationCard';

// File is named SearchStation.js (matches the repo); the component is StationSearch.
function StationSearch() {
  const [params, setParams] = useSearchParams();
  const city = params.get('city') || 'Bangalore';
  const [cities, setCities] = useState([]);
  const [query, setQuery] = useState('');
  const [stations, setStations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    getCities().then(setCities);
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError('');
    searchStations(city)
      .then((data) => !cancelled && setStations(data))
      .catch((e) => !cancelled && setError(errorMessage(e)))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [city]);

  const shown = stations.filter((s) =>
    `${s.station_name} ${s.address}`.toLowerCase().includes(query.toLowerCase())
  );

  return (
    <div>
      <h1>Find Charging Stations</h1>
      <div className="filters">
        <select value={city} onChange={(e) => setParams({ city: e.target.value })}>
          {cities.map((c) => (
            <option key={c}>{c}</option>
          ))}
        </select>
        <input
          placeholder="Search by name or area…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>
      {loading && <p className="muted">Loading stations…</p>}
      {error && <p className="error">{error}</p>}
      {!loading && !error && shown.length === 0 && <p className="muted">No stations found.</p>}
      <div className="grid">
        {shown.map((s) => (
          <StationCard key={s.station_id} station={{ ...s, city: s.city || city }} />
        ))}
      </div>
    </div>
  );
}

export default StationSearch;
