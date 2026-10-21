import React from 'react';
import ReactDOM from 'react-dom/client';
import './index.css';
import App from './App';

// NOTE: do NOT put <BrowserRouter> here AND in App.js. Exactly one Router,
// and it must wrap everything that uses <Link>/<NavLink> (including Header).
const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
