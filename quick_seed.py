#!/usr/bin/env python3
"""Quick MongoDB seed"""
from datetime import datetime
from pymongo import MongoClient

client = MongoClient('mongodb://ev_admin:evcharge_mongo_2024@mongodb:27017/')
db = client['ev_realtime']

print("Seeding MongoDB...")

# Chargers
cs = db['charger_status']
cs.delete_many({})
chargers = []
cid = 1
for city in ['bangalore', 'chennai', 'delhi']:
    for sid in range(1, 4):
        for i in range(3):
            chargers.append({
                'charger_id': cid, 'station_id': sid, 'city': city,
                'status': 'available' if i < 2 else 'occupied',
                'current_power_kw': 0.0 if i < 2 else 45.5,
                'session_energy_kwh': 0.0 if i < 2 else 12.3,
                'last_heartbeat': datetime.utcnow(),
                'updated_at': datetime.utcnow()
            })
            cid += 1
cs.insert_many(chargers)
cs.create_index('charger_id', unique=True)
print(f"✓ {len(chargers)} chargers")

# Sessions
sess = db['charging_sessions']
sess.delete_many({})
sess.insert_many([{
    'booking_id': 101, 'charger_id': 3, 'status': 'active',
    'session_energy_kwh': 12.3, 'power_samples': [],
    'created_at': datetime.utcnow()
}])
sess.create_index('booking_id', unique=True)
print("✓ 1 session")

print("✅ Done!")
