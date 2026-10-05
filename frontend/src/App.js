import React from 'react';
import './App.css';

function App() {
  return (
    <div className="App">
      <header className="App-header">
        <h1>⚡ EV Charging Network</h1>
        <p>Multi-city EV charging slot booking platform</p>
        <div className="status-cards">
          <div className="status-card">
            <h3>Frontend</h3>
            <span className="status-badge running">Running</span>
          </div>
          <div className="status-card">
            <h3>Backend API</h3>
            <span className="status-badge">Check localhost:8000</span>
          </div>
          <div className="status-card">
            <h3>MySQL Nodes</h3>
            <span className="status-badge">3 cities</span>
          </div>
          <div className="status-card">
            <h3>MongoDB</h3>
            <span className="status-badge">Real-time data</span>
          </div>
        </div>
        <p className="info">
          Ready for development. Team members can start building their components.
        </p>
      </header>
    </div>
  );
}

export default App;
