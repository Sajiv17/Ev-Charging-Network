import React, { useEffect, useState } from 'react';
import { getAdminOverview, errorMessage } from '../services/api';

function AdminPanel() {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState('');

  useEffect(() => {
    getAdminOverview().then(setRows).catch((e) => setError(errorMessage(e)));
  }, []);

  const sum = (key) => rows.reduce((t, r) => t + (r[key] || 0), 0);

  return (
    <div>
      <h1>Admin Panel</h1>
      {error && <p className="error">{error}</p>}
      <div className="stat-row">
        <div className="card stat"><span className="muted">Stations</span><strong>{sum('stations')}</strong></div>
        <div className="card stat"><span className="muted">Chargers</span><strong>{sum('chargers')}</strong></div>
        <div className="card stat"><span className="muted">Bookings</span><strong>{sum('bookings')}</strong></div>
        <div className="card stat"><span className="muted">Faulted</span><strong>{sum('faulted')}</strong></div>
      </div>
      <div className="card table-wrap">
        <table>
          <thead>
            <tr>
              <th>City</th><th>Stations</th><th>Chargers</th><th>Available</th>
              <th>Occupied</th><th>Faulted</th><th>Bookings</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.city}>
                <td>{r.city}</td><td>{r.stations}</td><td>{r.chargers}</td><td>{r.available}</td>
                <td>{r.occupied}</td><td>{r.faulted}</td><td>{r.bookings}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default AdminPanel;
