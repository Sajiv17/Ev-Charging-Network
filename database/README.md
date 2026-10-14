# Database (Person 1, Database Architect)

MySQL 8.0 schema, triggers, stored procedures and seed data for the three city nodes
(Bangalore, Chennai, Delhi). MongoDB (`mongodb/`) belongs to Person 3.

Design write-ups: [ER diagram](../docs/ER_DIAGRAM.md) · [Normalization](../docs/NORMALIZATION.md) ·
[Indexes + EXPLAIN](../docs/INDEXES.md) · [Corridor query](../docs/CORRIDOR_QUERY.md)

## Folder layout

```
database/mysql/
├── init.sh                    entrypoint hook: applies everything below, in order
├── schema/
│   ├── 01_catalog.sql         cities, connector_types, pricing_plans, corridors      (replicated)
│   └── 02_core.sql            users, vehicles (replicated); stations, charger_units, slots,
│                              bookings, payments, refunds, corridor_stations (fragmented)
├── triggers/
│   ├── charger_fault_trigger.sql     fault -> cancel + refund; repair -> re-open slots
│   ├── charger_type_consistency.sql  charger_type must match the connector (AC/DC)
│   ├── slot_availability.sql         bookings keep slots.is_available in step
│   ├── slot_overlap.sql              no overlapping slots on a charger
│   └── wallet_guard.sql              readable error for a negative wallet
├── procedures/
│   ├── sp_create_booking.sql   2PL booking in SQL (viva demo + tests; the backend does not call it)
│   ├── sp_generate_slots.sql   1-hour slots 06:00-22:00 for today..today+N, plus a daily EVENT
│   ├── sp_get_station_load.sql hourly bookings / utilisation for a station and date
│   └── sp_process_refund.sql   complete a queued refund locally, or hand it to the coordinator
├── seeds/
│   ├── common/                 loaded on ALL nodes: cities, connector types, pricing, corridors,
│   │                           30 users + vehicles (identical IDs everywhere)
│   ├── bangalore/ chennai/ delhi/   loaded only on that node: stations, chargers, slots, bookings
└── optional/
    └── double_booking_guard.sql   NOT auto-loaded (see below)
```

`seeds/` is **generated**. Edit `scripts/db/seed_data.py` or `generate_seeds.py`, then run
`python scripts/db/generate_seeds.py`. Do not edit the SQL by hand.

## How a node is initialised

`docker-compose.yml` mounts `./database/mysql` read-only at `/ev-sql` and `init.sh` as
`/docker-entrypoint-initdb.d/00_init.sh`, and sets `EV_CITY` per node. The official MySQL entrypoint
runs `init.sh` once; it does not recurse into folders itself. `init.sh` applies, each folder sorted by file name:

```
schema/  ->  triggers/  ->  procedures/  ->  seeds/common/  ->  seeds/$EV_CITY/
```

Each file runs in a session with `time_zone = '+05:30'`, the same as the nodes (`--default-time-zone=+05:30`)
and the backend's connections. So `NOW()`/`CURDATE()` in seeds, triggers and the slot event are IST
everywhere. Any SQL error stops the container (`docker logs ev-mysql-<city>` shows which file).

**Init only runs on an empty data volume.** After changing anything in `database/mysql/`, reset:

```bash
docker compose down -v          # deletes ALL volumes of this project (MySQL and MongoDB data)
docker compose up -d
```

To reset only the MySQL nodes, use `scripts/db/run_db_tests.sh --fresh` (it recreates the three
MySQL containers and their volumes, then runs the tests).

## Data placement

| | Tables | On each node |
|---|---|---|
| Replicated | cities, connector_types, pricing_plans, corridors, users, vehicles | all rows, identical IDs |
| Fragmented | stations, charger_units, slots, bookings, payments, refunds, corridor_stations | that city's rows only; IDs repeat across nodes, so the API uses `(city, id)` |

**Wallets.** `users.wallet_balance` is replicated with the user, but only the copy on the user's
home node (`users.home_city_id`) is authoritative. The seed writes the same value on every node.
The other copies are never read for money and drift once the user tops up or books.

## Seed data

- **Logins** (password `demo1234` for every account): `admin@demo.ev`, `operator.<city>@demo.ev`,
  `driver.<city>@demo.ev` (₹5000, with the backend's demo vehicles), and 23 fictitious drivers
  `<first>.<last>@example.com`. These are the same IDs as the backend's `scripts/seed_demo_data.py`
  (1-7), so that script is now a no-op.
- **Stations:** the backend's three demo stations per city (Koramangala, Whitefield, Bidadi NH-275;
  T Nagar, OMR, ECR; Connaught Place, Saket, Gurugram NH-48) with the same IDs and chargers.
  Real stations from Open Charge Map are added when `scripts/db/fetch_stations.py` is run with a key.
  The current seeds were generated **without** OCM data.
- **Slots:** `sp_generate_slots(7)` at init (today..today+7), then the event `ev_daily_slot_generation`
  tops up daily at 00:05 IST.
- **History:** 14 days of completed and cancelled bookings per city, with consistent payments and
  refunds. Plus two confirmed bookings tomorrow 10:00/11:00 on **charger 5** of each node, so the
  README's fault demo has something to refund.

### Real stations from Open Charge Map

```bash
pip install -r scripts/db/requirements.txt
export OCM_API_KEY=...            # free key: openchargemap.org -> My Profile -> My Apps
python scripts/db/fetch_stations.py
```

This saves the raw API responses to `scripts/db/raw/` and regenerates the seeds (about 20 real stations per
city plus stations along the NH-275 and NH-48 corridors). Generation is deterministic: commit `raw/`,
and anyone can regenerate identical SQL without a key.

**Attribution.** Station data © Open Charge Map contributors, licensed under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) (<https://openchargemap.org>). Keep this
notice wherever the data is used. OCM stations are tagged with their POI id in
`seeds/<city>/01_stations.sql`.

## Triggers and procedures at a glance

| Object | Fires / called | Effect |
|---|---|---|
| `after_charger_fault` | `UPDATE charger_units SET status='faulted'` | Cancels the charger's active bookings and its confirmed bookings whose slot has not ended. Refunds active ones in proportion to unused time and confirmed ones in full. Payment → refunded. Refund `completed` + wallet credited if the user's home node is this node, else `queued`. Earlier cancellations are untouched. |
| | `faulted → available` | Re-opens future slots with no live booking |
| `trg_charger_type_before_insert/update` | charger insert/update | Rejects e.g. `charger_type='AC'` with `connector_type='CCS2'` |
| `trg_slots_no_overlap_insert/update` | slot insert/update | Rejects overlapping intervals on the same charger and date (back-to-back is fine) |
| `trg_bookings_slot_after_insert/update` | booking insert/status change | Keeps `slots.is_available` consistent |
| `trg_users_wallet_guard` | wallet update | Friendly message; `CHECK (wallet_balance >= 0)` is the real guard |
| `CALL sp_create_booking(user, slot, vehicle, @booking_id, @amount)` | manual | Same 2PL transaction as the backend (lock slot, then wallet); rolls back on any error |
| `CALL sp_process_refund(refund_id)` | coordinator / manual | Local wallet → credit + `completed`; remote → returns `(user_id, home_city_id, amount)` |
| `CALL sp_get_station_load(station_id, date)` | dashboard | Per hour: slots, booked slots, bookings, utilisation % |
| `CALL sp_generate_slots(days)` | seed + daily event | Idempotent slot generation |

Try the fault trigger:

```bash
docker exec -it ev-mysql-bangalore mysql -uroot -pevcharge_root_2024 ev_bangalore
UPDATE charger_units SET status = 'faulted' WHERE charger_id = 5;
SELECT * FROM refunds ORDER BY refund_id DESC LIMIT 5;
UPDATE charger_units SET status = 'available' WHERE charger_id = 5;
```

## Tests

```bash
scripts/db/run_db_tests.sh --fresh    # recreate the 3 MySQL nodes, then run all checks
scripts/db/run_db_tests.sh            # run against the running nodes (expects fresh seed data)
```

It prints PASS/FAIL per check (46 checks): time zone, identical schema, fragmentation, identical
replicated IDs, `is_available` invariant, every constraint and trigger, the delete rules, all
procedures, the fault trigger scenarios, schema re-runs, and the optional guard. It exits non-zero on
any failure. Works from Linux, macOS and Git Bash on Windows.

## `optional/`: database-level double-booking guard

`optional/double_booking_guard.sql` adds a stored generated column (`slot_id` while the booking is
live, else NULL) with a UNIQUE index, so a slot can have at most one confirmed/active booking.
It is **not loaded by default**: the backend's unsafe-mode concurrency demo must be able to show a
real double booking, and this guard would turn it into a duplicate-key error. In production it is the
defence-in-depth option on top of 2PL. The test script applies it to a scratch database to prove it works.
