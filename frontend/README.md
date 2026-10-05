# Frontend — Person 4 (Frontend Developer)

## Your Responsibility

Build the React UI for drivers, operators, and admins — booking flow, live dashboard, and admin panel.

---

## What You Build

### 📁 `src/pages/`
**Empty — you create these**

One file per route/page:

**Tasks:**
- `Home.js` — Landing page with city selection
- `StationSearch.js` — Search and filter stations by city/location
- `StationDetail.js` — Show station details, available chargers, slot picker
- `BookingFlow.js` — 3-step booking form (pick slot → confirm → pay)
- `MyBookings.js` — User's upcoming, active, and past bookings
- `Dashboard.js` — Live station dashboard (for operators)
- `AdminPanel.js` — Network-wide admin view

**Example `StationSearch.js`:**
```javascript
import React, { useState, useEffect } from 'react';
import { searchStations } from '../services/api';

function StationSearch() {
  const [city, setCity] = useState('Bangalore');
  const [stations, setStations] = useState([]);
  
  useEffect(() => {
    searchStations(city).then(data => setStations(data));
  }, [city]);
  
  return (
    <div>
      <h1>Find Charging Stations</h1>
      <select value={city} onChange={e => setCity(e.target.value)}>
        <option>Bangalore</option>
        <option>Chennai</option>
        <option>Delhi</option>
      </select>
      
      <div className="station-list">
        {stations.map(s => (
          <div key={s.station_id} className="station-card">
            <h3>{s.station_name}</h3>
            <p>{s.address}</p>
            <span className="badge">{s.available_chargers} available</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default StationSearch;
```

### 📁 `src/components/`
**Empty — you create these**

Reusable UI components:

**Tasks:**
- `Header.js` — Navigation bar with logo, links, user menu
- `StationCard.js` — Card showing one station
- `ChargerStatusBadge.js` — Color-coded badge (green/yellow/red) for charger status
- `BookingCard.js` — Card showing one booking
- `LiveStatusPanel.js` — Real-time charger status widget (polls MongoDB data every 5 sec)
- `LoadChart.js` — Bar chart showing booking load per hour

**Example `ChargerStatusBadge.js`:**
```javascript
import React from 'react';
import './ChargerStatusBadge.css';

function ChargerStatusBadge({ status }) {
  const colors = {
    available: 'green',
    occupied: 'yellow',
    faulted: 'red',
    maintenance: 'gray'
  };
  
  return (
    <span className={`badge badge-${colors[status]}`}>
      {status}
    </span>
  );
}

export default ChargerStatusBadge;
```

### 📁 `src/services/`
**Empty — you create these**

API client to talk to backend:

**Tasks:**
- `api.js` — axios wrapper for all API calls

**Example `api.js`:**
```javascript
import axios from 'axios';

const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';

export const searchStations = async (city) => {
  const res = await axios.get(`${API_BASE}/api/stations`, { params: { city } });
  return res.data;
};

export const createBooking = async (userId, slotId, vehicleId) => {
  const res = await axios.post(`${API_BASE}/api/bookings`, {
    user_id: userId,
    slot_id: slotId,
    vehicle_id: vehicleId
  });
  return res.data;
};

export const getChargerStatus = async (chargerId) => {
  const res = await axios.get(`${API_BASE}/api/chargers/${chargerId}/status`);
  return res.data;
};

export const getMyBookings = async (userId) => {
  const res = await axios.get(`${API_BASE}/api/bookings`, { params: { user_id: userId } });
  return res.data;
};
```

### 📁 `src/utils/`
**Empty — you create these**

**Tasks:**
- `dateUtils.js` — format dates/times
- `priceCalculator.js` — calculate booking cost

---

## Routing

In `src/App.js`, set up React Router:

```javascript
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Home from './pages/Home';
import StationSearch from './pages/StationSearch';
import BookingFlow from './pages/BookingFlow';
import MyBookings from './pages/MyBookings';
import Dashboard from './pages/Dashboard';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/search" element={<StationSearch />} />
        <Route path="/book/:stationId" element={<BookingFlow />} />
        <Route path="/my-bookings" element={<MyBookings />} />
        <Route path="/dashboard" element={<Dashboard />} />
      </Routes>
    </BrowserRouter>
  );
}
```

---

## Live Dashboard (Key Feature)

Create `pages/Dashboard.js`:
- Shows all chargers at operator's station
- Polls backend every 5 seconds for live status from MongoDB
- Color-coded status badges
- Click a charger to see active booking details

```javascript
useEffect(() => {
  const interval = setInterval(() => {
    fetchChargerStatus().then(data => setChargers(data));
  }, 5000); // Poll every 5 seconds
  
  return () => clearInterval(interval);
}, []);
```

---

## Styling

You can use:
- Plain CSS (already set up in `src/index.css` and `src/App.css`)
- Or add Tailwind CSS / Material-UI if you want

---

## Testing Your Work

```bash
# Start frontend
cd frontend
npm install
npm start

# Access at http://localhost:3000
```

Make sure backend is running too:
```bash
docker-compose up backend
```

---

## Your Branch

```bash
git checkout -b frontend-ui
# Make changes
git add frontend/
git commit -m "feat(frontend): add station search and booking flow"
git push origin frontend-ui
# Open PR to main
```

---

## What You DON'T Touch

- ❌ `database/` — Person 1's territory
- ❌ `backend/` (except coordinating API contract with Person 2)
- ❌ `docker/` — Person 3's territory
