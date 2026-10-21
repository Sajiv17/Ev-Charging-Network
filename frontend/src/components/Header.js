import React, { useEffect, useState } from 'react';
import { NavLink, Link } from 'react-router-dom';
import { isDemoMode } from '../services/api';

const links = [
  { to: '/', label: 'Home', end: true },
  { to: '/search', label: 'Find Stations' },
  { to: '/my-bookings', label: 'My Bookings' },
  { to: '/dashboard', label: 'Operator Dashboard' },
  { to: '/admin', label: 'Admin' },
];

// Must be rendered INSIDE <BrowserRouter> (see App.js).
function Header() {
  const [demo, setDemo] = useState(isDemoMode());

  useEffect(() => {
    const on = () => setDemo(true);
    window.addEventListener('ev-demo-mode', on);
    return () => window.removeEventListener('ev-demo-mode', on);
  }, []);

  return (
    <>
      <header className="header">
        <div className="header-inner">
          <Link to="/" className="logo">⚡ EV Charging Network</Link>
          <nav className="nav">
            {links.map((l) => (
              <NavLink
                key={l.to}
                to={l.to}
                end={l.end}
                className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}
              >
                {l.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>
      {demo && (
        <div className="demo-banner" role="status">
          Backend API not reachable, showing demo data. Nothing here is saved to the real database.
        </div>
      )}
    </>
  );
}

export default Header;
  