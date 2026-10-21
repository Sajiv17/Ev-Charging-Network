# ⚡ Quick Start (5 Minutes)

**Fastest way to run the EV Charging Network project.**

---

## Prerequisites

✅ Docker Desktop (installed and running)  
✅ Node.js 18+ installed  
✅ Git installed

---

## Installation (Copy-paste these commands)

```bash
# 1. Clone the project
git clone https://github.com/Sajiv17/Ev-Charging-Network.git
cd Ev-Charging-Network

# 2. Start Docker containers (wait 1-2 minutes)
docker compose up -d

# 3. Seed MongoDB
docker exec ev-backend python scripts/quick_seed.py

# 4. Start simulator
docker exec -d ev-backend python scripts/simulate_realtime_status.py

# 5. Test backend
curl http://localhost:8000/health
# Should return: {"status":"healthy","mysql_nodes":{...}}

# 6. Start frontend (OPEN NEW TERMINAL for this)
cd frontend
npm install
npm start
```

**Browser opens at http://localhost:3000** 🎉

---

## Demo the Project

1. **Go to:** http://localhost:3000/dashboard
2. **Select:** Bangalore → Any station
3. **Watch:** Timestamp updates every 5 seconds ⏱️

**This proves real-time integration is working!** ✅

---

## Stop Everything

```bash
# Stop frontend: Ctrl+C in that terminal

# Stop Docker:
docker compose down
```

---

## Troubleshooting

**Backend not working?**
```bash
docker logs ev-backend
```

**Frontend shows yellow banner?**
- Backend not running. Run `docker compose up -d`

**Need detailed help?**
- See `SETUP_FOR_TEAMMATES.md` for full guide

---

**That's it! 🚀**
