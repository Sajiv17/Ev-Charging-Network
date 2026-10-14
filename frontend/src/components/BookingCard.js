import React from 'react';
import { formatRange, isUpcoming } from '../utils/dateUtils';
import { formatINR } from '../utils/priceCalculator';

const STATUS_COLOR = { confirmed: 'green', completed: 'gray', cancelled: 'red', active: 'yellow' };

function BookingCard({ booking, onCancel }) {
  const canCancel = booking.booking_status === 'confirmed' && isUpcoming(booking.start_time);
  return (
    <div className="card booking-card">
      <div className="card-top">
        <h3>{booking.station_name}</h3>
        <span className={`badge badge-${STATUS_COLOR[booking.booking_status] || 'gray'}`}>
          {booking.booking_status}
        </span>
      </div>
      <p className="muted">
        {booking.city}
        {booking.charger_label ? ` · ${booking.charger_label}` : ''}
      </p>
      <p>{formatRange(booking.start_time, booking.end_time)}</p>
      <p className="strong">{formatINR(booking.booking_amount)}</p>
      {canCancel && onCancel && (
        <button className="btn btn-outline" onClick={() => onCancel(booking.booking_id)}>
          Cancel booking
        </button>
      )}
    </div>
  );
}

export default BookingCard;
