# Docker & Distributed Setup — Person 3 (Distributed + NoSQL)

## Your Responsibility

Set up the distributed infrastructure (3 MySQL city nodes + MongoDB) and build the MongoDB integration.

---

## What You Build

### 📁 `docker/` (this folder)
**Currently empty — you add custom configs here if needed**

**Tasks:**
- If you need custom MySQL configs (e.g., replication settings), put them here as `mysql-bangalore.cnf`, `mysql-chennai.cnf`, etc.
- If you need MongoDB init scripts, put them here

**Note:** The main `docker-compose.yml` is already set up at the root. You can extend it if needed.

---

### 📁 `database/mongodb/schemas/`
**Empty — you create these**

Document the MongoDB schema structure (Mongoose-style for documentation):

**Tasks:**
- `charger_status_schema.js` — structure for real-time charger status
- `charging_session_schema.js` — structure for active charging sessions
- `fault_report_schema.js` — structure for operator fault reports
- `audit_log_schema.js` — structure for transaction audit trail

**Example `charger_status_schema.js`:**
```javascript
// MongoDB collection: charger_status
// One document per charger unit

{
  charger_id: 5,              // INT - references MySQL charger_units.charger_id
  station_id: 2,              // INT
  status: "available",        // "available" | "occupied" | "faulted" | "maintenance"
  current_power_kw: 0.0,      // FLOAT - current power draw (0 if not charging)
  last_heartbeat: ISODate("2024-10-05T14:32:10Z"),
  fault_code: null,           // STRING - error code if faulted
  updated_at: ISODate("2024-10-05T14:32:10Z")
}
```

### 📁 `database/mongodb/seeds/`
**Empty — you create these**

Sample data to populate MongoDB:

**Tasks:**
- `charger_status_seed.json` — initial status for all chargers
- `charging_sessions_seed.json` — a few sample active sessions
- `fault_reports_seed.json` — sample fault reports

**Example `charger_status_seed.json`:**
```json
[
  {
    "charger_id": 1,
    "station_id": 1,
    "status": "available",
    "current_power_kw": 0.0,
    "last_heartbeat": "2024-10-05T10:00:00Z",
    "fault_code": null
  },
  {
    "charger_id": 2,
    "station_id": 1,
    "status": "occupied",
    "current_power_kw": 47.5,
    "last_heartbeat": "2024-10-05T10:05:00Z",
    "fault_code": null
  }
]
```

---

### 📁 `backend/app/services/` (shared with Person 2)
**You add:**

**Tasks:**
- `mongodb_service.py` — functions to read/write MongoDB data

**Example:**
```python
from app.db.mongodb_connection import charger_status_collection
from datetime import datetime

def get_charger_status(charger_id: int):
    """Get real-time status of a charger from MongoDB"""
    return charger_status_collection.find_one({"charger_id": charger_id})

def update_charger_status(charger_id: int, status: str, power_kw: float):
    """Update charger status in real-time"""
    charger_status_collection.update_one(
        {"charger_id": charger_id},
        {
            "$set": {
                "status": status,
                "current_power_kw": power_kw,
                "last_heartbeat": datetime.utcnow()
            }
        },
        upsert=True
    )

def start_charging_session(charger_id: int, booking_id: int):
    """Log start of charging session"""
    from app.db.mongodb_connection import charging_sessions_collection
    charging_sessions_collection.insert_one({
        "charger_id": charger_id,
        "booking_id": booking_id,
        "start_time": datetime.utcnow(),
        "energy_consumed_kwh": 0.0,
        "status": "active"
    })
```

---

### 📁 `backend/scripts/`
**You add:**

**Tasks:**
- `simulate_realtime_status.py` — script that updates MongoDB every 5 seconds to simulate real charger telemetry
- `seed_mongodb.py` — script to load seed data into MongoDB

**Example `simulate_realtime_status.py`:**
```python
import time
import random
from app.db.mongodb_connection import charger_status_collection
from datetime import datetime

while True:
    # Pick a random charger and update its power draw
    charger_id = random.randint(1, 20)
    power_kw = random.uniform(0, 50) if random.random() > 0.3 else 0.0
    
    charger_status_collection.update_one(
        {"charger_id": charger_id},
        {
            "$set": {
                "current_power_kw": power_kw,
                "last_heartbeat": datetime.utcnow()
            }
        }
    )
    
    print(f"Updated charger {charger_id}: {power_kw:.2f} kW")
    time.sleep(5)
```

---

## Distributed DB Setup

**Already configured in `docker-compose.yml`:**
- ✅ 3 MySQL nodes (ports 3306, 3307, 3308)
- ✅ MongoDB (port 27017)
- ✅ Backend connects to all 3 MySQL nodes

**Your additional tasks:**
- Test cross-city queries (book a Chennai station from Bangalore)
- Document horizontal fragmentation in `docs/DISTRIBUTED.md`
- Show replication strategy (global catalog vs local data)

---

## Testing Your Work

```bash
# Start all services
docker-compose up --build

# Connect to MongoDB
docker exec -it ev-mongodb mongosh -u ev_admin -p evcharge_mongo_2024

# Check collections
use ev_realtime
db.charger_status.find().pretty()

# Run your status simulator (from another terminal)
docker exec -it ev-backend python scripts/simulate_realtime_status.py
```

---

## Your Branch

```bash
git checkout -b distributed-nosql
# Make changes
git add database/mongodb/ backend/scripts/ docker/
git commit -m "feat(mongodb): add real-time charger status tracking"
git push origin distributed-nosql
# Open PR to main
```

---

## What You DON'T Touch

- ❌ `database/mysql/` — Person 1's territory
- ❌ `backend/app/api/` — Person 2's territory (but coordinate on services/)
- ❌ `frontend/` — Person 4's territory
