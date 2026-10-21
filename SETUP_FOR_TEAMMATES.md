# 🚀 EV Charging Network - Setup Guide for Teammates

**Simple step-by-step guide to install and run the project on your computer.**

---

## 📋 Prerequisites (Install These First)

Before starting, make sure you have:

### 1. **Docker Desktop**
- Download: https://www.docker.com/products/docker-desktop
- Install and **start Docker Desktop**
- Verify: Open terminal and run `docker --version`
- You should see something like: `Docker version 24.x.x`

### 2. **Node.js** (Version 18 or higher)
- Download: https://nodejs.org (get the LTS version)
- Install it
- Verify: `node --version` should show `v18.x.x` or higher
- Verify: `npm --version` should show `9.x.x` or higher

### 3. **Git**
- Download: https://git-scm.com/downloads
- Install it
- Verify: `git --version`

---

## 📥 Step 1: Clone the Project

Open **Terminal** (Mac) or **Command Prompt** (Windows) and run:

```bash
git clone https://github.com/Sajiv17/Ev-Charging-Network.git
cd Ev-Charging-Network
```

---

## 🐳 Step 2: Start Docker Containers

**Make sure Docker Desktop is running!** (You should see the Docker icon in your menu bar/system tray)

Run this command:

```bash
docker compose up -d
```

**Wait 1-2 minutes** for containers to start.

**What this does:**
- Starts 3 MySQL databases (Bangalore, Chennai, Delhi)
- Starts MongoDB database
- Starts Python backend API

---

## ✅ Step 3: Verify Containers Are Running

Run:

```bash
docker ps
```

**You should see 5 containers:**
- `ev-mysql-bangalore`
- `ev-mysql-chennai`
- `ev-mysql-delhi`
- `ev-mongodb`
- `ev-backend`

**If you see fewer containers:**
- Wait 30 more seconds and run `docker ps` again
- Or run `docker compose logs` to see what went wrong

---

## 🗄️ Step 4: Seed MongoDB with Sample Data

Run this command:

```bash
docker exec ev-backend python scripts/quick_seed.py
```

**Expected output:**
```
Seeding MongoDB...
✓ 27 chargers
✓ 1 session
✅ Done!
```

---

## 🔄 Step 5: Start Real-Time Simulator

Run:

```bash
docker exec -d ev-backend python scripts/simulate_realtime_status.py
```

**What this does:**
- Updates charger status every 5 seconds
- Simulates real-time power draw and energy consumption

---

## 🧪 Step 6: Test Backend API

Run:

```bash
curl http://localhost:8000/health
```

**Expected output:**
```json
{"status":"healthy","mysql_nodes":{"bangalore":"up","chennai":"up","delhi":"up"}}
```

✅ **If you see this, backend is working!**

❌ **If you get "connection refused":**
- Wait 30 seconds and try again
- Or run `docker logs ev-backend` to see errors

---

## 💻 Step 7: Start Frontend

**Open a NEW terminal window** and run:

```bash
cd Ev-Charging-Network/frontend
npm install
npm start
```

**First time will take 2-3 minutes to install packages.**

**You'll see:**
```
Starting the development server...
...
Compiled successfully!

You can now view ev-charging-frontend in the browser.

  Local:            http://localhost:3000
```

**Browser will automatically open to http://localhost:3000**

---

## 🎯 Step 8: Test the Application

### **Home Page**
- You should see "⚡ EV Charging Network"
- Navigation menu at top
- **NO yellow banner** (if you see yellow banner, backend is not connected)

### **Find Stations**
1. Click **"Find Stations"** in menu
2. Select **Bangalore** from dropdown
3. You'll see list of charging stations

### **Operator Dashboard** (MAIN DEMO)
1. Click **"Operator Dashboard"** in menu
2. Select **Bangalore** city
3. Select any station from dropdown
4. **You'll see:**
   - Grid of chargers with color-coded status badges
   - Green = Available, Yellow = Occupied, Red = Faulted
   - "Updated at HH:MM:SS" timestamp
   - **Watch the timestamp - it updates every 5 seconds!**
   - This proves real-time integration is working ✅

### **Book a Slot**
1. Go to "Find Stations"
2. Click on any station
3. Click "Book Now"
4. Follow 3-step wizard:
   - Step 1: Pick charger and time slot
   - Step 2: Confirm details
   - Step 3: Pay (demo wallet)
5. You'll see "Booking confirmed ✅"

### **My Bookings**
1. Click "My Bookings" in menu
2. See your booking listed
3. Try clicking "Cancel"

---

## 🎬 Demo Script (For Presentation)

**Show these 3 things to demonstrate the full system:**

### 1️⃣ **Distributed Database** (30 seconds)
```bash
# Show Bangalore has different data than Chennai
docker exec ev-mysql-bangalore mysql -u ev_user -pevcharge_pass_2024 -e "SELECT COUNT(*) FROM ev_bangalore.stations"
docker exec ev-mysql-chennai mysql -u ev_user -pevcharge_pass_2024 -e "SELECT COUNT(*) FROM ev_chennai.stations"
```
**Different counts = data is fragmented by city ✅**

### 2️⃣ **Real-Time Dashboard** (2 minutes)
- Open http://localhost:3000/dashboard
- Select Bangalore → Pick a station
- **Point to screen:** "Watch the timestamp update every 5 seconds"
- Show charger status badges changing
- **This demonstrates MongoDB real-time integration ✅**

### 3️⃣ **Booking Flow** (1 minute)
- Book a slot end-to-end
- Show it creates booking in database
- Show cross-city booking (XA transactions)

---

## 🛑 How to Stop Everything

### Stop Frontend
In the terminal running frontend, press: **Ctrl+C**

### Stop Docker Containers
```bash
docker compose down
```

---

## 🔄 How to Restart Later

```bash
# 1. Start Docker containers
docker compose up -d

# 2. Start simulator (if needed)
docker exec -d ev-backend python scripts/simulate_realtime_status.py

# 3. Start frontend (in new terminal)
cd frontend
npm start
```

---

## 🐛 Troubleshooting

### **Problem: Port 3306 already in use**

**Solution:**
```bash
# Stop local MySQL if you have one
brew services stop mysql
# OR
sudo /usr/local/mysql/support-files/mysql.server stop
```

---

### **Problem: Frontend shows yellow banner "Backend API not reachable"**

**Check backend is running:**
```bash
curl http://localhost:8000/health
```

**If this fails:**
```bash
# Restart backend
docker restart ev-backend

# Check logs for errors
docker logs ev-backend
```

---

### **Problem: "docker: command not found"**

**Solution:** 
- Make sure Docker Desktop is installed and running
- You should see Docker icon in menu bar (Mac) or system tray (Windows)

---

### **Problem: Frontend won't start or shows errors**

**Solution 1: Clear npm cache**
```bash
cd frontend
rm -rf node_modules package-lock.json
npm install
npm start
```

**Solution 2: Use different port**
```bash
PORT=3001 npm start
# Then open http://localhost:3001
```

---

### **Problem: MongoDB has no data**

**Re-seed it:**
```bash
docker exec ev-backend python scripts/quick_seed.py
```

---

### **Problem: Simulator not updating**

**Restart simulator:**
```bash
# Stop any existing simulator
docker exec ev-backend pkill -f simulate_realtime_status.py

# Start new one
docker exec -d ev-backend python scripts/simulate_realtime_status.py
```

---

## 📊 What's Running on Your Computer?

```
✅ Backend API:           http://localhost:8000
✅ Frontend:              http://localhost:3000
✅ MySQL Bangalore:       localhost:3309
✅ MySQL Chennai:         localhost:3307
✅ MySQL Delhi:           localhost:3308
✅ MongoDB:               localhost:27017
```

---

## 🎓 Project Architecture

```
┌─────────────────────────────────────────┐
│         React Frontend (Port 3000)       │
│         - Station search                 │
│         - Booking flow                   │
│         - Live dashboard                 │
└─────────────────┬───────────────────────┘
                  │ HTTP API calls
                  ▼
┌─────────────────────────────────────────┐
│      Python Backend (Port 8000)          │
│      - FastAPI REST endpoints            │
│      - XA transaction coordinator        │
│      - Real-time data aggregation        │
└───────┬─────────┬──────────┬────────────┘
        │         │          │
        ▼         ▼          ▼
   ┌────────┐ ┌────────┐ ┌────────┐
   │ MySQL  │ │ MySQL  │ │ MySQL  │
   │Bangalore│ │Chennai │ │ Delhi  │
   │ :3309  │ │ :3307  │ │ :3308  │
   └────────┘ └────────┘ └────────┘
        │         │          │
        └─────────┼──────────┘
                  │ Charger data
                  ▼
            ┌──────────┐
            │ MongoDB  │
            │  :27017  │
            │Real-time │
            └──────────┘
                  ▲
                  │ Updates every 5s
            ┌──────────┐
            │Simulator │
            └──────────┘
```

---

## 📚 Additional Documentation

- **Full testing guide:** `TESTING_QUICK_START.md`
- **Distributed architecture:** `docs/DISTRIBUTED.md`
- **Frontend review:** `docs/FRONTEND_REVIEW.md`
- **End-to-end testing:** `docs/TESTING_E2E.md`

---

## ✅ Quick Verification Checklist

Before demo, verify:
- [ ] `docker ps` shows 5 containers running
- [ ] `curl http://localhost:8000/health` returns healthy status
- [ ] Frontend opens at http://localhost:3000
- [ ] No yellow banner on frontend
- [ ] Dashboard shows chargers
- [ ] Timestamp updates every 5 seconds
- [ ] Can create a booking
- [ ] Booking appears in "My Bookings"

---

## 🆘 Still Having Issues?

1. **Check all containers are running:**
   ```bash
   docker ps
   ```

2. **Check backend logs:**
   ```bash
   docker logs ev-backend
   ```

3. **Restart everything:**
   ```bash
   docker compose down
   docker compose up -d
   docker exec ev-backend python scripts/quick_seed.py
   docker exec -d ev-backend python scripts/simulate_realtime_status.py
   cd frontend && npm start
   ```

4. **Contact teammate who set up the project**

---

## 💡 Tips

- **First time setup takes 5-10 minutes** (downloading Docker images, npm packages)
- **After first time, starting takes only 1-2 minutes**
- **Keep Docker Desktop running** while using the project
- **Don't close the terminal** where frontend is running
- **Use Ctrl+C** to stop frontend, not closing terminal window

---

**🎉 That's it! You should now have the full project running!**

**Questions? Check the troubleshooting section above or ask in the team chat.**
