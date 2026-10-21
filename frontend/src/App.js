import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import './App.css';
import './styles/ui.css';

import Header from './components/Header';
import Home from './pages/Home';
import StationSearch from './pages/SearchStation'; // file is SearchStation.js
import StationDetail from './pages/StationDetail';
import BookingFlow from './pages/BookingFlow';
import MyBookings from './pages/MyBookings';
import Dashboard from './pages/Dashboard';
import AdminPanel from './pages/AdminPanel';

function App() {
  return (
    // The Router is the OUTERMOST element. Header uses <NavLink>, so it must
    // live INSIDE it. Header outside the Router = white page + "basename" error.
    <BrowserRouter>
      <Header />
      <main className="container">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/search" element={<StationSearch />} />
          <Route path="/stations/:city/:stationId" element={<StationDetail />} />
          <Route path="/book/:city/:stationId" element={<BookingFlow />} />
          <Route path="/my-bookings" element={<MyBookings />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/admin" element={<AdminPanel />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </BrowserRouter>
  );
}

export default App;
