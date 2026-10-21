#!/bin/bash
# Quick test script for EV Charging Network project
# Automates the testing setup process

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "========================================================================"
echo "🚀 EV Charging Network - Quick Test Setup"
echo "========================================================================"
echo ""

# Function to print status
print_status() {
  echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
  echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
  echo -e "${RED}✗${NC} $1"
}

# Step 1: Check Docker is running
echo "Step 1: Checking Docker..."
if ! docker info > /dev/null 2>&1; then
  print_error "Docker is not running. Please start Docker and try again."
  exit 1
fi
print_status "Docker is running"
echo ""

# Step 2: Start all containers
echo "Step 2: Starting all Docker containers..."
docker-compose up -d
echo ""

# Wait for containers to be ready
echo "Waiting for containers to be ready..."
sleep 5
echo ""

# Step 3: Verify containers are running
echo "Step 3: Verifying containers..."
EXPECTED_CONTAINERS=("ev-mysql-bangalore" "ev-mysql-chennai" "ev-mysql-delhi" "ev-mongodb" "ev-backend")
ALL_RUNNING=true

for container in "${EXPECTED_CONTAINERS[@]}"; do
  if docker ps --format '{{.Names}}' | grep -q "^${container}$"; then
    print_status "$container is running"
  else
    print_error "$container is NOT running"
    ALL_RUNNING=false
  fi
done

if [ "$ALL_RUNNING" = false ]; then
  print_error "Some containers failed to start. Check logs with: docker-compose logs"
  exit 1
fi
echo ""

# Step 4: Wait for MySQL to be ready
echo "Step 4: Waiting for MySQL nodes to be ready..."
for i in {1..30}; do
  if docker exec ev-mysql-bangalore mysqladmin ping -u ev_user -pevcharge_pass_2024 --silent > /dev/null 2>&1; then
    break
  fi
  if [ $i -eq 30 ]; then
    print_error "MySQL failed to start within 30 seconds"
    exit 1
  fi
  sleep 1
done
print_status "MySQL nodes are ready"
echo ""

# Step 5: Wait for MongoDB to be ready
echo "Step 5: Waiting for MongoDB to be ready..."
for i in {1..30}; do
  if docker exec ev-mongodb mongosh -u ev_admin -p evcharge_mongo_2024 --eval "db.version()" > /dev/null 2>&1; then
    break
  fi
  if [ $i -eq 30 ]; then
    print_error "MongoDB failed to start within 30 seconds"
    exit 1
  fi
  sleep 1
done
print_status "MongoDB is ready"
echo ""

# Step 6: Seed MongoDB
echo "Step 6: Seeding MongoDB with sample data..."
docker exec ev-backend python backend/scripts/seed_mongodb.py
echo ""

# Step 7: Verify MongoDB data
echo "Step 7: Verifying MongoDB collections..."
CHARGER_COUNT=$(docker exec ev-mongodb mongosh -u ev_admin -p evcharge_mongo_2024 --quiet --eval "db = db.getSiblingDB('ev_realtime'); db.charger_status.countDocuments({})")
if [ "$CHARGER_COUNT" -gt 0 ]; then
  print_status "MongoDB has $CHARGER_COUNT chargers"
else
  print_warning "MongoDB has no chargers. Seeding may have failed."
fi
echo ""

# Step 8: Start simulator
echo "Step 8: Starting real-time simulator..."
# Kill any existing simulator
docker exec ev-backend pkill -f simulate_realtime_status.py 2>/dev/null || true
sleep 1
# Start new simulator
docker exec -d ev-backend python backend/scripts/simulate_realtime_status.py
sleep 2

# Check if simulator is running
if docker exec ev-backend pgrep -f simulate_realtime_status.py > /dev/null; then
  print_status "Simulator is running"
else
  print_warning "Simulator may not have started. Check logs: docker logs ev-backend"
fi
echo ""

# Step 9: Test backend API
echo "Step 9: Testing backend API..."
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
  print_status "Backend API is responding"
else
  print_warning "Backend API is not responding on http://localhost:8000"
fi
echo ""

# Step 10: Check if frontend dependencies are installed
echo "Step 10: Checking frontend..."
if [ ! -d "frontend/node_modules" ]; then
  print_warning "Frontend dependencies not installed"
  echo "   Run: cd frontend && npm install"
else
  print_status "Frontend dependencies installed"
fi
echo ""

# Summary
echo "========================================================================"
echo "✅ Setup Complete!"
echo "========================================================================"
echo ""
echo "🗄️  Database Status:"
echo "   - MySQL (Bangalore): $(docker exec ev-mysql-bangalore mysql -u ev_user -pevcharge_pass_2024 -e 'SELECT COUNT(*) FROM ev_bangalore.stations' 2>/dev/null | tail -1) stations"
echo "   - MySQL (Chennai):   $(docker exec ev-mysql-chennai mysql -u ev_user -pevcharge_pass_2024 -e 'SELECT COUNT(*) FROM ev_chennai.stations' 2>/dev/null | tail -1) stations"
echo "   - MySQL (Delhi):     $(docker exec ev-mysql-delhi mysql -u ev_user -pevcharge_pass_2024 -e 'SELECT COUNT(*) FROM ev_delhi.stations' 2>/dev/null | tail -1) stations"
echo "   - MongoDB:           $CHARGER_COUNT chargers"
echo ""
echo "🔄 Real-time Simulator: Running (updates every 5 seconds)"
echo ""
echo "📡 Backend API: http://localhost:8000"
echo "   Test: curl http://localhost:8000/api/stations?city=bangalore"
echo ""
echo "💻 Frontend:"
echo "   1. cd frontend"
echo "   2. npm install  (if not done already)"
echo "   3. npm start"
echo "   4. Open http://localhost:3000"
echo ""
echo "🎯 Quick Test:"
echo "   1. Open http://localhost:3000/dashboard"
echo "   2. Select city + station"
echo "   3. Watch timestamp update every 5 seconds"
echo ""
echo "📊 Watch live simulator:"
echo "   docker logs -f ev-backend | grep -E 'Total:'"
echo ""
echo "🛑 Stop all:"
echo "   docker-compose down"
echo ""
echo "📚 Full testing guide: TESTING_QUICK_START.md"
echo "========================================================================"
