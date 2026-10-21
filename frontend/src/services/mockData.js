// Demo data used ONLY when the backend is unreachable (or REACT_APP_USE_MOCK=true).
// Shapes follow the field names in backend/README.md (station_id, station_name, ...).
// Replace/remove once Person 2's endpoints are live.

const CITIES = ['Bangalore', 'Chennai', 'Delhi'];

const stations = [
  { station_id: 1, city: 'Bangalore', station_name: 'Indiranagar Fast Hub', address: '100 Feet Rd, Indiranagar', total_chargers: 6 },
  { station_id: 2, city: 'Bangalore', station_name: 'Whitefield Tech Park Charge', address: 'ITPL Main Rd, Whitefield', total_chargers: 4 },
  { station_id: 3, city: 'Chennai', station_name: 'T. Nagar Charge Point', address: 'Usman Rd, T. Nagar', total_chargers: 5 },
  { station_id: 4, city: 'Chennai', station_name: 'OMR IT Corridor Station', address: 'Rajiv Gandhi Salai, OMR', total_chargers: 4 },
  { station_id: 5, city: 'Delhi', station_name: 'Connaught Place Hub', address: 'Block F, Connaught Place', total_chargers: 6 },
  { station_id: 6, city: 'Delhi', station_name: 'Dwarka Sector 21 Station', address: 'Sector 21, Dwarka', total_chargers: 3 },
];

const TYPES = [
  { charger_type: 'DC Fast (CCS2)', power_kw: 60, price_per_kwh: 18 },
  { charger_type: 'AC Type 2', power_kw: 22, price_per_kwh: 12 },
  { charger_type: 'DC Fast (CCS2)', power_kw: 120, price_per_kwh: 22 },
];
const STATUSES = ['available', 'occupied', 'faulted', 'maintenance'];

let chargers = [];
stations.forEach((s) => {
  for (let i = 0; i < s.total_chargers; i++) {
    const t = TYPES[i % TYPES.length];
    chargers.push({
      charger_id: s.station_id * 100 + i + 1,
      station_id: s.station_id,
      city: s.city,
      label: `Charger ${i + 1}`,
      ...t,
      status: i % 5 === 3 ? 'occupied' : i % 7 === 6 ? 'faulted' : 'available',
    });
  }
});

let bookings = [
  {
    booking_id: 9001, user_id: 1, city: 'Bangalore', station_id: 1,
    station_name: 'Indiranagar Fast Hub', charger_label: 'Charger 2',
    start_time: new Date(Date.now() + 3 * 3600e3).toISOString(),
    end_time: new Date(Date.now() + 4 * 3600e3).toISOString(),
    booking_status: 'confirmed', booking_amount: 180,
  },
  {
    booking_id: 9000, user_id: 1, city: 'Chennai', station_id: 3,
    station_name: 'T. Nagar Charge Point', charger_label: 'Charger 1',
    start_time: new Date(Date.now() - 48 * 3600e3).toISOString(),
    end_time: new Date(Date.now() - 47 * 3600e3).toISOString(),
    booking_status: 'completed', booking_amount: 240,
  },
];
let nextBookingId = 9002;

const delay = (v, ms = 250) => new Promise((r) => setTimeout(() => r(v), ms));

function slotsFor(charger) {
  const base = new Date();
  base.setMinutes(0, 0, 0);
  const out = [];
  for (let h = 1; h <= 8; h++) {
    const start = new Date(base.getTime() + h * 3600e3);
    const end = new Date(start.getTime() + 3600e3);
    const taken = bookings.some(
      (b) => b.charger_id === charger.charger_id && b.start_time === start.toISOString() && b.booking_status !== 'cancelled'
    );
    out.push({
      slot_id: charger.charger_id * 1000 + h,
      charger_id: charger.charger_id,
      start_time: start.toISOString(),
      end_time: end.toISOString(),
      is_available: !taken && (charger.charger_id + h) % 4 !== 0,
    });
  }
  return out;
}

export const mock = {
  cities: () => delay(CITIES),
  searchStations: (city) =>
    delay(
      stations
        .filter((s) => !city || s.city === city)
        .map((s) => ({
          ...s,
          available_chargers: chargers.filter((c) => c.station_id === s.station_id && c.status === 'available').length,
        }))
    ),
  getStation: (city, id) => {
    const s = stations.find((x) => x.station_id === Number(id));
    return delay(s ? { ...s } : null);
  },
  getChargers: (city, stationId) =>
    delay(chargers.filter((c) => c.station_id === Number(stationId)).map((c) => ({ ...c }))),
  getSlots: (city, chargerId) => {
    const c = chargers.find((x) => x.charger_id === Number(chargerId));
    return delay(c ? slotsFor(c) : []);
  },
  // Live status: randomly flips one charger so the 5s polling is visibly working.
  getLiveStatus: (city, stationId) => {
    const list = chargers.filter((c) => c.station_id === Number(stationId));
    if (list.length && Math.random() < 0.5) {
      const c = list[Math.floor(Math.random() * list.length)];
      c.status = STATUSES[Math.floor(Math.random() * 3)];
    }
    return delay(list.map((c) => ({ ...c, updated_at: new Date().toISOString() })), 150);
  },
  createBooking: ({ user_id, slot_id, city }) => {
    const charger = chargers.find((c) => Math.floor(slot_id / 1000) === c.charger_id);
    if (!charger) return Promise.reject(new Error('Slot not found'));
    const hour = slot_id % 1000;
    const base = new Date();
    base.setMinutes(0, 0, 0);
    const start = new Date(base.getTime() + hour * 3600e3);
    const station = stations.find((s) => s.station_id === charger.station_id);
    const b = {
      booking_id: nextBookingId++, user_id, city: city || station.city,
      station_id: station.station_id, station_name: station.station_name,
      charger_id: charger.charger_id, charger_label: charger.label,
      start_time: start.toISOString(), end_time: new Date(start.getTime() + 3600e3).toISOString(),
      booking_status: 'confirmed', booking_amount: Math.round(charger.power_kw * 0.5 * charger.price_per_kwh),
    };
    bookings = [b, ...bookings];
    return delay({ booking_id: b.booking_id, status: 'confirmed' });
  },
  getMyBookings: (userId) => delay(bookings.filter((b) => b.user_id === Number(userId)).map((b) => ({ ...b }))),
  cancelBooking: (id) => {
    bookings = bookings.map((b) => (b.booking_id === Number(id) ? { ...b, booking_status: 'cancelled' } : b));
    return delay({ booking_id: id, status: 'cancelled' });
  },
  getAdminOverview: () =>
    delay(
      CITIES.map((city) => {
        const cs = chargers.filter((c) => c.city === city);
        return {
          city,
          stations: stations.filter((s) => s.city === city).length,
          chargers: cs.length,
          available: cs.filter((c) => c.status === 'available').length,
          occupied: cs.filter((c) => c.status === 'occupied').length,
          faulted: cs.filter((c) => c.status === 'faulted').length,
          bookings: bookings.filter((b) => b.city === city).length,
        };
      })
    ),
  getHourlyLoad: () =>
    delay(Array.from({ length: 12 }, (_, i) => ({ hour: 8 + i, bookings: [2, 4, 6, 5, 3, 3, 4, 6, 9, 11, 8, 5][i] }))),
};

export const CITY_LIST = CITIES;
