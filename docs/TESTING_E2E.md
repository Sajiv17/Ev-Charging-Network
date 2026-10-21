# End-to-End Testing Guide

**Person 3: Distributed Database + NoSQL Testing**

This guide walks you through testing the complete distributed system from scratch.

---

## Prerequisites

All Docker containers running:
```bash
docker ps
# Should show: ev-mysql-bangalore, ev-mysql-chennai, ev-mysql-delhi, ev-mongodb, ev-backend
```

---

## Test 1: Verify Distributed MySQL Setup

### 1.1 Check All City Nodes Are Running

```bash
# Bangalore node
docker exec ev-mysql-bangalore mysql -u ev_user -pevcharge_pass_2024 -e \
  "SELECT DATABASE(); SELECT COUNT(*) as station_count FROM ev_bangalore.stations"

# Chennai node
docker exec ev-mysql-chennai mysql -u ev_user -pevcharge_pass_2024 -e \
  "SELECT DATABASE(); SELECT COUNT(*) as station_count FROM ev_chennai.stations"

# Delhi node
docker exec ev-mysql-delhi mysql -u ev_user -pevcharge_pass_2024 -e \
  "SELECT DATABASE(); SELECT COUNT(*) as station_count FROM ev_delhi.stations"
```

**Expected:** Each city reports different station counts (data is fragmented).

---

### 1.2 Verify Data Fragmentation

**Test:** Bangalore node should ONLY have Bangalore stations.

```bash
docker exec ev-mysql-bangalore mysql -u ev_user -pevcharge_pass_2024 ev_bangalore -e \
  "SELECT s.station_id, c.city_name, s.station_name 
   FROM stations s 
   JOIN cities c ON s.city_id = c.city_id 
   LIMIT 5"
```

**Expected:** All rows show `city_name = 'Bangalore'`.

**Repeat for Chennai and Delhi** — each should only show their own city's data.

---

### 1.3 Verify Data Replication

**Test:** Users table should be IDENTICAL on all 3 nodes.

```bash
# Count users on each node
docker exec ev-mysql-bangalore mysql -u ev_user -pevcharge_pass_2024 -e \
  "SELECT COUNT(*) FROM ev_bangalore.users"

docker exec ev-mysql-chennai mysql -u ev_user -pevcharge_pass_2024 -e \
  "SELECT COUNT(*) FROM ev_chennai.users"

docker exec ev-mysql-delhi mysql -u ev_user -pevcharge_pass_2024 -e \
  "SELECT COUNT(*) FROM ev_delhi.users"
```

**Expected:** All 3 counts are the same (users are replicated).

---

## Test 2: Verify MongoDB Setup

### 2.1 Check MongoDB Connection

```bash
docker exec -it ev-mongodb mongosh -u ev_admin -p evcharge_mongo_2024
```

Inside MongoDB shell:
```javascript
use ev_realtime
show collections
// Should show: charger_status, charging_sessions, fault_reports, audit_log

db.charger_status.countDocuments()
// Should show total number of chargers across ALL cities

exit
```

---

### 2.2 Seed MongoDB

```bash
docker exec ev-backend python backend/scripts/seed_mongodb.py
```

**Expected output:**
```
Seeding MongoDB collections...
✓ Created 27 charger status records (from all city nodes)
✓ Created 5 completed sessions
✓ Created 2 active sessions
✓ Created 4 fault reports
✓ Created sample audit log events
```

---

### 2.3 Verify MongoDB Indexes

```bash
docker exec ev-backend python backend/scripts/test_mongodb_integration.py
```

**Expected:** All checks pass with ✓ marks.

---

## Test 3: Backend Integration

### 3.1 Check Backend Can Connect to All Nodes

```bash
# Health check endpoint (if implemented)
curl http://localhost:8000/api/operations/node-health
```

**Expected:**
```json
{
  "bangalore": {"status": "healthy", "latency_ms": 12},
  "chennai": {"status": "healthy", "latency_ms": 15},
  "delhi": {"status": "healthy", "latency_ms": 18},
  "mongodb": {"status": "healthy", "latency_ms": 8}
}
```

---

### 3.2 Query Local Station Data

```bash
# Get Bangalore stations (should hit Bangalore node only)
curl http://localhost:8000/api/stations?city=bangalore
```

**Expected:** Returns Bangalore stations only.

---

### 3.3 Query Cross-City Station Data

```bash
# Get Chennai stations (backend should route to Chennai node)
curl http://localhost:8000/api/stations?city=chennai
```

**Expected:** Returns Chennai stations (routed to Chennai MySQL node).

---

## Test 4: Real-Time Simulator

### 4.1 Start Simulator

```bash
# Using helper script
./scripts/simulator.sh start

# Or directly in Docker
docker exec -d ev-backend python backend/scripts/simulate_realtime_status.py
```

---

### 4.2 Check Simulator Status

```bash
./scripts/simulator.sh status
```

**Expected:**
```
✓ Simulator is running
<process-id>  python backend/scripts/simulate_realtime_status.py
```

---

### 4.3 Watch Live Updates

```bash
./scripts/simulator.sh logs
```

**Expected output (every 5 seconds):**
```
[10:32:15] Total: 27 | Available: 23 | Occupied: 2 | Faulted: 1 | Maintenance: 1 | Active Sessions: 2
  Charger 2 (bangalore): 47.8 kW, 12.34 kWh
  Charger 11 (chennai): 6.9 kW, 7.82 kWh
```

Press `Ctrl+C` to stop watching logs.

---

### 4.4 Verify MongoDB Is Being Updated

**Option 1: MongoDB shell**
```bash
docker exec -it ev-mongodb mongosh -u ev_admin -p evcharge_mongo_2024
```

```javascript
use ev_realtime

// Check last_heartbeat is recent (should be within last 10 seconds)
db.charger_status.findOne({charger_id: 1})

// Watch occupied chargers (run this, wait 10s, run again — energy should increase)
db.charger_status.find({status: "occupied"}).pretty()

// Check power samples are being added
db.charging_sessions.findOne({status: "active"}).power_samples
// Should show growing array of {timestamp, power_kw} entries

exit
```

**Option 2: Backend API**
```bash
# Get live charger status
curl http://localhost:8000/api/stations/1/live
```

**Expected:** Returns live charger data with fresh `last_heartbeat` timestamp.

---

### 4.5 Wait for Session Auto-Completion

Sessions 30+ minutes old have 5% chance to end every 50 seconds.

```bash
# Watch logs for session completions
docker logs -f ev-backend | grep "Session ended"
```

**Expected (after a few minutes):**
```
Session ended: Charger 2, 28.50 kWh, ₹356.25
```

---

### 4.6 Stop Simulator

```bash
./scripts/simulator.sh stop
```

---

## Test 5: Distributed Transaction (XA)

**Note:** This test requires XA coordinator implementation in `backend/app/services/xa.py`.

### 5.1 Cross-City Booking Scenario

**Setup:**
- User 10 lives in Bangalore (home_city_id = 1)
- User wants to book a Chennai station (cross-city booking)

**What should happen:**
1. Backend debits wallet on **Bangalore** node (user's home city)
2. Backend creates booking on **Chennai** node (station's city)
3. XA transaction ensures both succeed or both fail

---

### 5.2 Test Cross-City Booking API

```bash
curl -X POST http://localhost:8000/api/bookings \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 10,
    "slot_id": 100,
    "vehicle_id": 1,
    "payment_method": "wallet"
  }'
```

**Expected response:**
```json
{
  "booking_id": 123,
  "status": "confirmed",
  "wallet_debited": 100.00,
  "city": "chennai"
}
```

---

### 5.3 Verify XA Transaction in Logs

```bash
docker logs ev-backend | grep "XA"
```

**Expected logs:**
```
XA START 'tx_<uuid>_bangalore'
XA END 'tx_<uuid>_bangalore'
XA PREPARE 'tx_<uuid>_bangalore'
XA START 'tx_<uuid>_chennai'
XA END 'tx_<uuid>_chennai'
XA PREPARE 'tx_<uuid>_chennai'
XA COMMIT 'tx_<uuid>_bangalore'
XA COMMIT 'tx_<uuid>_chennai'
```

---

### 5.4 Verify Audit Log in MongoDB

```bash
docker exec -it ev-mongodb mongosh -u ev_admin -p evcharge_mongo_2024
```

```javascript
use ev_realtime

// Find recent transaction events
db.audit_log.find({event_type: {$in: ["xa_prepare", "xa_commit"]}}).sort({timestamp: -1}).limit(5).pretty()

exit
```

**Expected:** Shows XA PREPARE and XA COMMIT events for both city nodes.

---

## Test 6: Failure Scenarios

### 6.1 Simulate City Node Failure

**Scenario:** Chennai node goes down.

```bash
# Stop Chennai node
docker stop ev-mysql-chennai
```

**Test local bookings still work:**
```bash
# Bangalore booking should succeed
curl -X POST http://localhost:8000/api/bookings \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 10,
    "slot_id": 50,
    "vehicle_id": 1,
    "city": "bangalore"
  }'
```

**Expected:** ✅ Booking succeeds (Bangalore node is still up).

**Test Chennai bookings fail gracefully:**
```bash
# Chennai booking should fail
curl -X POST http://localhost:8000/api/bookings \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 10,
    "slot_id": 100,
    "vehicle_id": 1,
    "city": "chennai"
  }'
```

**Expected:** ❌ 503 Service Unavailable with error message.

**Restore Chennai node:**
```bash
docker start ev-mysql-chennai
```

**Test Chennai bookings resume:**
```bash
# Retry Chennai booking
curl -X POST http://localhost:8000/api/bookings \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 10,
    "slot_id": 100,
    "vehicle_id": 1,
    "city": "chennai"
  }'
```

**Expected:** ✅ Booking succeeds (Chennai node is back up).

---

### 6.2 Simulate MongoDB Failure

```bash
# Stop MongoDB
docker stop ev-mongodb
```

**Test MySQL bookings still work:**
```bash
curl -X POST http://localhost:8000/api/bookings \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 10,
    "slot_id": 51,
    "vehicle_id": 1,
    "city": "bangalore"
  }'
```

**Expected:** ✅ Booking succeeds (MySQL handles transactional data independently).

**Test live status fails gracefully:**
```bash
curl http://localhost:8000/api/stations/1/live
```

**Expected:** ❌ Error (MongoDB unavailable) or cached data.

**Restore MongoDB:**
```bash
docker start ev-mongodb
```

---

## Test 7: Data Consistency Checks

### 7.1 Verify Charger Count Matches Across Systems

**MySQL total (sum of all city nodes):**
```bash
echo "Bangalore:"
docker exec ev-mysql-bangalore mysql -u ev_user -pevcharge_pass_2024 -e \
  "SELECT COUNT(*) FROM ev_bangalore.charger_units"

echo "Chennai:"
docker exec ev-mysql-chennai mysql -u ev_user -pevcharge_pass_2024 -e \
  "SELECT COUNT(*) FROM ev_chennai.charger_units"

echo "Delhi:"
docker exec ev-mysql-delhi mysql -u ev_user -pevcharge_pass_2024 -e \
  "SELECT COUNT(*) FROM ev_delhi.charger_units"
```

**MongoDB total:**
```bash
docker exec -it ev-mongodb mongosh -u ev_admin -p evcharge_mongo_2024 --eval \
  "db = db.getSiblingDB('ev_realtime'); db.charger_status.countDocuments({})"
```

**Expected:** MongoDB count = Bangalore + Chennai + Delhi.

---

### 7.2 Verify Active Sessions Match

**MySQL active bookings (sum of all cities):**
```bash
docker exec ev-mysql-bangalore mysql -u ev_user -pevcharge_pass_2024 -e \
  "SELECT COUNT(*) FROM ev_bangalore.bookings WHERE status = 'in_progress'"

docker exec ev-mysql-chennai mysql -u ev_user -pevcharge_pass_2024 -e \
  "SELECT COUNT(*) FROM ev_chennai.bookings WHERE status = 'in_progress'"

docker exec ev-mysql-delhi mysql -u ev_user -pevcharge_pass_2024 -e \
  "SELECT COUNT(*) FROM ev_delhi.bookings WHERE status = 'in_progress'"
```

**MongoDB active sessions:**
```bash
docker exec -it ev-mongodb mongosh -u ev_admin -p evcharge_mongo_2024 --eval \
  "db = db.getSiblingDB('ev_realtime'); db.charging_sessions.countDocuments({status: 'active'})"
```

**Expected:** Should be close (might differ by 1-2 due to timing of simulator ending sessions).

---

## Test 8: Performance Benchmarks

### 8.1 Local Query Performance

```bash
# Time a local query (same-city lookup)
time curl -s http://localhost:8000/api/stations?city=bangalore > /dev/null
```

**Expected:** < 50ms

---

### 8.2 Cross-City Query Performance

```bash
# Time a cross-city query
time curl -s http://localhost:8000/api/stations?city=chennai > /dev/null
```

**Expected:** < 100ms (slightly slower due to routing, but still fast).

---

### 8.3 MongoDB Query Performance

```bash
# Time a MongoDB query
time curl -s http://localhost:8000/api/stations/1/live > /dev/null
```

**Expected:** < 30ms (MongoDB is fast for reads).

---

## Test 9: Frontend Integration

**Note:** Person 4 is responsible for frontend, but here's how to test the integration.

### 9.1 Live Station Dashboard

1. Open frontend: http://localhost:3000/stations/1
2. Watch charger status update every 5-10 seconds
3. Power draw and energy should increment for occupied chargers

**Expected:**
- Chargers show "Available", "Occupied", "Faulted", or "Maintenance"
- Occupied chargers show real-time power (kW) and energy (kWh)
- Status updates without page refresh (WebSocket or polling)

---

### 9.2 Charging Session Progress

1. Start a charging session (book a slot, plug in)
2. Navigate to "My Sessions" page
3. Watch energy meter increase

**Expected:**
- Energy kWh increments every 5-10 seconds
- Charge curve graph shows power samples over time
- Estimated cost updates based on energy consumed

---

## Test 10: Demo Walkthrough

**Full demo flow for presentation:**

1. **Show distributed setup:**
   ```bash
   docker ps
   # Show all 5 containers running
   ```

2. **Show data fragmentation:**
   ```bash
   # Query each city node, show different data
   ```

3. **Start simulator:**
   ```bash
   ./scripts/simulator.sh start
   ./scripts/simulator.sh logs
   # Let it run for 30 seconds, show live updates
   ```

4. **Show MongoDB live data:**
   ```bash
   # Open MongoDB shell, show real-time updates
   ```

5. **Show frontend:**
   - Open http://localhost:3000
   - Show live station dashboard
   - Show active sessions updating

6. **Simulate failure:**
   ```bash
   docker stop ev-mysql-chennai
   # Try to book Chennai station → fails
   # Try to book Bangalore station → succeeds
   docker start ev-mysql-chennai
   ```

7. **Show recovery:**
   - Chennai bookings resume immediately
   - No data lost

---

## Troubleshooting

### MongoDB Not Updating

**Check simulator is running:**
```bash
./scripts/simulator.sh status
```

**Check MongoDB connection:**
```bash
docker exec ev-backend python -c "from pymongo import MongoClient; print(MongoClient('mongodb://ev_admin:evcharge_mongo_2024@mongodb:27017/').server_info())"
```

---

### City Node Not Responding

**Check Docker container status:**
```bash
docker ps -a | grep mysql
```

**Restart specific node:**
```bash
docker restart ev-mysql-<city>
```

---

### Cross-City Booking Fails

**Check XA coordinator logs:**
```bash
docker logs ev-backend | grep -E "XA|transaction"
```

**Verify both nodes are reachable:**
```bash
docker exec ev-backend python -c "
from app.db.mysql_connection import get_city_session
for city in ['bangalore', 'chennai', 'delhi']:
    try:
        db = get_city_session(city)
        print(f'{city}: OK')
        db.close()
    except Exception as e:
        print(f'{city}: FAILED - {e}')
"
```

---

## Summary Checklist

Before marking Person 3's work complete:

- [ ] All 3 MySQL city nodes running and seeded
- [ ] MongoDB running with all 4 collections
- [ ] 21 indexes created across MongoDB collections
- [ ] Backend can connect to all nodes
- [ ] Simulator updates MongoDB every 5 seconds
- [ ] Heartbeats are fresh (< 10 seconds old)
- [ ] Sessions auto-complete after 30+ minutes
- [ ] Data fragmentation verified (each city has own data)
- [ ] Data replication verified (users same on all nodes)
- [ ] Cross-city queries work
- [ ] Failure scenarios tested (node goes down, recovers)
- [ ] Documentation complete (DISTRIBUTED.md, README.md, README_SIMULATOR.md)

---

**Person 3's deliverables:**
- ✅ MongoDB schemas with validation (4 collections)
- ✅ MongoDB indexes (21 total)
- ✅ MongoDB seed data
- ✅ MongoDB CRUD service layer (600+ lines)
- ✅ Real-time status simulator (400+ lines)
- ✅ Integration tests
- ✅ Distributed architecture documentation
- ✅ End-to-end testing guide
