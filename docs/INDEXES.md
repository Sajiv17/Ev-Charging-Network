# Indexes: what changed and why, with EXPLAIN

Owner: Person 1 (Database). All indexes are InnoDB **B+ trees**. A secondary index stores its key
columns plus the primary key, so "covering" means the query can be answered from the index alone.

Method: the EXPLAIN output below was captured on the seeded **Bangalore node** (about 1,330 slots,
11 chargers, about 60 bookings) for the backend's **real queries**, copied from `backend-api`.
Parameters were substituted with typical values, and `ANALYZE TABLE` was run first.
**Before** = the original `01_init_schema.sql` indexes (old names); **after** = this branch.
The data is small, so row estimates are small, but the access paths are the ones that matter at scale.

Rule followed: drop an index only if it duplicates a UNIQUE key, is a left prefix of another index, or
is a low-cardinality boolean. Check every drop against the backend's SQL (`grep -rn "idx_\|INDEX" backend/`
finds no index hints or names). Add a composite index only where EXPLAIN shows a gain.

## Naming

Every index follows CONTRIBUTING.md: **`idx_<table>_<column(s)>`**, and **`uq_<table>_<column(s)>`**
for UNIQUE keys (formerly inline `UNIQUE` columns, which MySQL named after the column, e.g. `email`).
The old names repeated across tables (`idx_status` existed on four tables) and hid the table in
`EXPLAIN` and in deadlock reports. The backend never refers to an index name, so renaming is safe.

## Changes

| Table | Original index | Now | Why |
|---|---|---|---|
| cities | `idx_city_name (city_name)` | dropped; `uq_cities_city_name` | duplicate of the UNIQUE key |
| users | `idx_email (email)` | dropped; `uq_users_email` | duplicate of the UNIQUE key (login looks up by email through it) |
| payments | `idx_transaction_id` | dropped; `uq_payments_transaction_id` | duplicate of the UNIQUE key |
| charger_units | `idx_station_id (station_id)` | dropped | left prefix of `uq_charger_units_station_id_charger_code`, which also serves the FK |
| stations | `idx_city_id (city_id)` | dropped | left prefix of `idx_stations_city_id_is_operational`, which also serves the FK |
| bookings | `idx_user_id (user_id)` | dropped | left prefix of `idx_bookings_user_id_booking_status`, which also serves the FK |
| slots | `idx_charger_date (charger_id, slot_date)` | dropped | left prefix of `uq_slots_charger_id_slot_date_slot_start_time` |
| slots | `idx_availability (is_available)` | dropped | boolean (2 values): never selective, and rewritten on every booking |
| slots | `idx_slot_availability (charger_id, slot_date, is_available)` | dropped | same row estimate as the unique slot key for the backend's queries (see Q1/Q2), but it is **rewritten on every booking and cancellation** because it contains `is_available` |
| pricing_plans | `idx_city_charger_type (city_id, charger_type)`, `idx_effective_dates` | replaced by **`uq_pricing_plans_city_id_charger_type_effective_from`** (UNIQUE) | removes the filesort in `pricing.get_plan` (Q5) and enforces one plan per city/type/start date |
| corridor_stations | (new table) | `idx_corridor_stations_corridor_id_km_marker`, `idx_corridor_stations_station_id` | corridor query reads stations already in km order (`docs/CORRIDOR_QUERY.md`) |
| operator_alerts | (new table) | `idx_operator_alerts_operator_id_acknowledged_at`, `idx_operator_alerts_charger_id` | operator panel: unread alerts per operator; FK |

Kept (renamed only): the status enums `idx_charger_units_status`, `idx_bookings_booking_status`,
`idx_payments_payment_status`, `idx_refunds_refund_status` (used in filters;
`idx_refunds_refund_status` finds the few `queued` refunds quickly), `idx_users_role`,
`idx_users_home_city_id`, `idx_stations_latitude_longitude`, `idx_stations_operator_id`,
`idx_bookings_session_start_time_session_end_time`, `idx_bookings_slot_id`, `idx_payments_booking_id`,
`idx_refunds_payment_id`, `idx_vehicles_user_id`, `idx_charger_units_connector_type`
(FKs and lookups).

**Why fewer indexes on `slots` matters.** `slots` is the hottest table for writes: every booking runs
`UPDATE slots SET is_available = FALSE` under an X lock, and every cancel flips it back. Each secondary
index that contains `is_available` turns that one-row update into a delete and an insert in another
B+ tree, inside the critical section that other drivers are queued behind. After the change, `slots`
has one secondary index (`uq_slots_charger_id_slot_date_slot_start_time`), which does not contain
`is_available`. The flip only touches the clustered row.

---

## Q1. `station_service.search_stations` (city = Bangalore, connector CCS2, tomorrow)

**Before**

| table | type | key | key_len | ref | rows | filtered | Extra |
|---|---|---|---|---|---|---|---|
| c | ref | idx_connector_type | 42 | const | 6 | 100 | Using where; Using temporary; Using filesort |
| s | eq_ref | PRIMARY | 4 | c.station_id | 1 | 100 | Using where |
| sl | ref | idx_slot_availability | 9 | c.charger_id, const, const | 10 | 100 | Using where |

**After**

| table | type | key | key_len | ref | rows | filtered | Extra |
|---|---|---|---|---|---|---|---|
| c | ref | idx_charger_units_connector_type | 42 | const | 6 | 100 | Using where; Using temporary; Using filesort |
| s | eq_ref | PRIMARY | 4 | c.station_id | 1 | 100 | Using where |
| sl | ref | uq_slots_charger_id_slot_date_slot_start_time | 7 | c.charger_id, const | 10 | 100 | Using where |

Same plan shape and the same estimated rows per charger-day (about 16 slots exist, about 10 still
bookable). The unique slot key serves `(charger_id, slot_date)` equally well. The temporary table and
filesort come from `GROUP BY … ORDER BY available_slots DESC`, an aggregate, so no index can remove them.

## Q2. `station_service.list_slots` (station 1, tomorrow, only available)

**Before**

| table | type | key | key_len | ref | rows | filtered | Extra |
|---|---|---|---|---|---|---|---|
| s | const | PRIMARY | 4 | const | 1 | 100 | Using temporary; Using filesort |
| c | ref | unique_charger | 4 | const | 4 | 100 | Using where |
| sl | ref | idx_slot_availability | 9 | c.charger_id, const, const | 10 | 100 | Using where |

**After**

| table | type | key | key_len | ref | rows | filtered | Extra |
|---|---|---|---|---|---|---|---|
| s | const | PRIMARY | 4 | const | 1 | 100 | Using temporary; Using filesort |
| c | ref | uq_charger_units_station_id_charger_code | 4 | const | 4 | 100 | Using where |
| sl | ref | uq_slots_charger_id_slot_date_slot_start_time | 7 | c.charger_id, const | 10 | 10 | **Using index condition**; Using where |

`charger_units` was already reached through its unique `(station_id, charger_code)` key, never through
the dropped `idx_station_id`. On `slots`, the unique key contains `slot_start_time`, so
`TIMESTAMP(slot_date, slot_start_time) > NOW()` is now checked **inside the index** (index condition
pushdown) before the row is read. The filesort is for `ORDER BY sl.slot_start_time, c.charger_code`,
which spans two tables, so it stays.

## Q3. `booking_service._SLOT_SQL … FOR UPDATE OF sl` (the 2PL lock)

**Before and after (identical plan)**

| table | type | key | key_len | ref | rows | Extra |
|---|---|---|---|---|---|---|
| sl | const | PRIMARY | 4 | const | 1 | |
| c | const | PRIMARY | 4 | const | 1 | |
| s | const | PRIMARY | 4 | const | 1 | |

Three primary-key lookups. The X lock is taken on exactly **one clustered-index record** of `slots`, with no
gap lock (unique equality lookup), which is what keeps lock contention to "same slot only".
`docs/DB_RECOVERY_AND_DEADLOCK.md` shows the same `lock_mode X locks rec but not gap` in InnoDB's report.
Before the change, `possible_keys` also listed `idx_charger_date` and `idx_slot_availability`, which
the optimizer never used.

## Q4. `booking_service.list_user_bookings` (user 14, runs on every node)

**Before**

| table | type | possible_keys | key | rows |
|---|---|---|---|---|
| b | ref | idx_slot_id, idx_booking_user_status, **idx_user_id** | idx_booking_user_status | 8 |
| p | ref | idx_booking_id | idx_booking_id | 1 |
| sl | eq_ref | PRIMARY, … | PRIMARY | 1 |
| c | eq_ref | PRIMARY, … | PRIMARY | 1 |
| s | eq_ref | PRIMARY | PRIMARY | 1 |

**After**

| table | type | possible_keys | key | rows |
|---|---|---|---|---|
| b | ref | idx_bookings_slot_id, idx_bookings_user_id_booking_status | idx_bookings_user_id_booking_status | 8 |
| p | ref | idx_payments_booking_id | idx_payments_booking_id | 1 |
| sl | eq_ref | PRIMARY, uq_slots_charger_id_slot_date_slot_start_time | PRIMARY | 1 |
| c | eq_ref | PRIMARY, uq_charger_units_station_id_charger_code | PRIMARY | 1 |
| s | eq_ref | PRIMARY | PRIMARY | 1 |

Even when `idx_user_id` existed, the optimizer preferred the composite `(user_id, booking_status)`
index. The single-column index was pure write overhead.

## Q5. `pricing.get_plan` (Bangalore, DC, today)

**Before**

| table | type | key | key_len | ref | rows | filtered | Extra |
|---|---|---|---|---|---|---|---|
| pricing_plans | ref | idx_city_charger_type | 5 | const, const | 1 | 44.44 | Using where; **Using filesort** |

**After**

| table | type | key | key_len | ref | rows | filtered | Extra |
|---|---|---|---|---|---|---|---|
| pricing_plans | range | uq_pricing_plans_city_id_charger_type_effective_from | 8 | NULL | 1 | 44.44 | Using index condition; Using where; **Backward index scan** |

`WHERE city_id = ? AND charger_type = ? AND effective_from <= ? ORDER BY effective_from DESC LIMIT 1`
is answered by walking the unique `(city_id, charger_type, effective_from)` key backwards from the date
and stopping at the first match. The sort is gone. This query runs once per booking (inside the 2PL
transaction) and once per charger type per slot list.

---

## Reproduce

```bash
docker exec -it ev-mysql-bangalore mysql -uroot -pevcharge_root_2024 ev_bangalore
ANALYZE TABLE stations, charger_units, slots, bookings, payments, pricing_plans;
EXPLAIN <query from backend/app/services/...>;
```
