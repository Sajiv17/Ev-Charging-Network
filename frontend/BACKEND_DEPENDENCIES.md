# Frontend → Backend dependencies (Person 4 → Person 2)

Status when written: the backend (`backend/app/main.py`) only serves `GET /` and
`GET /health`. All routers are commented out. Until they exist, the frontend falls
back to **demo data** (`src/services/mockData.js`) and shows a yellow banner.

Every URL below lives in ONE place: `ENDPOINTS` in `src/services/api.js`.
Paths marked *(assumed)* are guesses, not from the README. Please confirm or correct.

| # | Frontend need | Method + path used | Source | Fields the UI reads |
|---|---------------|--------------------|--------|---------------------|
| 1 | Search stations by city | `GET /api/stations?city=` | README | `station_id, station_name, address, city, available_chargers, total_chargers` |
| 2 | One station | `GET /api/stations/{id}?city=` | assumed | same as above |
| 3 | Chargers of a station | `GET /api/stations/{id}/chargers?city=` | assumed | `charger_id, label, charger_type, power_kw, price_per_kwh, status` |
| 4 | Slots of a charger | `GET /api/chargers/{id}/slots?city=` | assumed | `slot_id, charger_id, start_time, end_time, is_available` |
| 5 | Live status (polled every 5 s) | `GET /api/stations/{id}/chargers/status?city=` | assumed (README only lists `/api/chargers/{id}/status`) | charger list + `status` (`available/occupied/faulted/maintenance`) |
| 6 | Create booking | `POST /api/bookings` body `{user_id, slot_id, vehicle_id, city}` | README | `booking_id, status` |
| 7 | My bookings | `GET /api/bookings?user_id=` | README | `booking_id, station_name, city, charger_label, start_time, end_time, booking_status, booking_amount` |
| 8 | Cancel booking | `DELETE /api/bookings/{id}` | assumed | n/a |
| 9 | Admin overview | `GET /api/admin/overview` | assumed | per city: `city, stations, chargers, available, occupied, faulted, bookings` |
| 10 | Hourly load chart | `GET /api/stations/load?city=` | assumed | `[{hour, bookings}]` |

## Open questions / gaps

1. **City routing:** the DB is split into 3 MySQL nodes. The UI sends `city` as a query
   param on every call. Is that the contract? (README's `POST /bookings` takes `city`.)
2. **No auth / users endpoint:** the UI uses a fixed demo user (`DEMO_USER_ID = 1`,
   `DEMO_VEHICLE_ID = 1` in `api.js`). Needs login/registration + a way to list the user's vehicles.
3. **No payment endpoint:** the "Pay" step just calls `POST /api/bookings` (wallet debit happens
   inside the booking transaction per the backend README).
4. **Operator ownership:** the Dashboard lets the operator pick any station. Needs an
   "stations owned by this operator" endpoint.
5. **Active booking per charger:** clicking a charger on the Dashboard should show its active
   booking. Needs the booking info in the live-status payload or a separate endpoint.
6. **CORS:** the backend must allow `http://localhost:3000` (check `CORSMiddleware` in `main.py`).
7. **Error shape:** the UI shows `response.data.detail` (FastAPI default) for 4xx errors, e.g. "Slot not available".

## Switching modes

- Normal: leave `REACT_APP_USE_MOCK` unset. Real API first, demo data only if the server is
  unreachable or the route returns 404/405/501.
- Force demo data: `REACT_APP_USE_MOCK=true` in `frontend/.env`.
- Different API URL: `REACT_APP_API_URL=http://localhost:8000` in `frontend/.env`.
