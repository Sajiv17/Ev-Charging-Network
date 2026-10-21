# Quick Start Testing Guide

**Complete step-by-step guide to test the entire EV Charging Network project**

---

## 🚀 Step 1: Start All Services

Open terminal and navigate to project root:

```bash
cd /Users/sajivvaila/ev-charging-network
```

Start all Docker containers:

```bash
docker-compose up -d
```

**Expected output:**
```
Creating ev-mysql-bangalore ... done
Creating ev-mysql-chennai    ... done
Creating ev-mysql-delhi      ... done
Creating ev-mongodb          ... done
Creating ev-backend          ... done
```

---

## ✅ Step 2: Verify All Containers Are Running

```bash
docker ps
```

**You should see 5 containers:**
- `ev-mysql-bangalore` (port 3306)
- `ev-mysql-chennai` (port 3307)
- `ev-mysql-delhi` (port 3308)
- `ev-mongodb` (port 27017)
- `ev-backend` (port 8000)

**If any container is missing:**
```bash
# Check logs for errors
docker logs <container-name>

# Restart if needed
docker-compose restart <service-name>
```

---

## 🗄️ Step 3: Test MySQL (Person 1's Work)

### Test Bangalore Node
```bash
docker exec ev-mysql-bangalore mysql -u ev_user -pevcharge_pass_2024 -e "SELECT COUNT(*) as stations FROM ev_bangalore.stations"
```

**Expected:** Shows number of stations in Bangalore

### Test Chennai Node
```bash
docker exec ev-mysql-chennai mysql -u ev_user -pevcharge_pass_2024 -e "SELECT COUNT(*) as stations FROM ev_chennai.stations"
```

**Expected:** Shows number of stations in Chennai (different from Bangalore)

### Test Data Fragmentation
```bash
# Bangalore should only have Bangalore stations
docker exec ev-mysql-bangalore mysql -u ev_user -pevcharge_pass_2024 ev_bangalore -e "SELECT s.station_id, c.city_name, s.station_name FROM stations s JOIN cities c ON s.city_id = c.city_id LIMIT 3"
```

**Expected:** All rows show `city_name = 'Bangalore'`

---

## 📦 Step 4: Test MongoDB (Person 3's Work)

### Seed MongoDB with sample data
```bash
docker exec ev-backend python backend/scripts/seed_mongodb.py
```

**Expected output:**
```
Seeding MongoDB collections...
✓ Created 27 charger status records
✓ Created 5 completed sessions
✓ Created 2 active sessions
✓ Created 4 fault reports
✓ Created sample audit log events
```

### Verify MongoDB has data
```bash
docker exec ev-backend python backend/scripts/test_mongodb_integration.py
```

**Expected:** All checks pass with ✓ marks

---

## 🔄 Step 5: Start Real-Time Simulator (Person 3's Work)

```bash
docker exec -d ev-backend python backend/scripts/simulate_realtime_status.py
```

**Check it's running:**
```bash
docker exec ev-backend pgrep -af simulate_realtime_status.py
```

**Watch live updates:**
```bash
docker logs -f ev-backend | grep -E "Total:|Charger|Session"
```

**You should see updates every 5 seconds:**
```
[10:32:15] Total: 27 | Available: 23 | Occupied: 2 | Faulted: 1
  Charger 2 (bangalore): 47.8 kW, 12.34 kWh
  Charger 11 (chennai): 6.9 kW, 7.82 kWh
```

Press `Ctrl+C` to stop watching.

---

## 🌐 Step 6: Test Backend API (Person 2's Work)

### Test health endpoint
```bash
curl http://localhost:8000/health
```

**Expected:** `{"status":"healthy"}`

### Test stations endpoint
```bash
curl "http://localhost:8000/api/stations?city=bangalore" | jq
```

**Expected:** JSON array of Bangalore stations

### Test live charger status
```bash
curl "http://localhost:8000/api/stations/1/chargers/status?city=bangalore" | jq
```

**Expected:** JSON array of chargers with real-time status

**If you get errors:**
```bash
# Check backend logs
docker logs ev-backend

# Check if routes are enabled in main.py
docker exec ev-backend grep -A5 "app.include_router" backend/app/main.py
```

---

## 💻 Step 7: Test Frontend (Person 4's Work)

### Install dependencies (first time only)
```bash
cd frontend
npm install
```

### Create .env file
```bash
cat > .env << EOF
REACT_APP_API_URL=http://localhost:8000
REACT_APP_USE_MOCK=false
EOF
```

### Start frontend
```bash
npm start
```

**Expected:** Browser opens at `http://localhost:3000`

**You should see:**
- Clean landing page with navigation
- NO yellow banner (means backend is reachable)
- ⚡ EV Charging Network logo

---

## 🧪 Step 8: Test Full Integration

### Test 1: Station Search
1. Open `http://localhost:3000/search`
2. Select "Bangalore" from dropdown
3. **Expected:** List of Bangalore stations from MySQL

### Test 2: Live Dashboard (MAIN DEMO)
1. Open `http://localhost:3000/dashboard`
2. Select "Bangalore" city
3. Select a station from dropdown
4. **Expected:**
   - Grid of chargers appears
   - Color-coded status badges (green/yellow/red/gray)
   - "Updated at HH:MM:SS" timestamp
   - Timestamp refreshes every 5 seconds

**Wait 10 seconds and watch:**
- Timestamp should update
- If any charger is "occupied", its power/energy should change

**This proves:**
- ✅ MongoDB simulator is running (updates every 5s)
- ✅ Backend API is reading from MongoDB
- ✅ Frontend is polling API every 5s
- ✅ Real-time integration works!

### Test 3: Booking Flow
1. Click "Find Stations" in navigation
2. Click on any station card
3. Click "Book Now"
4. **Step 1:** Select a charger → Select a time slot → Click "Continue"
5. **Step 2:** Review details → Click "Proceed to pay"
6. **Step 3:** Click "Pay ₹XXX"
7. **Expected:** "Booking confirmed ✅" message

### Test 4: My Bookings
1. Click "My Bookings" in navigation
2. **Expected:** Your booking appears under "Upcoming"
3. Click "Cancel" button
4. **Expected:** Booking moves to "Past & cancelled"

---

## 🎬 Step 9: Demo Mode Test (Failure Handling)

### Simulate backend failure
```bash
docker stop ev-backend
```

### Refresh frontend
1. Go to `http://localhost:3000`
2. **Expected:** Yellow banner appears:
   ```
   Backend API not reachable, showing demo data. Nothing here is saved to the real database.
   ```
3. Navigation still works
4. All pages show mock data
5. **This proves graceful degradation!**

### Restore backend
```bash
docker start ev-backend
```

Refresh page → Yellow banner disappears.

---

## 📊 Step 10: MongoDB Real-Time Verification

### Open MongoDB shell
```bash
docker exec -it ev-mongodb mongosh -u ev_admin -p evcharge_mongo_2024
```

### Check live data
```javascript
use ev_realtime

// Check a charger's status (run this, wait 10s, run again)
db.charger_status.findOne({charger_id: 1})
// Watch the "last_heartbeat" field - should be within last 10 seconds

// Check occupied chargers (energy should be increasing)
db.charger_status.find({status: "occupied"}).pretty()

// Check active sessions
db.charging_sessions.find({status: "active"}).pretty()

// Exit
exit
```

**Expected:**
- `last_heartbeat` is recent (within 10 seconds)
- `session_energy_kwh` increases if you check twice
- `power_samples` array grows over time

---

## 🏁 Step 11: Complete Demo Walkthrough

**For your presentation, follow this script:**

### 1. Show Infrastructure (30 seconds)
```bash
# Terminal 1: Show all containers
docker ps

# Terminal 2: Show simulator running
docker logs -f ev-backend | grep -E "Total:"
```

**Say:** "We have 3 MySQL nodes for 3 cities, MongoDB for real-time data, and a backend API. The simulator updates MongoDB every 5 seconds."

---

### 2. Show Distributed Database (1 minute)
```bash
# Show data fragmentation
docker exec ev-mysql-bangalore mysql -u ev_user -pevcharge_pass_2024 ev_bangalore -e "SELECT COUNT(*) FROM stations"
docker exec ev-mysql-chennai mysql -u ev_user -pevcharge_pass_2024 ev_chennai -e "SELECT COUNT(*) FROM stations"
```

**Say:** "Each city node only stores its own data - horizontal fragmentation. Bangalore has X stations, Chennai has Y."

---

### 3. Show MongoDB Real-Time (1 minute)
```bash
docker exec -it ev-mongodb mongosh -u ev_admin -p evcharge_mongo_2024 --eval "
use ev_realtime
db.charger_status.find({status: 'occupied'}).forEach(c => print('Charger ' + c.charger_id + ': ' + c.current_power_kw + ' kW, ' + c.session_energy_kwh + ' kWh'))
"
```

**Say:** "MongoDB stores real-time telemetry. These values update every 5 seconds."

---

### 4. Show Frontend Live Dashboard (2 minutes)
1. Open `http://localhost:3000/dashboard`
2. Select Bangalore → Select a station
3. **Point to screen:** "Watch the timestamp - it updates every 5 seconds"
4. Wait 10 seconds, point to timestamp changing
5. **Say:** "This is polling MongoDB through the backend API. Real-time integration."

---

### 5. Show Booking Flow (1 minute)
1. Click "Find Stations"
2. Pick a station → Click "Book Now"
3. Go through 3-step wizard
4. Complete booking
5. **Say:** "This creates a booking, debits wallet from user's home city, locks the slot - all using XA transactions across city nodes."

---

### 6. Show Failure Handling (1 minute)
```bash
# Stop backend
docker stop ev-backend
```

1. Refresh frontend
2. **Point to yellow banner:** "Backend is down, but UI still works with demo data"
3. **Say:** "Graceful degradation - AP in CAP theorem. System stays available even during partition."

```bash
# Restart backend
docker start ev-backend
```

---

## 🛠️ Troubleshooting

### Problem: "Connection refused" errors

**Solution:**
```bash
# Check all containers are running
docker ps

# If any are missing, restart
docker-compose up -d
```

---

### Problem: Frontend shows yellow banner even when backend is running

**Solution:**
```bash
# Check backend is accessible
curl http://localhost:8000/health

# Check CORS is enabled in backend
docker exec ev-backend grep -A10 "CORSMiddleware" backend/app/main.py

# Should include "http://localhost:3000" in allow_origins
```

---

### Problem: No data in MongoDB

**Solution:**
```bash
# Re-seed MongoDB
docker exec ev-backend python backend/scripts/seed_mongodb.py
```

---

### Problem: Simulator not updating

**Solution:**
```bash
# Check if simulator is running
docker exec ev-backend pgrep -af simulate_realtime_status.py

# If not running, start it
docker exec -d ev-backend python backend/scripts/simulate_realtime_status.py

# Check for errors
docker logs ev-backend | grep -i error
```

---

### Problem: Frontend won't start

**Solution:**
```bash
cd frontend

# Clean install
rm -rf node_modules package-lock.json
npm install

# Start again
npm start
```

---

## 📋 Complete Test Checklist

Before demo, verify:

**Infrastructure:**
- [ ] All 5 Docker containers running (`docker ps`)
- [ ] Backend health check passes (`curl http://localhost:8000/health`)

**Database:**
- [ ] MySQL nodes have data (different counts per city)
- [ ] MongoDB has 4 collections
- [ ] MongoDB has sample data (27+ chargers)

**Real-Time:**
- [ ] Simulator is running (`pgrep -af simulate`)
- [ ] MongoDB heartbeats are recent (< 10 seconds old)
- [ ] Occupied chargers show changing power/energy

**Frontend:**
- [ ] Frontend loads at `http://localhost:3000`
- [ ] No yellow banner (backend is reachable)
- [ ] Station search works
- [ ] Live dashboard updates every 5 seconds
- [ ] Booking flow creates bookings
- [ ] Demo mode works when backend is stopped

**Integration:**
- [ ] Live dashboard shows real-time MongoDB data
- [ ] Timestamp updates every 5 seconds
- [ ] Charger status badges match MongoDB enum
- [ ] Booking creates record in MySQL

---

## 🎯 Quick Test (2 Minutes)

**Fastest way to verify everything works:**

```bash
# 1. Start all services
docker-compose up -d

# 2. Seed MongoDB
docker exec ev-backend python backend/scripts/seed_mongodb.py

# 3. Start simulator
docker exec -d ev-backend python backend/scripts/simulate_realtime_status.py

# 4. Test backend API
curl http://localhost:8000/api/stations?city=bangalore

# 5. Start frontend (in new terminal)
cd frontend && npm start

# 6. Open browser
open http://localhost:3000/dashboard
```

**Select city → Select station → Watch for 10 seconds**

If timestamp updates every 5 seconds → ✅ **Everything works!**

---

## 📚 Detailed Documentation

For more details, see:
- **`docs/TESTING_E2E.md`** — Complete testing guide with 10 test suites
- **`docs/DISTRIBUTED.md`** — Distributed architecture explanation
- **`docs/FRONTEND_REVIEW.md`** — Frontend code review
- **`backend/scripts/README_SIMULATOR.md`** — Simulator documentation

---

**Ready to test? Start with Step 1 above! 🚀**
