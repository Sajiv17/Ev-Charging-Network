# Indexes: what changed and why, with EXPLAIN

Owner: Person 1 (Database). All indexes are InnoDB **B+ trees**. A secondary index stores its key
columns plus the primary key, so "covering" means the query can be answered from the index alone.

Method: the EXPLAIN output below was captured on the seeded **Bangalore node** (1,334 slots,
11 chargers, 56 bookings) for the backend's **real queries**, copied from `backend-api`.
Parameters were substituted with typical values, and `ANALYZE TABLE` was run first.
**Before** = the original `01_init_schema.sql` indexes; **after** = this branch.
The data is small, so row estimates are small, but the access paths are the ones that matter at scale.

Rule followed: drop an index only if it duplicates a UNIQUE key, is a left prefix of another index, or
is a low-cardinality boolean. Check every drop against the backend's SQL (`grep -rn "idx_\|INDEX" backend/`
finds no index hints or names). Add a composite index only where EXPLAIN shows a gain.

## Changes

| Table | Index | Change | Why |
|---|---|---|---|
| cities | `idx_city_name (city_name)` | dropped | duplicate of `UNIQUE(city_name)` |
| users | `idx_email (email)` | dropped | duplicate of `UNIQUE(email)` (login looks up by email through the unique index) |
| payments | `idx_transaction_id` | dropped | duplicate of `UNIQUE(transaction_id)` |
| charger_units | `idx_station_id (station_id)` | dropped | left prefix of `unique_charger (station_id, charger_code)`, which also serves the FK |
| stations | `idx_city_id (city_id)` | dropped | left prefix of `idx_station_city_status (city_id, is_operational)`, which also serves the FK |
| bookings | `idx_user_id (user_id)` | dropped | left prefix of `idx_booking_user_status (user_id, booking_status)`, which also serves the FK |
| slots | `idx_charger_date (charger_id, slot_date)` | dropped | left prefix of `unique_slot (charger_id, slot_date, slot_start_time)` |
| slots | `idx_availability (is_available)` | dropped | boolean (2 values): never selective, and rewritten on every booking |
| slots | `idx_slot_availability (charger_id, slot_date, is_available)` | dropped | same row estimate as `unique_slot` for the backend's queries (see Q1/Q2), but it is **rewritten on every booking and cancellation** because it contains `is_available` |
| pricing_plans | `idx_city_charger_type (city_id, charger_type)`, `idx_effective_dates` | replaced by **`uq_plan_period (city_id, charger_type, effective_from)` UNIQUE** | removes the filesort in `pricing.get_plan` (Q5) and enforces one plan per city/type/start date |
| corridor_stations | `idx_cs_km (corridor_id, km_marker)`, `idx_cs_station` | new table | corridor query reads stations already in km order (`docs/CORRIDOR_QUERY.md`) |

Kept on purpose: `idx_status` on `charger_units`, `bookings`, `payments`, `refunds` (enums used in
filters; `refunds.idx_status` finds the few `queued` refunds quickly), `idx_role`, `idx_home_city`,
`idx_coordinates`, `idx_session_times`, `idx_slot_id`, `idx_booking_id`, `idx_payment_id` (FKs and
lookups by booking/payment).

**Why fewer indexes on `slots` matters.** `slots` is the hottest table for writes: every booking runs
`UPDATE slots SET is_available = FALSE` under an X lock, and every cancel flips it back. Each secondary
index that contains `is_available` turns that one-row update into a delete and an insert in another
B+ tree, inside the critical section that other drivers are queued behind. After the change, `slots`
has one secondary index (`unique_slot`), which does not contain `is_available`. The flip only
touches the clustered row.

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
| c | ref | idx_connector_type | 42 | const | 6 | 100 | Using where; Using temporary; Using filesort |
| s | eq_ref | PRIMARY | 4 | c.station_id | 1 | 100 | Using where |
| sl | ref | unique_slot | 7 | c.charger_id, const | 10 | 100 | Using where |

Same plan shape and the same estimated rows per charger-day (about 16 slots exist, about 10 still
bookable). `unique_slot` serves `(charger_id, slot_date)` equally well. The temporary table and
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
| c | ref | unique_charger | 4 | const | 4 | 100 | Using where |
| sl | ref | unique_slot | 7 | c.charger_id, const | 10 | 10 | **Using index condition**; Using where |

`charger_units` was already reached through `unique_charger`, never through the dropped `idx_station_id`.
On `slots`, `unique_slot` contains `slot_start_time`, so `TIMESTAMP(slot_date, slot_start_time) > NOW()` is
now checked **inside the index** (index condition pushdown) before the row is read. The filesort
is for `ORDER BY sl.slot_start_time, c.charger_code`, which spans two tables, so it stays.

## Q3. `booking_service._SLOT_SQL … FOR UPDATE OF sl` (the 2PL lock)

**Before and after (identical)**

| table | type | key | key_len | ref | rows | Extra |
|---|---|---|---|---|---|---|
| sl | const | PRIMARY | 4 | const | 1 | |
| c | const | PRIMARY | 4 | const | 1 | |
| s | const | PRIMARY | 4 | const | 1 | |

Three primary-key lookups. The X lock is taken on exactly **one clustered-index record** of `slots`, with no
gap lock (unique equality lookup), which is what keeps lock contention to "same slot only".
Before the change, `possible_keys` also listed `idx_charger_date` and `idx_slot_availability`, which
the optimizer never used.

## Q4. `booking_service.list_user_bookings` (user 14, runs on every node)

**Before**

| table | type | possible_keys | key | rows | Extra |
|---|---|---|---|---|---|
| b | ref | idx_slot_id, idx_booking_user_status, **idx_user_id** | idx_booking_user_status | 8 | |
| p | ref | idx_booking_id | idx_booking_id | 1 | |
| sl | eq_ref | PRIMARY, … | PRIMARY | 1 | |
| c | eq_ref | PRIMARY, … | PRIMARY | 1 | |
| s | eq_ref | PRIMARY | PRIMARY | 1 | |

**After**

| table | type | possible_keys | key | rows | Extra |
|---|---|---|---|---|---|
| b | ref | idx_slot_id, idx_booking_user_status | idx_booking_user_status | 8 | |
| p | ref | idx_booking_id | idx_booking_id | 1 | |
| sl | eq_ref | PRIMARY, unique_slot | PRIMARY | 1 | |
| c | eq_ref | PRIMARY, unique_charger | PRIMARY | 1 | |
| s | eq_ref | PRIMARY | PRIMARY | 1 | |

Even when `idx_user_id` existed, the optimizer preferred the composite `idx_booking_user_status`.
The single-column index was pure write overhead.

## Q5. `pricing.get_plan` (Bangalore, DC, today)

**Before**

| table | type | key | key_len | ref | rows | filtered | Extra |
|---|---|---|---|---|---|---|---|
| pricing_plans | ref | idx_city_charger_type | 5 | const, const | 1 | 44.44 | Using where; **Using filesort** |

**After**

| table | type | key | key_len | ref | rows | filtered | Extra |
|---|---|---|---|---|---|---|---|
| pricing_plans | range | uq_plan_period | 8 | NULL | 1 | 44.44 | Using index condition; Using where; **Backward index scan** |

`WHERE city_id = ? AND charger_type = ? AND effective_from <= ? ORDER BY effective_from DESC LIMIT 1`
is answered by walking `uq_plan_period` backwards from the date and stopping at the first match.
The sort is gone. This query runs once per booking (inside the 2PL transaction) and once per
charger type per slot list.

---

## Reproduce

```bash
docker exec -it ev-mysql-bangalore mysql -uroot -pevcharge_root_2024 ev_bangalore
ANALYZE TABLE stations, charger_units, slots, bookings, payments, pricing_plans;
EXPLAIN <query from backend/app/services/...>;
```
