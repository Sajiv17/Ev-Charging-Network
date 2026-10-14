import React, { useCallback, useEffect, useState } from 'react';
import { getMyBookings, cancelBooking, errorMessage, DEMO_USER_ID } from '../services/api';
import BookingCard from '../components/BookingCard';

function MyBookings() {
  const [bookings, setBookings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(() => {
    setLoading(true);
    getMyBookings(DEMO_USER_ID)
      .then(setBookings)
      .catch((e) => setError(errorMessage(e)))
      .finally(() => setLoading(false));
  }, []);

  useEffect(load, [load]);

  const onCancel = async (id) => {
    try {
      await cancelBooking(id);
      load();
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  const now = Date.now();
  const upcoming = bookings.filter((b) => b.booking_status === 'confirmed' && new Date(b.end_time) > now);
  const past = bookings.filter((b) => !upcoming.includes(b));

  return (
    <div>
      <h1>My Bookings</h1>
      {loading && <p className="muted">Loading…</p>}
      {error && <p className="error">{error}</p>}
      <h2>Upcoming</h2>
      {!loading && upcoming.length === 0 && <p className="muted">No upcoming bookings.</p>}
      <div className="grid">
        {upcoming.map((b) => <BookingCard key={b.booking_id} booking={b} onCancel={onCancel} />)}
      </div>
      <h2>Past &amp; cancelled</h2>
      {!loading && past.length === 0 && <p className="muted">Nothing here yet.</p>}
      <div className="grid">
        {past.map((b) => <BookingCard key={b.booking_id} booking={b} />)}
      </div>
    </div>
  );
}

export default MyBookings;
