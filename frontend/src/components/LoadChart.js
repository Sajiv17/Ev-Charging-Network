import React from 'react';

// Simple CSS bar chart: bookings per hour. data = [{ hour: 9, bookings: 4 }, ...]
function LoadChart({ data = [] }) {
  const max = Math.max(1, ...data.map((d) => d.bookings));
  return (
    <div className="card">
      <h3>Booking load per hour</h3>
      <div className="chart">
        {data.map((d) => (
          <div className="chart-col" key={d.hour} title={`${d.bookings} bookings`}>
            <span className="chart-val">{d.bookings}</span>
            <div className="chart-bar" style={{ height: `${(d.bookings / max) * 100}%` }} />
            <span className="chart-label">{d.hour}:00</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default LoadChart;
