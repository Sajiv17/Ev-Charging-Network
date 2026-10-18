# Backend: Person 2 (Backend + Transactions)

FastAPI service that sits between the React frontend and the 3 MySQL city nodes + MongoDB.
API reference for the frontend: [`docs/API.md`](../docs/API.md).
Concurrency write-up: [`docs/CONCURRENCY.md`](../docs/CONCURRENCY.md).
2PC and recovery write-up: [`docs/RECOVERY_DEMO.md`](../docs/RECOVERY_DEMO.md).

## Status

| Part | Status |
|------|--------|
| Users, login (JWT), wallet top-up, vehicles | Done |
| Station search, station detail, slots with price estimate | Done |
| Booking transaction with strict 2PL + deadlock retry | Done |
| Cancel booking + refund | Done |
| Concurrency demo (double booking + lost update) | Done |
| Live transaction audit log | Done (in-memory + MongoDB `audit_log`) |
| Cross-city booking and cancel with XA two-phase commit | Done |
| Recovery of in-doubt 2PC transactions (startup, every 30 s, on demand) + demo | Done |
| Charging sessions: start, end with kWh billing and refund of unused prepayment | Done |
| Charger fault → cross-city refunds paid to the home-node wallet (2PC) | Done |
| Deadlock demo (wrong vs right lock order) | Done |
| Payments history, charger status (+ MongoDB live data if available) | Done |
| Operator panel API (report fault/repair, alerts), admin API (node health, recovery) | Done |

## Folder layout

```
backend/
├── app/
│   ├── main.py              app, routers, error handling, /health
│   ├── core/
│   │   ├── config.py        settings from environment variables
│   │   ├── cities.py        city <-> node registry
│   │   └── security.py      password hashing, JWT
│   ├── db/                  one SQLAlchemy engine per city node, MongoDB client
│   ├── models/              SQLAlchemy models (one per table)
│   ├── schemas/             Pydantic request/response shapes
│   ├── api/                 HTTP routes (thin: validate, call a service)
│   └── services/            all business logic and SQL
│       ├── booking_service.py   <- the 2PL booking transaction (same city)
│       ├── xa.py                <- 2PC coordinator (MySQL XA) + recovery
│       ├── cross_city.py        <- cross-city booking / cancel over 2PC
│       ├── recovery_service.py  background recovery + queued refund payouts
│       ├── session_service.py   charging sessions and final billing
│       ├── ops_service.py       payments, chargers, operator alerts
│       ├── live_status.py       optional MongoDB reads/writes (2 s timeout)
│       ├── user_service.py
│       ├── station_service.py
│       ├── pricing.py
│       ├── replication.py   writes to replicated tables on all nodes
│       ├── audit.py         live transaction log
│       └── demo_service.py
├── scripts/seed_demo_data.py    fallback test data (not needed: database/mysql/seeds/ loads it)
├── demo/concurrency_demo.py     double booking, lost update, deadlock
├── demo/recovery_demo.py        2PC crash + recovery
└── var/                         2PC coordinator decision log (not committed)
```

## Data placement (agreed design)

- **Fragmented by city** (only on that city's node): stations, charger_units, slots, bookings, payments, refunds.
- **Replicated** (same rows, same IDs, on all nodes): cities, pricing_plans, users, vehicles.
- **Wallet:** `users.wallet_balance` is only real on the user's **home node** (`users.home_city_id`).
  Booking in your home city = 1 node, plain transaction. Booking in another city = 2 nodes,
  two-phase commit (`app/services/xa.py`).

`users.home_city_id` and the wallet CHECK are in `database/mysql/schema/02_core.sql`.
The backend logs an error at startup if a node was built from an older schema.

## Run it

### With Docker (whole project)

```bash
docker-compose up --build                                  # schema, triggers and seed data load automatically
docker exec ev-backend python demo/concurrency_demo.py                       # double booking
docker exec ev-backend python demo/concurrency_demo.py --scenario wallet     # lost update
docker exec ev-backend python demo/concurrency_demo.py --scenario deadlock   # deadlock + retry
docker exec ev-backend python demo/recovery_demo.py                          # 2PC crash + recovery
```

The node-crash part of the recovery demo kills a MySQL container, so it needs the `docker`
command and runs from your own terminal, not inside the backend container:

```bash
cd backend
pip install httpx
python demo/recovery_demo.py --node-crash
```

The database is only built when its Docker volume is empty. After any change under
`database/mysql/`, reset with `docker-compose down -v` (deletes DB data) and start again.
Demo logins: `driver.bangalore@demo.ev` / `demo1234` (also chennai, delhi).

### Without Docker (backend only, against local MySQL)

```bash
cd backend
python -m venv venv && source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Defaults expect MySQL on localhost ports 3306/3307/3308 with user `ev_user`
(see `app/core/config.py`). Open http://localhost:8000/docs.

## Settings (environment variables)

| Variable | Default | Meaning |
|----------|---------|---------|
| `DEMO_MODE` | `true` | Enables `/api/demo/*` (unsafe booking etc.). Set `false` outside demos. |
| `SQL_ECHO` | `false` | Print every SQL statement |
| `SECRET_KEY` | placeholder | JWT signing key |
| `DB_TIME_ZONE` | `+05:30` | MySQL session time zone, so "slot in the past" checks use IST |
| `RECOVERY_INTERVAL_S` | `30` | Seconds between background recovery passes. `0` turns it off |
| `XA_LOG_PATH` | `backend/var/xa_coordinator.log` | The 2PC coordinator's decision log |

Run a single uvicorn worker (the default). The coordinator tracks its in-flight transactions in
memory, so several workers would each think the others' transactions were abandoned.

## Notes for teammates

- **Database (Vyaan):** the backend is tested against `database/mysql` on main (schema, all triggers,
  seeds). `after_charger_fault` refunds bookings made through the API straight into the wallet;
  the refunds it queues for users from other cities are paid by `recovery_service` over 2PC
  (same idea as `sp_process_refund`, but across two nodes). Recovery uses the
  `XA_RECOVER_ADMIN` grant from `init.sh`.
- **Person 3:** the backend writes `audit_log` and `charging_sessions` documents
  (`{city, booking_id, charger_id, user_id, status, started_at, ended_at, energy_kwh, final_cost}`)
  and reads `charger_status` by `{charger_id, city}` for `GET /api/chargers/...`. All of it is
  best effort: with MongoDB down everything still works on MySQL. Tell me if your document
  shapes differ and I'll match them.
- **Person 4:** see `docs/API.md`. Always keep `(city, id)` pairs, since IDs repeat across cities.
