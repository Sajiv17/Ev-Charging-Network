# Real-Time Status Simulator

The real-time status simulator continuously updates MongoDB to simulate live charger telemetry.

---

## What It Does

Every 5 seconds:
1. **Updates heartbeats** for all chargers (shows they're online)
2. **Simulates power draw** for occupied chargers:
   - DC fast chargers: 48-50 kW initially, tapering to 20-30 kW as battery fills
   - AC chargers: Steady 6-8 kW
3. **Increments energy** delivered in active sessions
4. **Adds power samples** to charging_sessions for charge curve graphs
5. **Randomly ends** long-running sessions (30+ minutes, 5% chance per check)

---

## Running the Simulator

### Option 1: Run in Docker (Recommended)

```bash
# Start in background
docker exec -d ev-backend python backend/scripts/simulate_realtime_status.py

# View logs
docker logs -f ev-backend

# Stop (kill the Python process inside container)
docker exec ev-backend pkill -f simulate_realtime_status.py
```

### Option 2: Run Locally

```bash
# Make sure MongoDB and MySQL are running
docker-compose up -d mongodb mysql-bangalore mysql-chennai mysql-delhi

# Activate venv if you have one
source venv/bin/activate

# Run simulator
python backend/scripts/simulate_realtime_status.py

# Stop with Ctrl+C
```

### Option 3: Custom Update Interval

```bash
# Update every 10 seconds instead of 5
docker exec -d ev-backend python backend/scripts/simulate_realtime_status.py --interval 10
```

---

## What You'll See

```
======================================================================
Real-Time Charger Status Simulator
======================================================================
Update interval: 5 seconds
Press Ctrl+C to stop
======================================================================

Connected to MongoDB: ev_realtime
Charger status collection: 27 chargers
Active sessions: 2

[10:32:15] Total: 27 | Available: 23 | Occupied: 2 | Faulted: 1 | Maintenance: 1 | Active Sessions: 2
  Charger 2 (bangalore): 47.8 kW, 12.34 kWh
  Charger 11 (chennai): 6.9 kW, 7.82 kWh

[10:32:20] Total: 27 | Available: 23 | Occupied: 2 | Faulted: 1 | Maintenance: 1 | Active Sessions: 2
  Charger 2 (bangalore): 46.5 kW, 12.41 kWh
  Charger 11 (chennai): 6.8 kW, 7.83 kWh

  Session ended: Charger 2, 28.50 kWh, ₹356.25

[10:32:25] Total: 27 | Available: 24 | Occupied: 1 | Faulted: 1 | Maintenance: 1 | Active Sessions: 1
  Charger 11 (chennai): 6.7 kW, 7.84 kWh
```

---

## How It Integrates with Backend

The backend's `live_status.py` service reads from MongoDB:

```python
from app.services import live_status

# Get live charger status (updated by simulator)
status = live_status.charger_live(city="bangalore", charger_id=2)
# Returns: {"charger_id": 2, "status": "occupied", "current_power_kw": 47.8, ...}
```

The simulator updates:
- `charger_status` collection — power, energy, heartbeat
- `charging_sessions` collection — energy, power samples

The backend API reads this data to show:
- Live station dashboard (operator view)
- Current charging session progress (driver view)
- Charger availability in real-time

---

## Seeding Before Running

Make sure MongoDB is seeded first:

```bash
# Seed MongoDB with initial charger status
docker exec ev-backend python backend/scripts/seed_mongodb.py

# Then start simulator
docker exec -d ev-backend python backend/scripts/simulate_realtime_status.py
```

---

## Testing the Simulator

### Check MongoDB is Being Updated

```bash
# Connect to MongoDB
docker exec -it ev-mongodb mongosh -u ev_admin -p evcharge_mongo_2024

# Switch to database
use ev_realtime

# Watch charger status update in real-time (run this, then wait 5-10 seconds and run again)
db.charger_status.find({status: "occupied"}).pretty()

# Check last_heartbeat is recent (should be within last 5 seconds)
db.charger_status.findOne({charger_id: 1})
```

### Check Sessions Are Being Updated

```bash
# Active sessions should show increasing session_energy_kwh
db.charging_sessions.find({status: "active"}).pretty()

# Power samples array should be growing
db.charging_sessions.findOne({status: "active"}).power_samples
```

---

## How Sessions End

Sessions end in two ways:

1. **Simulator randomly ends them** — After 30+ minutes, 5% chance every 50 seconds
2. **Backend ends them** — When driver clicks "Stop Charging" in the UI

When a session ends:
1. Charger status → `available`
2. Session status → `completed`
3. Final energy and cost are calculated
4. Power draw → 0 kW

---

## Troubleshooting

**Simulator not starting:**
```bash
# Check MongoDB is running
docker ps | grep mongodb

# Check backend container is running
docker ps | grep backend

# Check MongoDB connection
docker exec ev-backend python -c "from pymongo import MongoClient; print(MongoClient('mongodb://ev_admin:evcharge_mongo_2024@mongodb:27017/').server_info())"
```

**No chargers in MongoDB:**
```bash
# Seed MongoDB first
docker exec ev-backend python backend/scripts/seed_mongodb.py
```

**Simulator stops unexpectedly:**
```bash
# Check logs
docker logs ev-backend

# Run in foreground to see errors
docker exec -it ev-backend python backend/scripts/simulate_realtime_status.py
```

---

## Next Steps (Phase 3)

Phase 2 complete:
- ✅ Real-time status simulator
- ✅ Power draw simulation (DC/AC profiles)
- ✅ Energy increment every 5 seconds
- ✅ Session auto-completion

**Phase 3** will add:
- Distributed setup documentation (DISTRIBUTED.md)
- Integration testing end-to-end
- Demo walkthrough
