# API Reference (for Person 4 - Frontend)

Base URL: `http://localhost:8000`
Interactive docs with "Try it out": **http://localhost:8000/docs**

## Conventions

- **Auth:** log in, then send `Authorization: Bearer <access_token>` on every 🔒 request.
- **Cities:** `bangalore`, `chennai`, `delhi` (lowercase). Each city is a separate MySQL node,
  so station, slot and booking IDs are only unique **within a city**. Always keep the pair
  `(city, id)` in the frontend.
- **Errors** always look like `{"detail": "human message", "code": "machine_code"}`.
  Show `detail` to the user, branch on `code`.

| HTTP | code | Meaning |
|------|------|---------|
| 400 | `bad_request`, `connector_mismatch` | Invalid input |
| 401 | | Not logged in or token expired → go to login |
| 402 | `insufficient_balance` | Wallet too low → offer top-up |
| 404 | `not_found` | |
| 409 | `slot_unavailable`, `slot_in_past`, `charger_unavailable` | Someone else got the slot → refresh slots |
| 409 | `email_taken`, `not_cancellable` | |
| 409 | `outside_slot_window`, `not_startable`, `not_active`, `charger_busy` | Session start/end not allowed now |
| 400 | `energy_too_high` | Session end: more kWh than the slot can deliver |
| 403 | `forbidden` | Operator acting on another operator's station |
| 503 | `node_unavailable`, `lock_timeout` | A city node is down / busy → retry |

## Users

| Method | Path | Body / Query | Returns |
|--------|------|--------------|---------|
| POST | `/api/users/register` | `{email, password, full_name, phone?, home_city, role?}` | `{access_token, user}` |
| POST | `/api/users/login` | `{email, password}` | `{access_token, user}` |
| GET 🔒 | `/api/users/me` | | user |
| GET 🔒 | `/api/users/me/wallet` | | `{user_id, home_city, wallet_balance}` |
| POST 🔒 | `/api/users/me/wallet/topup` | `{amount}` | same as above |
| GET 🔒 | `/api/users/me/vehicles` | | `[vehicle]` |
| POST 🔒 | `/api/users/me/vehicles` | `{make, model, battery_capacity_kwh, connector_type, registration_number?}` | vehicle |
| DELETE 🔒 | `/api/users/me/vehicles/{vehicle_id}` | | 204 |

`user = {user_id, email, full_name, phone, role, home_city, wallet_balance}`
`connector_type` is one of `CCS2`, `CHAdeMO`, `Type2`.

## Stations and slots

| Method | Path | Query | Returns |
|--------|------|-------|---------|
| GET | `/api/stations/cities` | | `[{key, city_id, name}]` |
| GET | `/api/stations` | `city, date? (YYYY-MM-DD, default today), connector_type?, charger_type? (AC/DC), from_time?, to_time? (HH:MM)` | `[station summary]` |
| GET | `/api/stations/{city}/{station_id}` | | station + `chargers[]` |
| GET | `/api/stations/{city}/{station_id}/slots` | `date? (default today), connector_type?, only_available? (default true)` | `[slot]` |

`city` is case-insensitive (`Bangalore` and `bangalore` both work), so a dropdown with
display names can send its value directly.

Station summary: `{city, station_id, station_name, address, latitude, longitude, on_date, matching_chargers, available_chargers, available_slots, max_power_kw}`

- `matching_chargers`: working chargers that fit the filters
- `available_chargers`: of those, how many still have at least one free slot on `on_date`
  (use this for the "N available" badge)
- `available_slots`: total free slots across them on `on_date`

Note: the frontend README's example `createBooking(userId, slotId, vehicleId)` and
`getMyBookings(userId)` don't match this API. The user comes from the login token, not a
`user_id` field (otherwise anyone could book as anyone), and a booking needs `city`.
Use `POST /api/bookings` with `{city, slot_id, vehicle_id}` and `GET /api/bookings`, both with
the `Authorization` header.

Slot: `{city, slot_id, charger_id, charger_code, charger_type, connector_type, max_power_kw, slot_date, start_time, end_time, is_available, estimated_max_price}`

Tip: pass the user's vehicle `connector_type` to only show compatible chargers.

## Bookings 🔒

| Method | Path | Body | Returns |
|--------|------|------|---------|
| POST | `/api/bookings` | `{city, slot_id, vehicle_id}` | booking (201) |
| GET | `/api/bookings` | | `[booking]`, all cities, newest first |
| GET | `/api/bookings/{city}/{booking_id}` | | booking |
| POST | `/api/bookings/{city}/{booking_id}/cancel` | | `{city, booking_id, booking_status, refund_amount, wallet_balance_after}` |

Booking: `{city, booking_id, booking_status, booking_amount, slot_id, vehicle_id, charger_id, charger_code, station_id, station_name, slot_date, start_time, end_time, payment_id, payment_status, transaction_id, wallet_balance_after, created_at, distributed}`

`booking_status`: `confirmed`, `active`, `completed`, `cancelled`.
The booking amount is a **prepayment** for the most energy the slot can deliver; when the
session ends, the unused part is refunded to the wallet.

**Booking in another city works the same way from the frontend.** If the station's city is not
the user's `home_city`, the backend runs a two-phase commit across the two nodes. The response
then also has `distributed: {gtrid, wallet_node, pending_commit}` (null for same-city bookings).
Nice touch for the UI: show "Paid from your Bangalore wallet" when `distributed` is set.

## Charging sessions 🔒

| Method | Path | Body | Returns |
|--------|------|------|---------|
| POST | `/api/sessions/{city}/{booking_id}/start` | `{force?: bool}` | `{city, booking_id, booking_status: "active", charger_id, charger_code, session_start_time}` |
| POST | `/api/sessions/{city}/{booking_id}/end` | `{energy_kwh}` | `{city, booking_id, booking_status: "completed", energy_consumed_kwh, prepaid, final_cost, refund_amount, wallet_balance_after}` |

- Start = "scan QR at the charger". Allowed from 15 minutes before the slot until it ends.
  `force: true` skips the time check, only when `DEMO_MODE=true` (so you can demo a session today).
- End = "unplug". `energy_kwh` is what the charger delivered (in the demo, type it in or take it
  from Person 3's telemetry). Final bill = booking fee + rate × kWh, never more than prepaid.

## Payments 🔒

| Method | Path | Returns |
|--------|------|---------|
| GET | `/api/payments` | `[{city, payment_id, booking_id, amount, payment_method, payment_status, transaction_id, payment_timestamp, station_name, refunded, refund_pending}]` |

## Chargers

| Method | Path | Returns |
|--------|------|---------|
| GET | `/api/chargers/{city}/{charger_id}` | `{city, charger_id, charger_code, charger_type, connector_type, max_power_kw, status, station_id, station_name, active_session, live}` |

`live` is the MongoDB telemetry document from Person 3's `charger_status` collection, or `null`
if MongoDB is not running. For the station list, `GET /api/stations/{city}/{station_id}` already
returns every charger's `status`.

## Operator panel 🔒 (role `operator` or `admin`)

| Method | Path | Body | Returns |
|--------|------|------|---------|
| POST | `/api/operator/chargers/{city}/{charger_id}/status` | `{status: "faulted"\|"available"\|"maintenance"}` | `{old_status, status, alert, cross_city_refunds_paid}` |
| GET | `/api/operator/alerts?unread_only=true` | | `[alert]`, the operator's stations (admin: all) |
| POST | `/api/operator/alerts/{city}/{alert_id}/ack` | | `{acknowledged: true}` |

Setting `faulted` fires the database trigger: affected bookings are cancelled and refunded and
an alert is written. `alert.message` reads like
"Charger CHG-01 (8) faulted: 1 booking(s) cancelled, Rs 0.00 refunded, Rs 1086.30 queued for other nodes".
Refunds for drivers from other cities are then paid at once (`cross_city_refunds_paid`).
An operator can only change chargers of their own stations.

## Admin 🔒 (role `admin`)

| Method | Path | Returns |
|--------|------|---------|
| GET | `/api/admin/nodes` | `{mysql_nodes: {city: "up"\|"down"}, in_doubt: {city: {reachable, prepared: [{gtrid, bqual}]}}, last_recovery}` |
| POST | `/api/admin/recover` | runs recovery now: `{in_doubt: {committed, rolled_back, ...}, refunds: {settled, ...}}` |
| GET | `/api/admin/xa-log` | the 2PC coordinator's decision log |

For the admin panel's node-health view, `/api/admin/nodes` is the one to poll.

## Demo endpoints (only when `DEMO_MODE=true`)

| Method | Path | Notes |
|--------|------|-------|
| POST 🔒 | `/api/demo/book` | `{city, slot_id, vehicle_id, mode: "locked"\|"unsafe"\|"wrong_order", delay_ms, lock_gap_ms, fail_point: null\|"after_prepare"\|"after_decision"}` |
| POST | `/api/demo/fresh-slot?city=bangalore` | creates an empty slot to race on |
| GET | `/api/demo/slot-report/{city}/{slot_id}` | `confirmed_bookings > 1` = double booked |
| GET | `/api/demo/audit-log?after_seq=0` | live transaction log, poll with the last `seq` you saw |
| DELETE | `/api/demo/audit-log` | clear the log |

Audit event: `{seq, ts, event, txn, city, ...details}`. Events: `BEGIN`, `LOCK_REQUEST`,
`LOCK_ACQUIRED` (with `waited_ms`), `HOLDING_LOCKS`, `WALLET_DEBIT`, `BOOKING_WRITTEN`,
`COMMIT`, `ROLLBACK` (with `reason`), `RETRY`, `READ_NO_LOCK`, `RACE_WINDOW`, and for 2PC
`XA_BEGIN`, `XA_START`, `XA_PREPARED`, `XA_DECISION`, `XA_COMMIT`, `XA_ROLLBACK`,
`XA_COMMIT_PENDING`, `COORDINATOR_CRASH`, `XA_RECOVERED`, plus `SESSION_STARTED`, `SESSION_ENDED`,
`REFUND_SETTLED`, `CHARGER_STATUS`.
Colour suggestion for the live log: LOCK_* amber, COMMIT / XA_COMMIT green, ROLLBACK / XA_ROLLBACK red,
XA_PREPARED blue, COORDINATOR_CRASH purple.

## Health

`GET /health` → `{status: "healthy"|"degraded", mysql_nodes: {bangalore: "up"|"down", ...}}`
(for the admin panel's node health view).

## Demo logins (after running the seed script)

`driver.bangalore@demo.ev`, `driver.chennai@demo.ev`, `driver.delhi@demo.ev`,
`operator.<city>@demo.ev`, `admin@demo.ev`, all with password `demo1234`.
