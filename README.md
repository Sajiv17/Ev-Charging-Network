# EV Charging Network

> **Multi-city EV charging station booking platform with distributed database architecture**  
> BACSE202 Database Systems · Semester Project · VIT

---

## 🚀 Quick Start

```bash
# Clone the repo
git clone https://github.com/YOUR_USERNAME/ev-charging-network.git
cd ev-charging-network

# Start all services (MySQL nodes, MongoDB, Backend, Frontend)
docker-compose up --build

# Access the application
# Frontend: http://localhost:3000
# Backend API: http://localhost:8000
# API Docs: http://localhost:8000/docs
```

---

## 📦 What This Is

A full-stack booking system for a network of EV charging stations across **Bangalore, Chennai, and Delhi**. Drivers can search for stations, book time slots, and pay — all backed by:

- **Distributed MySQL** (3 city nodes with horizontal fragmentation)
- **MongoDB** (real-time charger status and session logs)
- **Python FastAPI** backend with 2-Phase Locking for concurrency control
- **React** frontend with live dashboard

Real-world equivalent: Tata Power EZ Charge, ChargePoint, EVGO.

---

## 🏗️ Project Structure

```
ev-charging-network/
├── backend/                 # Python FastAPI backend
│   ├── app/
│   │   ├── api/            # REST endpoints
│   │   ├── core/           # Config, security, dependencies
│   │   ├── db/             # Database connections (MySQL + MongoDB)
│   │   ├── models/         # SQLAlchemy models
│   │   ├── schemas/        # Pydantic schemas (request/response)
│   │   └── services/       # Business logic (booking, payments, concurrency)
│   ├── scripts/            # Utility scripts
│   ├── requirements.txt
│   └── Dockerfile
│
├── frontend/                # React frontend
│   ├── src/
│   │   ├── components/     # Reusable UI components
│   │   ├── pages/          # Route pages (Home, Booking, Dashboard, Admin)
│   │   ├── services/       # API client
│   │   ├── utils/          # Helpers
│   │   └── assets/         # Images, icons
│   ├── package.json
│   └── Dockerfile
│
├── database/                # Database schemas and scripts
│   ├── mysql/
│   │   ├── schema/         # DDL scripts (CREATE TABLE)
│   │   ├── procedures/     # Stored procedures
│   │   ├── triggers/       # Triggers (fault handling, refunds)
│   │   └── seeds/          # Sample data
│   └── mongodb/
│       ├── schemas/        # MongoDB schemas (Mongoose-style docs)
│       └── seeds/          # Sample data
│
├── docker/                  # Docker configs for each service
├── docs/                    # Documentation
│   ├── ER_DIAGRAM.md
│   ├── API.md
│   ├── CONCURRENCY.md
│   └── RECOVERY_DEMO.md
│
├── docker-compose.yml       # Orchestrates all services
├── .gitignore
└── README.md
```

---

## 👥 Team & Work Split

| Person | Role | Responsibility |
|--------|------|----------------|
| **Person 1** | Database Architect | MySQL schema, normalization (1NF→BCNF), stored procedures, triggers, indexes. Owns ER/EER diagram and all DDL. |
| **Person 2** | Backend + Transactions | FastAPI endpoints, booking logic with 2PL, deadlock demo, payment flow, recovery scenario code. |
| **Person 3** | Distributed + NoSQL | MongoDB integration, real-time status simulation, Docker setup for 3 MySQL nodes, cross-city routing, replication. |
| **Person 4** | Frontend | React booking UI, live dashboard, operator/admin panels. API integration. Owns demo walkthrough. |

---

## 🛠️ Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| **Relational DB** | MySQL (×3 Docker containers) | Core transactional data. 3 instances = 3 city nodes. |
| **NoSQL** | MongoDB | Real-time charger telemetry, session logs, fault reports. |
| **Backend** | Python · FastAPI | Async support, SQLAlchemy ORM, clean REST API. |
| **Frontend** | React | Live dashboard with polling, multi-step booking form. |
| **Infrastructure** | Docker Compose | One command starts all services. Simulates distributed deployment locally. |

---

## 🗄️ Database Split

### MySQL (Relational + Transactional)
- Users, Vehicles, Stations, ChargerUnits, Slots, Bookings, Payments, PricingPlans

### MongoDB (Real-time + Unstructured)
- ChargerStatus (live telemetry)
- ChargingSessions (open session logs)
- FaultReports (operator-submitted issues)
- AuditLog (transaction events for demo)

---

## 🔒 Key Features We're Demonstrating

### 1. Concurrency Control (2-Phase Locking)
Two drivers booking the same slot simultaneously → one gets the lock, the other waits. No double-booking ever.

**Demo:** Fire two simultaneous requests from browser dev console, show MySQL transaction log in real time.

### 2. Distributed Database
- 3 MySQL city nodes (Bangalore, Chennai, Delhi)
- Horizontal fragmentation: each node only stores its city's data
- Global catalog replicated across all nodes
- Cross-city booking = distributed transaction

**Demo:** Book a Chennai station from Bangalore UI, show cross-node query routing.

### 3. Recovery Scenario
Node crashes mid-transaction (after payment, before booking write). WAL-based deferred update recovery rolls it back cleanly.

**Demo:** Force-kill Docker container mid-booking, bring it back up, show rollback in logs.

### 4. Triggers
Charger fault mid-session → trigger fires → booking cancelled → refund queued → operator alerted.

**Demo:** Manually set charger status to "faulted", show trigger chain in MySQL log.

---

## 📚 Setup Instructions

### Prerequisites
- **Docker** & **Docker Compose** (latest)
- **Node.js** 18+ (for local frontend dev)
- **Python** 3.10+ (for local backend dev)

### First Time Setup

1. **Clone the repo**
   ```bash
   git clone https://github.com/YOUR_USERNAME/ev-charging-network.git
   cd ev-charging-network
   ```

2. **Start all services**
   ```bash
   docker-compose up --build
   ```
   This starts:
   - MySQL node: Bangalore (port 3306)
   - MySQL node: Chennai (port 3307)
   - MySQL node: Delhi (port 3308)
   - MongoDB (port 27017)
   - Backend API (port 8000)
   - Frontend (port 3000)

3. **Load sample data**
   ```bash
   # Run seed scripts (from another terminal while containers are up)
   docker exec ev-backend python scripts/seed_mysql.py
   docker exec ev-backend python scripts/seed_mongodb.py
   ```

4. **Access the app**
   - Frontend: http://localhost:3000
   - Backend API docs: http://localhost:8000/docs
   - MongoDB Express (optional): http://localhost:8081

---

## 🧪 Running the Demos

### Concurrency Demo (Double-Booking Prevention)
```bash
# Open browser dev console at http://localhost:3000
# Paste this to fire two simultaneous booking requests:

Promise.all([
  fetch('http://localhost:8000/bookings', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({user_id: 1, slot_id: 42})
  }),
  fetch('http://localhost:8000/bookings', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({user_id: 2, slot_id: 42})
  })
]).then(r => console.log(r))

# Watch backend logs: docker logs -f ev-backend
# You'll see one transaction acquire lock, the other wait, then fail.
```

### Recovery Demo (Node Crash Mid-Transaction)
```bash
# Start a booking request (Postman or curl)
curl -X POST http://localhost:8000/bookings \
  -H "Content-Type: application/json" \
  -d '{"user_id": 1, "slot_id": 50}'

# While it's processing, kill the Bangalore MySQL node
docker kill ev-mysql-bangalore

# Bring it back
docker start ev-mysql-bangalore

# Check the WAL and booking status
docker exec ev-mysql-bangalore mysql -u root -ppassword \
  -e "SELECT * FROM ev_bangalore.bookings WHERE slot_id=50;"
# Booking should be rolled back (not present)
```

### Trigger Demo (Charger Fault → Auto Refund)
```bash
# Manually set a charger to faulted
docker exec ev-mysql-bangalore mysql -u root -ppassword \
  -e "UPDATE ev_bangalore.charger_units SET status='faulted' WHERE id=5;"

# The trigger should:
# 1. Cancel active booking on that charger
# 2. Queue refund
# 3. Log fault event

# Verify trigger fired
docker exec ev-mysql-bangalore mysql -u root -ppassword \
  -e "SELECT * FROM ev_bangalore.refunds ORDER BY created_at DESC LIMIT 5;"
```

---

## 📖 Documentation

- [ER Diagram & Schema Design](docs/ER_DIAGRAM.md)
- [API Reference](docs/API.md)
- [Concurrency Control Deep Dive](docs/CONCURRENCY.md)
- [Recovery Scenario Walkthrough](docs/RECOVERY_DEMO.md)

---

## 🤝 Contributing

Each team member has their own branch:
- `database-schema` (Person 1)
- `backend-api` (Person 2)
- `distributed-nosql` (Person 3)
- `frontend-ui` (Person 4)

**Workflow:**
1. Create your feature branch from `main`
2. Work on your part
3. Open a PR to `main` when ready
4. Get one other person to review
5. Merge

**Commit messages:** Use conventional commits
```
feat(backend): add booking endpoint with 2PL
fix(database): correct foreign key constraint on payments
docs(readme): add recovery demo instructions
```

---

## 📝 License

MIT License · Educational project for BACSE202 Database Systems course.

---

## 🎯 Project Goals (What We're Proving)

✅ ER/EER modeling + normalization to BCNF  
✅ Concurrency control (2PL, deadlock handling)  
✅ Recovery mechanisms (WAL, deferred update)  
✅ Distributed DB (horizontal fragmentation, replication)  
✅ SQL + NoSQL hybrid (right tool for the right job)  
✅ Triggers, stored procedures, indexing (B+ trees)  
✅ Full-stack integration (DB → API → UI)

---

**Questions?** Open an issue or contact the team.
