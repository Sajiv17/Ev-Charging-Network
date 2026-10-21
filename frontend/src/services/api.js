import axios from 'axios';
import { mock, CITY_LIST } from './mockData';

const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';
const FORCE_MOCK = process.env.REACT_APP_USE_MOCK === 'true';

// ---------------------------------------------------------------------------
// !! UNVERIFIED ENDPOINTS !!
// The backend currently exposes only GET / and GET /health (all routers are
// commented out in backend/app/main.py). The paths below come from
// backend/README.md and frontend/README.md. Confirm each one with Person 2
// and change ONLY this table when the real contract is known.
// ---------------------------------------------------------------------------
export const ENDPOINTS = {
  stations: '/api/stations',                         // GET ?city=
  station: (id) => `/api/stations/${id}`,            // GET ?city=
  stationChargers: (id) => `/api/stations/${id}/chargers`, // GET ?city=   (assumed)
  chargerSlots: (id) => `/api/chargers/${id}/slots`, // GET ?city=   (assumed)
  chargerStatus: (stationId) => `/api/stations/${stationId}/chargers/status`, // GET ?city= (assumed; README only lists /api/chargers/{id}/status)
  bookings: '/api/bookings',                         // GET ?user_id= , POST
  cancelBooking: (id) => `/api/bookings/${id}`,      // DELETE (assumed)
  adminOverview: '/api/admin/overview',              // GET (assumed)
  hourlyLoad: '/api/stations/load',                  // GET ?city= (assumed)
};

// --- demo-mode notification (Header shows a banner when this fires) ---------
let demoActive = FORCE_MOCK;
export const isDemoMode = () => demoActive;
function enterDemoMode() {
  if (!demoActive) {
    demoActive = true;
    window.dispatchEvent(new Event('ev-demo-mode'));
  }
}

// Try the real API; if the server is unreachable or the route does not exist
// yet (404/405/501), fall back to demo data. Real validation errors (400/409/
// 422...) are NOT swallowed, so booking conflicts still show properly.
async function call(real, fake) {
  if (FORCE_MOCK) return fake();
  try {
    return await real();
  } catch (err) {
    const status = err.response && err.response.status;
    const unreachable = !err.response; // network error / CORS / server down
    if (unreachable || [404, 405, 501].includes(status)) {
      enterDemoMode();
      return fake();
    }
    throw err;
  }
}

const http = axios.create({ baseURL: API_BASE, timeout: 8000 });

export const errorMessage = (err) =>
  (err && err.response && err.response.data && (err.response.data.detail || err.response.data.message)) ||
  (err && err.message) ||
  'Something went wrong';

export const getCities = () => Promise.resolve(CITY_LIST);

export const searchStations = (city) =>
  call(async () => (await http.get(ENDPOINTS.stations, { params: { city } })).data, () => mock.searchStations(city));

export const getStation = (city, id) =>
  call(async () => (await http.get(ENDPOINTS.station(id), { params: { city } })).data, () => mock.getStation(city, id));

export const getStationChargers = (city, id) =>
  call(async () => (await http.get(ENDPOINTS.stationChargers(id), { params: { city } })).data, () => mock.getChargers(city, id));

export const getChargerSlots = (city, chargerId) =>
  call(async () => (await http.get(ENDPOINTS.chargerSlots(chargerId), { params: { city } })).data, () => mock.getSlots(city, chargerId));

export const getLiveStatus = (city, stationId) =>
  call(async () => (await http.get(ENDPOINTS.chargerStatus(stationId), { params: { city } })).data, () => mock.getLiveStatus(city, stationId));

export const createBooking = ({ userId, slotId, vehicleId, city }) =>
  call(
    async () =>
      (await http.post(ENDPOINTS.bookings, { user_id: userId, slot_id: slotId, vehicle_id: vehicleId, city })).data,
    () => mock.createBooking({ user_id: userId, slot_id: slotId, vehicle_id: vehicleId, city })
  );

export const getMyBookings = (userId) =>
  call(async () => (await http.get(ENDPOINTS.bookings, { params: { user_id: userId } })).data, () => mock.getMyBookings(userId));

export const cancelBooking = (id) =>
  call(async () => (await http.delete(ENDPOINTS.cancelBooking(id))).data, () => mock.cancelBooking(id));

export const getAdminOverview = () =>
  call(async () => (await http.get(ENDPOINTS.adminOverview)).data, () => mock.getAdminOverview());

export const getHourlyLoad = (city) =>
  call(async () => (await http.get(ENDPOINTS.hourlyLoad, { params: { city } })).data, () => mock.getHourlyLoad(city));

// No auth endpoint exists yet, so the UI uses a fixed demo user.
export const DEMO_USER_ID = 1;
export const DEMO_VEHICLE_ID = 1;
