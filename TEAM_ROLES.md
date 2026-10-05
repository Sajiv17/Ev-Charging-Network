# Team Roles & Folder Ownership

Quick reference for who works where.

---

## Person 1 — Database Architect

**Branch:** `database-schema`

**Folders you own:**
```
database/
├── mysql/
│   ├── schema/        ← Review + refine existing schema
│   ├── triggers/      ← Add more triggers (already has 1 example)
│   ├── procedures/    ← CREATE stored procedures (empty, you build)
│   └── seeds/         ← CREATE seed data (empty, you build)
```

**You also create:**
- `docs/ER_DIAGRAM.md` — ER diagram
- `docs/NORMALIZATION.md` — Show 1NF → BCNF steps

**Read:** [database/README.md](database/README.md)

---

## Person 2 — Backend + Transactions

**Branch:** `backend-api`

**Folders you own:**
```
backend/
├── app/
│   ├── api/           ← CREATE REST endpoints (empty, you build)
│   ├── models/        ← CREATE SQLAlchemy models (empty, you build)
│   ├── schemas/       ← CREATE Pydantic schemas (empty, you build)
│   └── services/      ← CREATE booking logic with 2PL (empty, you build)
```

**Key deliverable:**
- `services/booking_service.py` — **Booking with 2-Phase Locking**

**You also create:**
- `docs/CONCURRENCY.md` — Explain 2PL implementation
- `docs/RECOVERY_DEMO.md` — Recovery scenario walkthrough

**Read:** [backend/README.md](backend/README.md)

---

## Person 3 — Distributed + NoSQL

**Branch:** `distributed-nosql`

**Folders you own:**
```
database/
└── mongodb/
    ├── schemas/       ← CREATE schema docs (empty, you build)
    └── seeds/         ← CREATE seed data (empty, you build)

backend/
├── scripts/           ← CREATE MongoDB seed + status simulator (empty, you build)
└── app/services/
    └── mongodb_service.py  ← CREATE MongoDB read/write functions (you add)

docker/                ← Add custom configs if needed (currently empty)
```

**Key deliverable:**
- `scripts/simulate_realtime_status.py` — Real-time charger telemetry simulation

**You also create:**
- `docs/DISTRIBUTED.md` — Explain 3-node setup + fragmentation

**Read:** [docker/README.md](docker/README.md)

---

## Person 4 — Frontend

**Branch:** `frontend-ui`

**Folders you own:**
```
frontend/
└── src/
    ├── components/    ← CREATE reusable UI (empty, you build)
    ├── pages/         ← CREATE route pages (empty, you build)
    ├── services/      ← CREATE API client (empty, you build)
    └── utils/         ← CREATE helpers (empty, you build)
```

**Key deliverable:**
- `pages/Dashboard.js` — Live station dashboard (polls MongoDB every 5s)
- `pages/BookingFlow.js` — Multi-step booking form

**Read:** [frontend/README.md](frontend/README.md)

---

## Shared Responsibility

**Nobody owns these, coordinate together:**
- `docker-compose.yml` — already set up, but if you need to add services, discuss first
- `.env` files — if you need environment variables, add them and document in README
- `docs/API.md` — Person 2 should document the API, Person 4 uses it

---

## Git Workflow Reminder

```bash
# 1. Clone (everyone does this once)
git clone https://github.com/Sajiv17/Ev-Charging-Network.git
cd Ev-Charging-Network

# 2. Create your branch
git checkout -b <your-branch-name>

# 3. Work on your part
# ... make changes ...

# 4. Commit + push
git add <your-folders>
git commit -m "feat(<area>): what you did"
git push origin <your-branch-name>

# 5. Open PR on GitHub
# Go to repo → Pull Requests → New PR
# Select your branch → main
# Request review from one teammate
```

---

## Testing Before PR

**Everyone should test their work locally:**

```bash
# Start all services
docker-compose up --build

# Check logs
docker logs -f ev-backend       # Backend
docker logs -f ev-mysql-bangalore  # MySQL
docker logs -f ev-mongodb       # MongoDB
docker logs -f ev-frontend      # Frontend
```

**Access points:**
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

---

## Questions?

- Open an issue on GitHub
- Tag the relevant person
- Use team chat for quick questions

---

**Now everyone knows exactly what to build. Let's get started!**
