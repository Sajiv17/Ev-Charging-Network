import React, { useEffect, useState } from 'react';
import { searchStations, getHourlyLoad, getCities } from '../services/api';
import LiveStatusPanel from '../components/LiveStatusPanel';
import LoadChart from '../components/LoadChart';

// Operator dashboard. There is no operator login/ownership endpoint yet,
// so the operator picks a city + station manually.
function Dashboard() {
  const [cities, setCities] = useState([]);
  const [city, setCity] = useState('Bangalore');
  const [stations, setStations] = useState([]);
  const [stationId, setStationId] = useState(null);
  const [load, setLoad] = useState([]);
  const [picked, setPicked] = useState(null);

  useEffect(() => { getCities().then(setCities); }, []);

  useEffect(() => {
    let cancelled = false;
    searchStations(city).then((s) => {
      if (cancelled) return;
      setStations(s);
      setStationId(s.length ? s[0].station_id : null);
    }).catch(() => !cancelled && setStations([]));
    getHourlyLoad(city).then((d) => !cancelled && setLoad(d)).catch(() => {});
    return () => { cancelled = true; };
  }, [city]);

  return (
    <div>
      <h1>Operator Dashboard</h1>
      <div className="filters">
        <select value={city} onChange={(e) => setCity(e.target.value)}>
          {cities.map((c) => <option key={c}>{c}</option>)}
        </select>
        <select value={stationId || ''} onChange={(e) => setStationId(Number(e.target.value))}>
          {stations.map((s) => <option key={s.station_id} value={s.station_id}>{s.station_name}</option>)}
        </select>
      </div>
      {stationId && (
        <LiveStatusPanel city={city} stationId={stationId} onSelect={setPicked} />
      )}
      {picked && (
        <div className="card">
          <h3>{picked.label || `Charger ${picked.charger_id}`}</h3>
          <p className="muted">Status: {picked.status}. Active booking details need a backend endpoint (see docs).</p>
        </div>
      )}
      <LoadChart data={load} />
    </div>
  );
}

export default Dashboard;
