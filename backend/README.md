# Backend: Person 2 (Backend + Transactions)

FastAPI service that sits between the React frontend and the 3 MySQL city nodes + MongoDB.
API reference for the frontend: [`docs/API.md`](../docs/API.md).
Concurrency write-up: [`docs/CONCURRENCY.md`](../docs/CONCURRENCY.md).

## Status

| Part | Status |
|------|--------|
| Users, login (JWT), wallet top-up, vehicles | Done |
| Station search, station detail, slots with price estimate | Done |
| Booking transaction with strict 2PL + deadlock retry | Done |
| Cancel booking + refund | Done |
| Concurrency demo (double booking + lost update) | Done |
| Live transaction audit log | Done (in-memory + MongoDB `audit_log`) |
| Cross-city booking with XA two-phase commit | Phase 2 |
| Crash/recovery demo | Phase 2 |
| Charging sessions (start / end with kWh billing), fault refunds to wallet | Phase 2 |
| Deadlock demo | Phase 2 |

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
│       ├── booking_service.py   <- the 2PL booking transaction
│       ├── user_service.py
│       ├── station_service.py
│       ├── pricing.py
│       ├── replication.py   writes to replicated tables on all nodes
│       ├── audit.py         live transaction log
│       └── demo_service.py
├── scripts/seed_demo_data.py    test data for all 3 nodes
└── demo/concurrency_demo.py     the live concurrency demo
```

## Data placement (agreed design)

- **Fragmented by city** (only on that city's node): stations, charger_units, slots, bookings, payments, refunds.
- **Replicated** (same rows, same IDs, on all nodes): cities, pricing_plans, users, vehicles.
- **Wallet:** `users.wallet_balance` is only real on the user's **home node** (`users.home_city_id`).
  Booking in your home city = 1 node, plain transaction. Booking in another city = 2 nodes,
  needs two-phase commit (phase 2).

This needs `database/mysql/schema/02_backend_additions.sql` (adds `users.home_city_id`).
The backend logs an error at startup if it is missing.

## Run it

### With Docker (whole project)

```bash
docker-compose up --build
docker exec ev-backend python -m scripts.seed_demo_data      # once, loads test data
docker exec ev-backend python demo/concurrency_demo.py       # the demo
```

If you already had the MySQL containers before `02_backend_additions.sql` was added, the init
scripts will not rerun. Reset with `docker-compose down -v` (deletes DB data) and start again.

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

## Notes for teammates

- **Person 1:** please review `02_backend_additions.sql`. Also, the trigger in `database/mysql/triggers/`
  is not loaded by Docker (only `schema/` is mounted), and it refunds the full amount rather than
  "proportional to unused time" as in the pitch.
- **Person 3:** the audit log writes to `audit_log` in MongoDB. If MongoDB is down, bookings still
  work and the log is still served from memory. Suggest `serverSelectionTimeoutMS=2000` on the
  MongoClient so a missing MongoDB fails fast.
- **Person 4:** see `docs/API.md`. Always keep `(city, id)` pairs, since IDs repeat across cities.
