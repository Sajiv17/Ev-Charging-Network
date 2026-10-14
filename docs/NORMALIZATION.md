# Normalization: from a booking sheet to BCNF

Owner: Person 1 (Database). Schema: `database/mysql/schema/01_catalog.sql`, `02_core.sql`.

This walks from the spreadsheet a charging operator would naturally keep, through 1NF, 2NF,
3NF and BCNF, to the schema we deploy. It then explains the **three places where we
deliberately keep redundancy** and what protects each one.

---

## 0. Unnormalized: the booking sheet

One row per booking, the way an operator might log it:

| booking | user | vehicle(s) | station | charger | slot | price | payment(s) | refund(s) |
|---|---|---|---|---|---|---|---|---|
| 41 | ananya@x.com, Ananya Sharma, home Bangalore, wallet 2200 | KA01AB1234 Tata Nexon EV 40.5 kWh CCS2; KA03CD9 MG Comet 17.3 kWh Type2 | Koramangala EV Hub, 80 Feet Rd, Bangalore, Karnataka, op: operator.bangalore | CHG-01, DC, CCS2, 60 kW | 2026-10-15 10:00-11:00 | 21/kWh + 30 fee = 880.50 | WLT-9F.. wallet 880.50 completed | 880.50 "Charger fault" queued |

Problems:

- **Non-atomic values:** "vehicle(s)" holds a list, and "user" packs four facts into one cell.
- **Repeating groups:** one booking can have several payments and several refunds.
- **Update anomaly:** Ananya's wallet appears in every row she ever booked. Updating one row leaves the others stale.
- **Insert anomaly:** a new charger cannot be recorded until somebody books it.
- **Delete anomaly:** deleting the only booking on a charger deletes everything we knew about the charger.

## 1. Attributes and functional dependencies

After splitting the packed cells into single attributes:

```
BookingSheet(booking_id, booking_status, booking_amount, energy_kwh, session_start, session_end,
             email, full_name, phone, role, home_city, wallet_balance,
             registration_no, make, model, battery_kwh, vehicle_connector,
             station_name, address, latitude, longitude, city_name, state, operator_email,
             charger_code, charger_type, connector_type, max_power_kw, charger_status,
             slot_date, slot_start, slot_end, is_available,
             rate_per_kwh, booking_fee, plan_from, plan_to,
             txn_id, pay_method, pay_amount, pay_status, pay_time,
             refund_no, refund_amount, refund_reason, refund_status)
```

Functional dependencies (with the surrogate IDs the schema uses as shorthand for the natural keys):

| # | FD | Meaning |
|---|---|---|
| F1 | `email → full_name, phone, role, home_city, wallet_balance` | a user (`user_id` ↔ `email`) |
| F2 | `registration_no → make, model, battery_kwh, vehicle_connector, email` | a vehicle belongs to one user |
| F3 | `city_name → state` | |
| F4 | `station → station_name, address, latitude, longitude, city_name, operator_email` | `station_id` |
| F5 | `(station, charger_code) → charger_type, connector_type, max_power_kw, charger_status` | a charger (`charger_id`) |
| **F6** | **`connector_type → current_type`** | **CCS2 and CHAdeMO are DC, Type2 is AC: a property of the plug standard** |
| F7 | `(charger, slot_date, slot_start) → slot_end, is_available` | a slot (`slot_id`) |
| F8 | `booking_id → status, amount, energy, session times, email, registration_no, slot` | |
| F9 | `(city, current_type, plan_from) → rate_per_kwh, booking_fee, plan_to` | a pricing plan (`plan_id`) |
| F10 | `txn_id → booking_id, pay_method, pay_amount, pay_status, pay_time` | a payment (`payment_id`) |
| F11 | `refund_no → txn_id, refund_amount, refund_reason, refund_status` | a refund (`refund_id`) |

Not FDs, on purpose:

- `booking_amount` is **not** determined by the pricing plan. Plans change, and the amount is the
  prepaid estimate **frozen at booking time** (`pricing.prepaid_amount`). It is a historical fact,
  like the price on an invoice line.
- `is_available` is a **derived** attribute: a slot is available iff it has no live booking. See §6.2.

## 2. First normal form (1NF)

Rule: every attribute is atomic, and there are no repeating groups.

- The packed "user" and "vehicle(s)" cells become single-valued attributes (§1).
- The repeating groups **payments** and **refunds** are flattened. Each row is now one
  (booking, payment, refund) combination, so the key becomes **`(booking_id, txn_id, refund_no)`**.

The relation is in 1NF but heavily redundant. Every booking attribute is repeated once per payment and once per refund.

## 3. Second normal form (2NF)

Rule: no non-key attribute depends on only **part** of a composite key.

With key `(booking_id, txn_id, refund_no)`:

- `booking_id → …` (F8, and everything reachable from it) depends on part of the key.
- `txn_id → pay_*` (F10) depends on part of the key.

Decompose by those partial dependencies:

```
Booking(booking_id, status, amount, energy, session times, email, user fields…, registration_no,
        vehicle fields…, station fields…, charger fields…, slot fields…, plan fields…)
Payment(txn_id, booking_id, pay_method, pay_amount, pay_status, pay_time)
Refund(refund_no, txn_id, refund_amount, refund_reason, refund_status)
```

Each relation now has a single-attribute key, so 2NF holds trivially.

## 4. Third normal form (3NF)

Rule: no non-key attribute depends transitively on the key through another non-key attribute.

`Booking` is full of transitive dependencies:

| Chain | Pull out |
|---|---|
| `booking_id → email → full_name, home_city, wallet_balance…` | **users** |
| `booking_id → registration_no → make, model, battery_kwh…` | **vehicles** |
| `booking_id → slot → slot_end, is_available, charger` | **slots** |
| `slot → charger → charger_type, connector_type, max_power_kw…` | **charger_units** |
| `charger → station → address, city…` | **stations** |
| `station → city_name → state` | **cities** |
| `(city, current_type, date) → rate_per_kwh, booking_fee` | **pricing_plans** |

What remains in `bookings` is `(booking_id, user_id, slot_id, vehicle_id, status, amount, energy,
session times)`. Every non-key attribute now depends on the key, the whole key, and nothing
but the key.

**One transitive dependency is easy to miss**, inside `charger_units`:

```
charger_id → connector_type → current_type   (F6)
```

`current_type` (stored as `charger_type`) depends on `connector_type`, which is not a key. That
violates 3NF, and therefore BCNF. §5 fixes it formally, and §6.3 explains why the column is still
there.

## 5. Boyce-Codd normal form (BCNF)

Rule: for every non-trivial FD `X → Y`, X is a superkey.

Check every relation's determinants:

| Relation | Candidate keys | Other determinants | BCNF? |
|---|---|---|---|
| cities | `city_id`, `city_name` | none | ✓ |
| users | `user_id`, `email` | none | ✓ |
| vehicles | `vehicle_id` (`registration_number` is UNIQUE but nullable) | none | ✓ |
| stations | `station_id` | none | ✓ |
| charger_units | `charger_id`, `(station_id, charger_code)` | **`connector_type → charger_type`** | ✗ |
| slots | `slot_id`, `(charger_id, slot_date, slot_start_time)` | none | ✓ |
| bookings | `booking_id` | (see §7 for `user_id`) | ✓ |
| payments | `payment_id`, `transaction_id` | none | ✓ |
| refunds | `refund_id` | none | ✓ |
| pricing_plans | `plan_id`, `(city_id, charger_type, effective_from)` (UNIQUE `uq_plan_period`) | none | ✓ |
| corridors / corridor_stations | `corridor_id` / `(corridor_id, station_id)` | none | ✓ |

**BCNF decomposition of `charger_units`** on the violating FD `connector_type → current_type`:

```
ChargerUnits(charger_id, station_id, charger_code, max_power_kw, connector_type, status)
ConnectorTypes(connector_type PK, current_type, description)
```

This decomposition is lossless (`connector_type` is the key of `ConnectorTypes`) and preserves dependencies.
We implemented it: **`connector_types`** is a replicated catalog table, and both
`charger_units.connector_type` and `vehicles.connector_type` are foreign keys to it. Adding a
new plug standard is now one `INSERT`, not an `ALTER` of two ENUMs on three nodes.

## 6. Deliberate deviations, and what protects each one

Normalization removes redundancy that can go **out of sync by accident**. The three cases below
keep redundancy **on purpose**, and each one has a mechanism that stops it from going out of sync.

### 6.1 Replicated `users.wallet_balance`

**The redundancy.** `users` (and `vehicles`) are replicated to all three nodes with identical
IDs. Bookings on any node need foreign keys to them, and Bangalore issues the IDs
(`replication.write_everywhere`). So every user has three copies of `wallet_balance`.

**Why not a separate `wallets` table?** It would not remove the problem: the wallet still has to live
somewhere, and the choice that matters is **which node owns it**. A fourth table on one node would
add a join without adding safety.

**What protects it:**

1. **Home-node authority.** `users.home_city_id` names the node whose copy is real. The backend
   reads balances only from the home node (`user_service.get_wallet_balance`), tops up only there,
   and books only when station node = home node (`_require_same_city`; cross-city bookings need 2PC,
   which is phase 2). The other two copies are never read for money. They keep the seed value and
   are stale by design.
2. **The fault trigger follows the same rule.** It credits the wallet only when the user's home node is
   the station's node. Otherwise it writes a `queued` refund for the coordinator (`sp_process_refund`).
3. **`CHECK (wallet_balance >= 0)`** on every copy. Even buggy code cannot overdraw a wallet.
   `trg_users_wallet_guard` only turns the violation into a readable message.
4. Within the home node, every debit and credit happens under the row's X lock (2PL) or is an atomic
   `wallet_balance = wallet_balance ± x`, so there are no lost updates (`docs/CONCURRENCY.md`).

### 6.2 `slots.is_available`: controlled redundancy

**The redundancy.** `is_available` is derivable: a slot is free iff no `confirmed` or `active`
booking references it. Storing it is a classic derived attribute.

**Why keep it?**

- **It is the lock target.** The 2PL booking transaction does `SELECT … FROM slots … FOR UPDATE`.
  The slot row exists before anyone books it, so two drivers racing for it contend on the same row.
  Locking "the absence of a booking" instead would need gap/next-key locks on `bookings` and
  phantom protection, which is harder to reason about and to demonstrate.
- **It is the cheapest search filter.** Station search and slot lists filter on it without an
  anti-join against `bookings`.

**What keeps it consistent:**

| Writer | How |
|---|---|
| Backend booking (2PL) | sets it FALSE while holding the slot's X lock, in the same transaction as the booking |
| Backend cancel | sets it TRUE in the cancel transaction |
| `trg_bookings_slot_after_insert` | a new live booking closes the slot (CLI, procedures, seeds) |
| `trg_bookings_slot_after_update` | cancellation re-opens a future slot, unless another live booking remains (possible only after the unsafe demo) or the charger is out of service |
| `after_charger_fault` | slots of fault-cancelled bookings stay closed. Repair (`faulted → available`) re-opens future slots with no live booking |

Invariant checked by `scripts/db/run_db_tests.sh`: **no slot is available while it has a live
booking.** The converse does not hold on purpose. A past slot, or one held closed by a faulted
charger, can be unavailable without a booking, so `is_available` really means "bookable".

**Not a view, and no UNIQUE live-booking constraint by default.** A view could not be locked.
A UNIQUE "one live booking per slot" index would turn the backend's unsafe-mode demo
(which must show a real double booking) into a duplicate-key error. That guard ships as
`database/mysql/optional/double_booking_guard.sql`, the defence-in-depth option for production.

### 6.3 `charger_units.charger_type`: denormalized for query simplicity

**The redundancy.** After the BCNF decomposition in §5, `charger_type` duplicates
`connector_types.current_type` via `connector_type`.

**Why keep it?** It is used constantly, and always next to the charger row:

- `station_service.search_stations` filters `c.charger_type = :ctype` (AC/DC filter in the UI),
- `pricing.get_plan` looks up the plan by `charger_type`, and `pricing_plans.charger_type` joins on it,
- `_SLOT_SQL` (the 2PL lock query) and `list_slots` return it.

Dropping it would add a join to `connector_types` in each of those queries, including inside the
locking transaction, and would change the backend's SQL for no gain in correctness.

**What protects it:** `trg_charger_type_before_insert` / `_before_update` reject any row whose
`charger_type` disagrees with `connector_types.current_type` (`SIGNAL SQLSTATE '45000'`), so the copy
can never be wrong. Status-only updates (fault/repair) skip the lookup.

## 7. Things that look redundant but are not

| Column | Why it is a fact, not a copy |
|---|---|
| `bookings.user_id` | Today the backend only books a user's own vehicle, so `vehicle_id → user_id` would make this transitive. But it records **who paid**, which may differ from the owner (fleet or family cars), and it keeps "my bookings" (`idx_booking_user_status`) a single-table lookup. |
| `bookings.booking_amount` | Snapshot of the prepaid price at booking time; plans change later (§1). |
| `payments.amount` | Equals `booking_amount` today. Phase-2 kWh settlement will make them differ (final bill and partial refunds). |
| `stations.city_id` on a fragmented node | Constant per node, but it keeps rows self-describing when results from several nodes are merged, and it is what the fragmentation predicate (`city_id = node`) is written in. |

## 8. Final schema

```
cities(city_id PK, city_name UQ, state, country)                                    replicated
connector_types(connector_type PK, current_type, description)                       replicated
pricing_plans(plan_id PK, city_id FK, charger_type, rate_per_kwh, booking_fee,
              effective_from, effective_to; UQ(city_id, charger_type, effective_from)) replicated
corridors(corridor_id PK, corridor_name UQ, highway, origin_city_id FK, destination, length_km)  replicated
users(user_id PK, email UQ, password_hash, full_name, phone, role, wallet_balance*,
      home_city_id FK, is_active)                                                   replicated
vehicles(vehicle_id PK, user_id FK, make, model, battery_capacity_kwh,
         connector_type FK, registration_number UQ)                                 replicated
stations(station_id PK, station_name, city_id FK, address, latitude, longitude,
         operator_id FK, is_operational)                                            fragmented
charger_units(charger_id PK, station_id FK, charger_code, charger_type*, max_power_kw,
              connector_type FK, status; UQ(station_id, charger_code))              fragmented
slots(slot_id PK, charger_id FK, slot_date, slot_start_time, slot_end_time,
      is_available*; UQ(charger_id, slot_date, slot_start_time))                    fragmented
bookings(booking_id PK, user_id FK, slot_id FK, vehicle_id FK, booking_status,
         booking_amount, energy_consumed_kwh, session_start_time, session_end_time) fragmented
payments(payment_id PK, booking_id FK, amount, payment_method, payment_status,
         transaction_id UQ, payment_timestamp)                                      fragmented
refunds(refund_id PK, payment_id FK, refund_amount, refund_reason, refund_status,
        created_at, processed_at)                                                   fragmented
corridor_stations(corridor_id FK, station_id FK, km_marker; PK(corridor_id, station_id))  fragmented
```

`*` = deliberate redundancy, protected as described in §6. Everything else is in BCNF.
