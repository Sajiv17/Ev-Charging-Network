# MongoDB (Person 3, Distributed + NoSQL)

MongoDB 6.0 real-time data storage for the EV Charging Network.

**Collections:**
- `charger_status` — Real-time operational status for all chargers (updated every 5-10s)
- `charging_sessions` — Active and completed session logs with energy consumption
- `fault_reports` — Operator-submitted fault reports with photos and resolution tracking
- `audit_log` — Transaction event log for concurrency demo and debugging

---

## 📚 Complete Documentation

**For comprehensive guides, see:**
- **[DISTRIBUTED.md](../../docs/DISTRIBUTED.md)** — Distributed architecture: 3 MySQL city nodes, horizontal fragmentation, CAP theorem, XA transactions
- **[TESTING_E2E.md](../../docs/TESTING_E2E.md)** — End-to-end testing: distributed setup verification, failure scenarios, performance benchmarks
- **[README_SIMULATOR.md](../../backend/scripts/README_SIMULATOR.md)** — Real-time status simulator: how it works, running it, troubleshooting

This README covers MongoDB setup only. For the big picture, start with DISTRIBUTED.md.

---

## Folder Layout

```
database/mongodb/
├── schemas/                    Schema documentation (JS comments showing structure)
│   ├── charger_status.js       Real-time charger telemetry
│   ├── charging_sessions.js    Session logs with energy data
│   ├── fault_reports.js        Unstructured fault reports
│   └── audit_log.js            Transaction event logging
│
└── seeds/
    └── init_collections.js     Creates all collections with validation + indexes
```

**Backend integration:**
- `backend/scripts/seed_mongodb.py` — Seed sample data
- `backend/app/services/mongodb_service.py` — CRUD operations for all collections

---

## How MongoDB is Initialized

`docker-compose.yml` sets `MONGO_INITDB_DATABASE=ev_realtime`. When the container starts,
MongoDB runs `init_collections.js` which creates all 4 collections with:
- JSON Schema validation
- 21 indexes total
- Proper enum constraints

After collections exist, run the seed script to populate sample data:

```bash
docker exec ev-backend python backend/scripts/seed_mongodb.py
```

---

## Collections at a Glance

### charger_status (Real-time telemetry)

**Purpose:** Live operational status of every charger (available, occupied, faulted, maintenance).
Updated every 5-10 seconds by the status simulator and by the backend when sessions start/end.

**Key fields:**
- `charger_id` (unique) — links to MySQL charger_units
- `status` — enum: available | occupied | faulted | maintenance
- `current_power_kw` — instantaneous power draw
- `session_energy_kwh` — cumulative energy in current session
- `last_heartbeat` — when this status was last updated

**Indexes:**
- `{ charger_id: 1 }` (unique)
- `{ station_id: 1, status: 1 }` — "show all available chargers at this station"
- `{ city: 1, status: 1 }` — city-wide status queries
- `{ last_heartbeat: 1 }` — detect stale/offline chargers

---

### charging_sessions (Session logs)

**Purpose:** Detailed logs of active and completed charging sessions. Captures continuous
energy delivery data that doesn't fit MySQL's structured booking table.

**Key fields:**
- `booking_id` (unique) — links to MySQL bookings
- `status` — enum: active | completed | interrupted
- `session_energy_kwh` — cumulative energy delivered (updated live)
- `final_energy_kwh` — locked when session ends
- `power_samples` — array of {timestamp, power_kw} for charge curve graphs
- `energy_cost` — final_energy_kwh × rate (calculated when session ends)

**Indexes:**
- `{ booking_id: 1 }` (unique)
- `{ charger_id: 1, status: 1 }` — active sessions on a charger
- `{ user_id: 1, session_started_at: -1 }` — user's session history
- `{ status: 1, session_started_at: -1 }` — find stale active sessions

---

### fault_reports (Unstructured fault data)

**Purpose:** Operator-submitted fault reports with photos, error descriptions, and resolution logs.
This is unstructured data — each charger model has different error codes, operators may attach
multiple photos, descriptions vary in length.

**Key fields:**
- `charger_id`, `station_id`, `operator_id`
- `fault_type` — category (free-form string, not enforced enum)
- `error_code` — charger-specific error code
- `severity` — enum: low | medium | high | critical
- `description` — free-form text
- `photos` — array of {filename, url, uploaded_at}
- `resolution_status` — enum: open | in_progress | resolved | escalated

**Indexes:**
- `{ charger_id: 1, fault_reported_at: -1 }` — fault history per charger
- `{ station_id: 1, resolution_status: 1 }` — open faults per station
- `{ resolution_status: 1, fault_reported_at: -1 }` — prioritize unresolved faults

---

### audit_log (Transaction events)

**Purpose:** Every booking attempt, lock acquisition, commit, and rollback is logged here
with microsecond timestamps. This is the "black box" for the concurrency demo — when two users
try to book the same slot simultaneously, this log shows exactly what happened and in what order.

**Key fields:**
- `event_type` — enum: lock_acquired, lock_wait, lock_timeout, slot_check, wallet_debit,
  booking_created, commit, rollback, xa_prepare, xa_commit, xa_rollback
- `transaction_id` — unique transaction ID
- `lock_wait_time_ms` — how long this tx waited for the lock
- `success` — did the transaction commit successfully?
- `error_message` — error if failed
- `xa_global_id` — XA global transaction ID (for cross-city bookings)

**Indexes:**
- `{ transaction_id: 1 }` — trace all events for one transaction
- `{ slot_id: 1, timestamp: 1 }` — timeline of all attempts on a slot
- `{ timestamp: -1 }` — recent events first (for live monitoring)

---

## Backend Service Layer

`backend/app/services/mongodb_service.py` provides clean CRUD operations:

**Charger Status:**
- `get_charger_status(charger_id)` — current status
- `get_station_chargers_status(station_id)` — all chargers at a station
- `update_charger_status(...)` — update status, power, energy (called by simulator)
- `create_charger_status(...)` — add new charger

**Sessions:**
- `create_charging_session(...)` — start new session
- `update_session_energy(...)` — update cumulative energy (called by simulator)
- `end_charging_session(...)` — finalize session and calculate cost
- `get_active_sessions()` — all active sessions
- `get_user_sessions(user_id)` — user's session history

**Fault Reports:**
- `create_fault_report(...)` — file new fault
- `update_fault_status(...)` — update resolution status
- `get_station_faults(station_id)` — faults for a station

**Audit Log:**
- `log_transaction_event(...)` — log transaction event
- `get_transaction_audit_trail(tx_id)` — all events for one transaction
- `get_slot_contention_log(slot_id)` — all attempts on a slot
- `get_recent_audit_events()` — live monitoring feed

---

## Seeding MongoDB

After MySQL is seeded and the backend can connect to both databases:

```bash
# Make sure containers are running
docker-compose up -d

# Run the seed script
docker exec ev-backend python backend/scripts/seed_mongodb.py
```

This populates:
- **charger_status**: all chargers from MySQL (initial state: all available)
- **charging_sessions**: 5 completed + 2 active sessions
- **fault_reports**: 3 resolved + 1 open fault
- **audit_log**: sample transaction events (successful + failed booking)

---

## Integration with Backend

The backend's `live_status.py` service uses MongoDB:

```python
from app.services import mongodb_service

# Get live status for a station
chargers = mongodb_service.get_station_chargers_status(station_id=2)
# Returns: [{"charger_id": 5, "status": "available", "current_power_kw": 0.0, ...}, ...]

# Update charger status (called by simulator)
mongodb_service.update_charger_status(
    charger_id=5,
    status="occupied",
    current_power_kw=47.8,
    session_energy_kwh=12.3,
    active_booking_id=142
)
```

---

## Next Steps (Phase 2)

Phase 1 is complete:
- ✅ MongoDB schemas documented
- ✅ Collections created with validation + indexes
- ✅ Seed data script
- ✅ Backend service layer with CRUD operations

**Phase 2** will add:
- Real-time status simulator (updates charger_status every 5s)
- Session simulator (increments session_energy_kwh for active sessions)
- Integration with backend API endpoints
- Distributed setup documentation

---

## Testing

```bash
# Connect to MongoDB
docker exec -it ev-mongodb mongosh -u ev_admin -p evcharge_mongo_2024

# Switch to database
use ev_realtime

# Check collections
show collections

# Query charger status
db.charger_status.find().pretty()

# Get active sessions
db.charging_sessions.find({status: "active"}).pretty()

# Check audit log
db.audit_log.find().sort({timestamp: -1}).limit(10).pretty()
```
