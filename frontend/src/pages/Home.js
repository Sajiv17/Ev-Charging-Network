import React from 'react';
import { Link } from 'react-router-dom';
import { CITY_LIST } from '../services/mockData';

function Home() {
  return (
    <div>
      <section className="hero">
        <h1>Book an EV charging slot in minutes</h1>
        <p>Pick your city, choose a station, reserve a time slot.</p>
      </section>
      <div className="city-grid">
        {CITY_LIST.map((city) => (
          <Link key={city} to={`/search?city=${city}`} className="card city-card">
            <h2>{city}</h2>
            <span className="muted">Find stations →</span>
          </Link>
        ))}
      </div>
    </div>
  );
}

export default Home;
