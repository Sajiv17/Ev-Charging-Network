# Distributed Database Architecture

**EV Charging Network — Person 3 Documentation**

This document explains the distributed database setup: how 3 MySQL city nodes work together,
how data is fragmented and replicated, and why MongoDB handles real-time data separately.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    Application Layer (FastAPI)                  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Booking Coordinator (backend/app/services/xa.py)        │  │
│  │  - Routes queries to the right city node                 │  │
│  │  - Handles cross-city bookings (XA transactions)         │  │
│  │  - Manages distributed commits/rollbacks                 │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                                 │
                 ┌───────────────┼───────────────┐
                 │               │               │
                 ▼               ▼               ▼
        ┌────────────┐  ┌────────────┐  ┌────────────┐
        │ MySQL Node │  │ MySQL Node │  │ MySQL Node │
        │ Bangalore  │  │  Chennai   │  │   Delhi    │
        │  :3306     │  │   :3307    │  │   :3308    │
        └────────────┘  └────────────┘  └────────────┘
             │                │                │
             └────────────────┼────────────────┘
                              │
                              ▼
                      ┌────────────────┐
                      │    MongoDB     │
                      │   :27017       │
                      │  (Real-time)   │
                      └────────────────┘
```

---

## Data Fragmentation Strategy

### Horizontal Fragmentation (Partitioned by City)

Each MySQL node stores **only its own city's data**. A booking in Bangalore lives only on
the Bangalore node; Chennai's bookings stay in Chennai.

**Fragmented Tables** (each node has different rows):
- `stations` — only this city's stations
- `charger_units` — only this city's chargers
- `slots` — only slots for this city's chargers
- `bookings` — only bookings made at this city's stations
- `payments` — only payments for this city's bookings
- `refunds` — only refunds from this city's bookings
- `corridor_stations` — only entries where this station is local
- `operator_alerts` — only alerts for this city's operators

**Why fragment?**
- **Scalability**: Each city handles its own load independently
- **Locality**: Queries for Bangalore data don't hit Chennai's database
- **Fault tolerance**: If Chennai node goes down, Bangalore keeps working
- **Realistic**: This mirrors how real distributed networks are deployed (regional data centers)

---

### Replication (Identical on All Nodes)

**Replicated Tables** (same data on every node):
- `cities` — catalog of all cities in the network
- `connector_types` — CCS2, CHAdeMO, Type2
- `pricing_plans` — pricing rules per city (all nodes have all cities' plans)
- `corridors` — highway routes connecting cities
- `users` — all user accounts (drivers, operators, admins)
- `vehicles` — all vehicles (linked to users)

**Why replicate?**
- **Fast lookups**: Every node can answer "what's the rate in Chennai?" without cross-node query
- **Join efficiency**: Local joins between bookings and users don't need network calls
- **CAP theorem**: We choose **Availability** and **Partition tolerance** over strong **Consistency**
  - Pricing plans change rarely (admin updates them manually)
  - User registration happens on one node, then replicates (eventual consistency is acceptable)

---

## How Queries Are Routed

### Local Queries (Single City)

**Example:** Driver in Bangalore searches for Bangalore stations.

```python
# Backend routes this to Bangalore node only
city = "bangalore"
db = get_city_session(city)  # Opens connection to mysql-bangalore:3306

stations = db.execute("""
    SELECT * FROM stations WHERE city_id = (SELECT city_id FROM cities WHERE city_name = 'Bangalore')
""").fetchall()
```

**Result:** Fast, no cross-node communication needed.

---

### Cross-City Queries

**Example:** Driver in Bangalore searches for Chennai stations (planning a road trip).

```python
# Backend routes this to Chennai node
city = "chennai"
db = get_city_session(city)  # Opens connection to mysql-chennai:3307

stations = db.execute("""
    SELECT * FROM stations WHERE city_id = (SELECT city_id FROM cities WHERE city_name = 'Chennai')
""").fetchall()
```

**Result:** Still fast — the coordinator knows which city to query.

---

### Cross-City Bookings (Distributed Transactions)

**Example:** Driver from Bangalore books a Chennai station.

This is the **hard case** — money is debited from Bangalore (user's home city), but the
booking happens in Chennai (station's city).

**Without XA (2-Phase Commit):**
1. Debit wallet on Bangalore node ✅
2. Network failure ❌
3. Chennai booking never created
4. Money is gone, no booking exists → **INCONSISTENT**

**With XA (2-Phase Commit):**

```python
# Phase 1: PREPARE
bangalore_db.execute("XA START 'global_tx_123'")
bangalore_db.execute("UPDATE users SET wallet_balance = wallet_balance - 100 WHERE user_id = 10")
bangalore_db.execute("XA END 'global_tx_123'")
bangalore_db.execute("XA PREPARE 'global_tx_123'")  # ✅ Ready to commit

chennai_db.execute("XA START 'global_tx_123'")
chennai_db.execute("INSERT INTO bookings (...) VALUES (...)")
chennai_db.execute("XA END 'global_tx_123'")
chennai_db.execute("XA PREPARE 'global_tx_123'")  # ✅ Ready to commit

# Phase 2: COMMIT (if both prepared successfully)
bangalore_db.execute("XA COMMIT 'global_tx_123'")  # ✅
chennai_db.execute("XA COMMIT 'global_tx_123'")    # ✅
```

**If any PREPARE fails:** Both nodes rollback.

**Coordinator implementation:** `backend/app/services/xa.py` (515 lines)

---

## MongoDB's Role (Real-Time Data)

MongoDB is **NOT fragmented** — it's a single shared database across all cities.

**Why separate from MySQL?**

| Data Type | MySQL | MongoDB |
|-----------|-------|---------|
| **Transactional** (bookings, payments) | ✅ ACID required | ❌ Overkill |
| **Real-time telemetry** (power draw, status) | ❌ Too rigid | ✅ Schema-less |
| **Audit logs** (transaction events) | ❌ High write volume | ✅ Optimized for writes |
| **Fault reports** (photos, descriptions) | ❌ Unstructured | ✅ Flexible documents |

**MongoDB Collections:**
- `charger_status` — live status of all chargers (updated every 5s by simulator)
- `charging_sessions` — session logs with energy consumption
- `fault_reports` — operator fault reports with photos
- `audit_log` — transaction event logging for concurrency demo

**Integration:**
- Backend writes session start/end to MongoDB
- Frontend polls MongoDB for live charger status every 5-10s
- Simulator continuously updates MongoDB to simulate real-time telemetry

---

## CAP Theorem Trade-offs

The **CAP theorem** states you can have at most 2 of:
- **Consistency** — all nodes see the same data at the same time
- **Availability** — every request gets a response (even if stale)
- **Partition tolerance** — system works even if nodes can't talk to each other

**Our choice: AP (Availability + Partition tolerance)**

### What This Means

**Scenario:** Network partition separates Bangalore node from Chennai node.

**Result:**
- ✅ Bangalore drivers can still book Bangalore stations (local transactions work)
- ✅ Chennai drivers can still book Chennai stations (local transactions work)
- ❌ Cross-city bookings fail (coordinator can't reach both nodes)

**After partition heals:**
- No data loss (each node committed its own transactions)
- Cross-city bookings resume immediately

### Why Not CP (Consistency + Partition tolerance)?

If we chose **strong consistency**:
- During a partition, the system would **refuse all writes** until partition heals
- A Bangalore network outage would block **all** bookings everywhere
- Not acceptable for a real-world booking system

### Eventual Consistency

**User registration:**
1. User registers in Bangalore → record written to Bangalore node
2. Replication script copies user to Chennai and Delhi nodes (happens in background, ~1-5 seconds)
3. For those few seconds, Chennai doesn't know about this user
4. Eventually, all nodes have the same user data

**This is acceptable because:**
- Users don't immediately book in another city after registering
- By the time they do, replication has caught up
- If it hasn't, the booking coordinator can fetch user data from their home city

---

## Replication (How It Works)

**Current implementation:** Manual replication via seed scripts

All nodes run the same seed files:
- `database/mysql/seeds/common/` — loaded on all 3 nodes (users, pricing, corridors)
- `database/mysql/seeds/<city>/` — loaded only on that node (stations, bookings)

**Production-grade replication** (not implemented in this project):
- MySQL's built-in replication (master-slave)
- Galera Cluster (multi-master)
- Application-level replication triggers

**Why we don't need it for this project:**
- Seed data is static (loaded once at startup)
- New users are rare in the demo (operators manually add them if needed)
- Focus is on demonstrating **fragmentation** and **distributed transactions**, not replication complexity

---

## Data Placement Example

**User 10** lives in Bangalore (`home_city_id = 1`).

| Table | Bangalore Node | Chennai Node | Delhi Node |
|-------|----------------|--------------|------------|
| `users` (user 10) | ✅ Full record | ✅ Full record | ✅ Full record |
| `vehicles` (user 10's car) | ✅ Full record | ✅ Full record | ✅ Full record |
| `wallet_balance` (user 10) | ✅ **Authoritative** (₹5000) | ⚠️ Stale copy (₹5000) | ⚠️ Stale copy (₹5000) |
| `bookings` (user 10 in BLR) | ✅ Here | ❌ Not here | ❌ Not here |
| `bookings` (user 10 in CHN) | ❌ Not here | ✅ Here | ❌ Not here |

**Wallet handling:**
- User 10's wallet lives on **Bangalore node** (their home city)
- When user 10 books a Chennai station:
  1. Coordinator debits wallet on **Bangalore** (authoritative copy)
  2. Coordinator creates booking on **Chennai** (station's city)
  3. XA transaction ensures both happen or neither happens

**Why replicate users if wallet is authoritative on one node?**
- **Fast joins**: Chennai node can `JOIN bookings b ON b.user_id = u.user_id` locally
- **User info**: Chennai node can show user's name/email without cross-node query
- **Wallet reads**: Only **debits** go to home node; **reading** balance happens locally

---

## Testing Distributed Setup

### 1. Verify All Nodes Are Running

```bash
docker ps | grep mysql
# Should show:
#   ev-mysql-bangalore   :3306
#   ev-mysql-chennai     :3307
#   ev-mysql-delhi       :3308
```

### 2. Check Data Fragmentation

```bash
# Bangalore node: how many stations?
docker exec ev-mysql-bangalore mysql -u ev_user -pevcharge_pass_2024 -e \
  "SELECT COUNT(*) FROM ev_bangalore.stations"

# Chennai node: how many stations?
docker exec ev-mysql-chennai mysql -u ev_user -pevcharge_pass_2024 -e \
  "SELECT COUNT(*) FROM ev_chennai.stations"

# Should be different counts (each city has different number of stations)
```

### 3. Check Replication

```bash
# Users should be identical on all nodes
docker exec ev-mysql-bangalore mysql -u ev_user -pevcharge_pass_2024 -e \
  "SELECT COUNT(*) FROM ev_bangalore.users"

docker exec ev-mysql-chennai mysql -u ev_user -pevcharge_pass_2024 -e \
  "SELECT COUNT(*) FROM ev_chennai.users"

# Should be the same count (users are replicated)
```

### 4. Test Cross-City Booking

```bash
# Use backend API to book a Chennai station from Bangalore user
curl -X POST http://localhost:8000/api/bookings \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 10,
    "slot_id": 100,
    "vehicle_id": 1,
    "from_city": "bangalore",
    "to_city": "chennai"
  }'

# Check logs for XA transaction
docker logs ev-backend | grep "XA PREPARE"
```

---

## Failure Scenarios

### Scenario 1: One Node Goes Down

**What happens:**
```bash
# Simulate Chennai node failure
docker stop ev-mysql-chennai
```

**Result:**
- ✅ Bangalore and Delhi bookings continue working
- ❌ Chennai bookings fail (503 Service Unavailable)
- ❌ Cross-city bookings involving Chennai fail

**Recovery:**
```bash
docker start ev-mysql-chennai
# System immediately resumes normal operation
```

---

### Scenario 2: Network Partition

**Simulated by:** Firewall rules blocking traffic between nodes

**Result (with our AP design):**
- Each city continues processing **local** bookings
- Cross-city bookings are rejected with clear error message
- No data corruption (each node's local transactions are ACID-compliant)

**After partition heals:**
- All committed local transactions remain valid
- Cross-city bookings resume

---

### Scenario 3: Coordinator Crashes Mid-Transaction

**What happens:**
1. Coordinator sends XA PREPARE to both nodes ✅
2. Both nodes are in "prepared" state (locked, waiting for commit)
3. Coordinator crashes before sending XA COMMIT ❌

**Recovery (automatic):**
```python
# On coordinator restart, it runs XA RECOVER on all nodes
bangalore_db.execute("XA RECOVER")
# Returns: 'global_tx_123' in PREPARED state

# Coordinator commits or rolls back based on its transaction log
bangalore_db.execute("XA COMMIT 'global_tx_123'")
chennai_db.execute("XA COMMIT 'global_tx_123'")
```

**Implementation:** `backend/app/services/recovery_service.py`

---

## Monitoring Distributed Health

**Backend provides endpoints:**

```bash
# Check all city nodes
curl http://localhost:8000/api/operations/node-health
```

**Returns:**
```json
{
  "bangalore": {"status": "healthy", "latency_ms": 12},
  "chennai": {"status": "healthy", "latency_ms": 15},
  "delhi": {"status": "healthy", "latency_ms": 18},
  "mongodb": {"status": "healthy", "latency_ms": 8}
}
```

---

## Performance Characteristics

### Local Booking (Same City)

- **Query latency:** ~10-20ms
- **Network hops:** 0 (all data on one node)
- **Lock contention:** Only local (no distributed locks)

### Cross-City Booking (XA Transaction)

- **Query latency:** ~50-100ms
- **Network hops:** 2 (coordinator → both nodes)
- **Lock contention:** Higher (2 nodes must coordinate)
- **Failure probability:** Higher (both nodes + network must work)

**Trade-off:** Cross-city bookings are slower but necessary for road trips.

---

## Summary

| Aspect | Design Choice | Reason |
|--------|---------------|--------|
| **Fragmentation** | Horizontal by city | Scalability + fault tolerance |
| **Replication** | Catalog tables + users | Fast joins + cross-city queries |
| **CAP** | AP (Availability + Partition tolerance) | Real-world booking systems must stay available |
| **Cross-city tx** | XA 2-Phase Commit | Ensures ACID across nodes |
| **MongoDB** | Separate, shared | Real-time data doesn't need fragmentation |
| **Failure mode** | Local operations continue | City outage doesn't affect other cities |

---

**This architecture demonstrates:**
- ✅ Horizontal fragmentation (Module 5: Distributed DB)
- ✅ Data replication strategies (Module 5)
- ✅ CAP theorem trade-offs (Module 5: NoSQL)
- ✅ Distributed transaction coordination (Module 4 + 5)
- ✅ Failure handling and recovery (Module 4)
- ✅ Polyglot persistence (SQL + NoSQL) (Module 5)

---

**Implementation files:**
- `backend/app/services/xa.py` — XA transaction coordinator
- `backend/app/services/cross_city.py` — Cross-city query routing
- `backend/app/services/recovery_service.py` — XA recovery after crash
- `backend/app/services/replication.py` — Replication helpers
- `backend/app/db/mysql_connection.py` — Multi-node connection management
