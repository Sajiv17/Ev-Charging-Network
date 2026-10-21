import React, { useEffect, useState } from 'react';
import { useParams, useSearchParams, Link } from 'react-router-dom';
import {
  getStation, getStationChargers, getChargerSlots, createBooking, errorMessage,
  DEMO_USER_ID, DEMO_VEHICLE_ID,
} from '../services/api';
import { formatRange } from '../utils/dateUtils';
import { estimateCost, formatINR } from '../utils/priceCalculator';

const STEPS = ['Pick slot', 'Confirm', 'Pay'];

function BookingFlow() {
  const { city, stationId } = useParams();
  const [params] = useSearchParams();
  const [step, setStep] = useState(1);
  const [station, setStation] = useState(null);
  const [chargers, setChargers] = useState([]);
  const [chargerId, setChargerId] = useState(Number(params.get('charger')) || null);
  const [slots, setSlots] = useState([]);
  const [slotId, setSlotId] = useState(Number(params.get('slot')) || null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);

  useEffect(() => {
    Promise.all([getStation(city, stationId), getStationChargers(city, stationId)])
      .then(([s, c]) => {
        setStation(s);
        setChargers(c);
      })
      .catch((e) => setError(errorMessage(e)));
  }, [city, stationId]);

  useEffect(() => {
    if (!chargerId) return;
    getChargerSlots(city, chargerId)
      .then(setSlots)
      .catch((e) => setError(errorMessage(e)));
  }, [city, chargerId]);

  const charger = chargers.find((c) => c.charger_id === chargerId);
  const slot = slots.find((s) => s.slot_id === slotId);

  const pay = async () => {
    setBusy(true);
    setError('');
    try {
      // No payment endpoint exists yet: booking creation is the whole "pay" step.
      const res = await createBooking({
        userId: DEMO_USER_ID, slotId, vehicleId: DEMO_VEHICLE_ID, city,
      });
      setResult(res);
    } catch (e) {
      setError(errorMessage(e)); // e.g. "Slot not available" from the backend's lock
    } finally {
      setBusy(false);
    }
  };

  if (result) {
    return (
      <div className="card center">
        <h1>Booking confirmed ✅</h1>
        <p>Booking #{result.booking_id}</p>
        <Link className="btn" to="/my-bookings">View my bookings</Link>
      </div>
    );
  }

  return (
    <div>
      <h1>Book a slot{station ? ` at ${station.station_name}` : ''}</h1>
      <ol className="steps">
        {STEPS.map((label, i) => (
          <li key={label} className={step === i + 1 ? 'on' : step > i + 1 ? 'done' : ''}>{label}</li>
        ))}
      </ol>
      {error && <p className="error">{error}</p>}

      {step === 1 && (
        <div className="card">
          <label>Charger
            <select
              value={chargerId || ''}
              onChange={(e) => { setChargerId(Number(e.target.value)); setSlotId(null); }}
            >
              <option value="" disabled>Select a charger</option>
              {chargers.map((c) => (
                <option key={c.charger_id} value={c.charger_id}>
                  {c.label} · {c.charger_type} · {c.power_kw} kW
                </option>
              ))}
            </select>
          </label>
          <div className="slot-grid">
            {slots.map((s) => (
              <button
                key={s.slot_id}
                type="button"
                disabled={!s.is_available}
                className={`slot ${slotId === s.slot_id ? 'selected' : ''}`}
                onClick={() => setSlotId(s.slot_id)}
              >
                {formatRange(s.start_time, s.end_time)}
              </button>
            ))}
          </div>
          <button className="btn" disabled={!slot} onClick={() => setStep(2)}>Continue</button>
        </div>
      )}

      {step === 2 && slot && charger && (
        <div className="card">
          <h3>Confirm details</h3>
          <p>{station && station.station_name}, {city}</p>
          <p>{charger.label} · {charger.charger_type}</p>
          <p>{formatRange(slot.start_time, slot.end_time)}</p>
          <p className="strong">Estimated: {formatINR(estimateCost(charger, 1))}</p>
          <button className="btn btn-outline" onClick={() => setStep(1)}>Back</button>{' '}
          <button className="btn" onClick={() => setStep(3)}>Proceed to pay</button>
        </div>
      )}

      {step === 3 && (
        <div className="card">
          <h3>Pay from wallet</h3>
          <p className="muted">Demo user wallet. The real amount is calculated by the backend.</p>
          <button className="btn btn-outline" onClick={() => setStep(2)} disabled={busy}>Back</button>{' '}
          <button className="btn" onClick={pay} disabled={busy}>
            {busy ? 'Booking…' : `Pay ${formatINR(estimateCost(charger, 1))}`}
          </button>
        </div>
      )}
    </div>
  );
}

export default BookingFlow;
 