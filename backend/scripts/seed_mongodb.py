"""
Seed MongoDB with sample data for EV Charging Network.

This script populates:
- charger_status: initial status for all chargers from MySQL
- charging_sessions: 5 completed sessions + 2 active sessions
- fault_reports: 3 resolved faults + 1 open fault
- audit_log: sample transaction events

Run after MySQL is seeded and backend can connect to both databases.
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
from pymongo import MongoClient

# Add parent directory to path to import from app
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import settings
from app.db.mysql_connection import get_city_session


def get_mongo_db():
    """Connect to MongoDB"""
    client = MongoClient(settings.mongodb_url)
    return client[settings.MONGODB_DB]


def seed_charger_status(mongo_db):
    """
    Populate charger_status collection with all chargers from MySQL.
    Initial state: all chargers are 'available' with zero power.
    """
    print("Seeding charger_status...")

    charger_status_coll = mongo_db["charger_status"]
    charger_status_coll.delete_many({})  # Clear existing

    cities = ["bangalore", "chennai", "delhi"]
    total_inserted = 0

    for city in cities:
        db = get_city_session(city)
        try:
            # Fetch all chargers from this city's MySQL node
            result = db.execute("""
                SELECT cu.charger_id, cu.station_id, cu.status
                FROM charger_units cu
                JOIN stations s ON s.station_id = cu.station_id
                ORDER BY cu.charger_id
            """)

            chargers = result.fetchall()

            for charger in chargers:
                charger_id, station_id, mysql_status = charger

                # Map MySQL status to MongoDB status
                # MySQL: available, occupied, faulted, maintenance
                # MongoDB: same enum
                mongo_status = mysql_status

                now = datetime.utcnow()

                doc = {
                    "charger_id": charger_id,
                    "station_id": station_id,
                    "city": city,
                    "status": mongo_status,
                    "current_power_kw": 0.0,
                    "session_energy_kwh": 0.0,
                    "fault_code": None,
                    "fault_message": None,
                    "last_heartbeat": now,
                    "status_changed_at": now,
                    "active_booking_id": None,
                    "session_started_at": None,
                    "created_at": now,
                    "updated_at": now
                }

                charger_status_coll.insert_one(doc)
                total_inserted += 1

        finally:
            db.close()

    print(f"✓ Inserted {total_inserted} charger status documents")


def seed_charging_sessions(mongo_db):
    """
    Create sample charging sessions:
    - 5 completed sessions (1-2 days ago)
    - 2 active sessions (right now)
    """
    print("Seeding charging_sessions...")

    sessions_coll = mongo_db["charging_sessions"]
    sessions_coll.delete_many({})

    now = datetime.utcnow()

    # Completed sessions
    completed_sessions = [
        {
            "booking_id": 1,
            "charger_id": 1,
            "user_id": 10,
            "station_id": 1,
            "city": "bangalore",
            "status": "completed",
            "session_started_at": now - timedelta(days=2, hours=10),
            "session_ended_at": now - timedelta(days=2, hours=9),
            "session_energy_kwh": 28.5,
            "final_energy_kwh": 28.5,
            "rate_per_kwh": 12.50,
            "energy_cost": 356.25,
            "charger_type": "DC",
            "vehicle_make": "Tata",
            "vehicle_model": "Nexon EV",
            "created_at": now - timedelta(days=2, hours=10),
            "updated_at": now - timedelta(days=2, hours=9)
        },
        {
            "booking_id": 2,
            "charger_id": 3,
            "user_id": 12,
            "station_id": 1,
            "city": "bangalore",
            "status": "completed",
            "session_started_at": now - timedelta(days=1, hours=15),
            "session_ended_at": now - timedelta(days=1, hours=14, minutes=30),
            "session_energy_kwh": 15.2,
            "final_energy_kwh": 15.2,
            "rate_per_kwh": 8.00,
            "energy_cost": 121.60,
            "charger_type": "AC",
            "vehicle_make": "MG",
            "vehicle_model": "ZS EV",
            "created_at": now - timedelta(days=1, hours=15),
            "updated_at": now - timedelta(days=1, hours=14, minutes=30)
        },
        {
            "booking_id": 3,
            "charger_id": 10,
            "user_id": 15,
            "station_id": 4,
            "city": "chennai",
            "status": "completed",
            "session_started_at": now - timedelta(days=1, hours=8),
            "session_ended_at": now - timedelta(days=1, hours=7, minutes=15),
            "session_energy_kwh": 32.0,
            "final_energy_kwh": 32.0,
            "rate_per_kwh": 12.50,
            "energy_cost": 400.00,
            "charger_type": "DC",
            "vehicle_make": "Hyundai",
            "vehicle_model": "Kona Electric",
            "created_at": now - timedelta(days=1, hours=8),
            "updated_at": now - timedelta(days=1, hours=7, minutes=15)
        },
        {
            "booking_id": 4,
            "charger_id": 16,
            "user_id": 20,
            "station_id": 7,
            "city": "delhi",
            "status": "completed",
            "session_started_at": now - timedelta(hours=12),
            "session_ended_at": now - timedelta(hours=11, minutes=20),
            "session_energy_kwh": 18.7,
            "final_energy_kwh": 18.7,
            "rate_per_kwh": 13.00,
            "energy_cost": 243.10,
            "charger_type": "DC",
            "vehicle_make": "Tata",
            "vehicle_model": "Tigor EV",
            "created_at": now - timedelta(hours=12),
            "updated_at": now - timedelta(hours=11, minutes=20)
        },
        {
            "booking_id": 5,
            "charger_id": 18,
            "user_id": 22,
            "station_id": 7,
            "city": "delhi",
            "status": "interrupted",  # Charger faulted mid-session
            "session_started_at": now - timedelta(hours=6),
            "session_ended_at": now - timedelta(hours=5, minutes=40),
            "session_energy_kwh": 8.3,
            "final_energy_kwh": 8.3,
            "rate_per_kwh": 13.00,
            "energy_cost": 107.90,
            "charger_type": "DC",
            "vehicle_make": "Mahindra",
            "vehicle_model": "e2oPlus",
            "created_at": now - timedelta(hours=6),
            "updated_at": now - timedelta(hours=5, minutes=40)
        }
    ]

    sessions_coll.insert_many(completed_sessions)
    print(f"✓ Inserted {len(completed_sessions)} completed sessions")

    # Active sessions (happening right now)
    active_sessions = [
        {
            "booking_id": 100,
            "charger_id": 2,
            "user_id": 11,
            "station_id": 1,
            "city": "bangalore",
            "status": "active",
            "session_started_at": now - timedelta(minutes=25),
            "session_ended_at": None,
            "session_energy_kwh": 12.3,  # Still accumulating
            "final_energy_kwh": None,
            "power_samples": [
                {"timestamp": now - timedelta(minutes=25), "power_kw": 48.2},
                {"timestamp": now - timedelta(minutes=20), "power_kw": 47.8},
                {"timestamp": now - timedelta(minutes=15), "power_kw": 46.5},
                {"timestamp": now - timedelta(minutes=10), "power_kw": 45.1},
                {"timestamp": now - timedelta(minutes=5), "power_kw": 43.9}
            ],
            "rate_per_kwh": 12.50,
            "energy_cost": None,
            "charger_type": "DC",
            "vehicle_make": "Tata",
            "vehicle_model": "Nexon EV",
            "created_at": now - timedelta(minutes=25),
            "updated_at": now
        },
        {
            "booking_id": 101,
            "charger_id": 11,
            "user_id": 16,
            "station_id": 4,
            "city": "chennai",
            "status": "active",
            "session_started_at": now - timedelta(minutes=40),
            "session_ended_at": None,
            "session_energy_kwh": 7.8,
            "final_energy_kwh": None,
            "power_samples": [
                {"timestamp": now - timedelta(minutes=40), "power_kw": 7.2},
                {"timestamp": now - timedelta(minutes=35), "power_kw": 7.1},
                {"timestamp": now - timedelta(minutes=30), "power_kw": 7.0},
                {"timestamp": now - timedelta(minutes=25), "power_kw": 6.9},
                {"timestamp": now - timedelta(minutes=20), "power_kw": 6.8}
            ],
            "rate_per_kwh": 8.00,
            "energy_cost": None,
            "charger_type": "AC",
            "vehicle_make": "MG",
            "vehicle_model": "ZS EV",
            "created_at": now - timedelta(minutes=40),
            "updated_at": now
        }
    ]

    sessions_coll.insert_many(active_sessions)
    print(f"✓ Inserted {len(active_sessions)} active sessions")


def seed_fault_reports(mongo_db):
    """
    Create sample fault reports:
    - 3 resolved faults
    - 1 open fault
    """
    print("Seeding fault_reports...")

    faults_coll = mongo_db["fault_reports"]
    faults_coll.delete_many({})

    now = datetime.utcnow()

    faults = [
        {
            "charger_id": 18,
            "station_id": 7,
            "operator_id": 3,  # operator.delhi@demo.ev
            "city": "delhi",
            "fault_type": "hardware_failure",
            "error_code": "ERR_OVERHEAT_CPU",
            "severity": "critical",
            "description": "Charger CPU temperature reached 95°C. Automatic shutdown triggered. Visual inspection shows dust buildup in cooling fan.",
            "photos": [],
            "resolution_status": "resolved",
            "resolution_notes": "Replaced cooling fan, cleaned heat sink, system operational.",
            "fault_reported_at": now - timedelta(days=1, hours=6),
            "resolved_at": now - timedelta(days=1, hours=2),
            "resolved_by": 3,
            "estimated_repair_time_hours": 4.0,
            "actual_repair_time_hours": 4.0,
            "charger_make": "ABB",
            "charger_model": "Terra 184",
            "created_at": now - timedelta(days=1, hours=6),
            "updated_at": now - timedelta(days=1, hours=2)
        },
        {
            "charger_id": 5,
            "station_id": 2,
            "operator_id": 2,  # operator.bangalore@demo.ev
            "city": "bangalore",
            "fault_type": "communication_error",
            "error_code": "ERR_COMM_TIMEOUT",
            "severity": "high",
            "description": "Charger lost connection to backend. Network cable found unplugged.",
            "photos": [],
            "resolution_status": "resolved",
            "resolution_notes": "Reconnected network cable. Connection stable.",
            "fault_reported_at": now - timedelta(days=3, hours=10),
            "resolved_at": now - timedelta(days=3, hours=9, minutes=30),
            "resolved_by": 2,
            "estimated_repair_time_hours": 0.5,
            "actual_repair_time_hours": 0.5,
            "charger_make": "Delta",
            "charger_model": "DC City 25",
            "created_at": now - timedelta(days=3, hours=10),
            "updated_at": now - timedelta(days=3, hours=9, minutes=30)
        },
        {
            "charger_id": 12,
            "station_id": 5,
            "operator_id": 4,  # operator.chennai@demo.ev
            "city": "chennai",
            "fault_type": "software_error",
            "error_code": "ERR_FIRMWARE_CRASH",
            "severity": "medium",
            "description": "Charger firmware crashed during session. Rebooted automatically but session data lost.",
            "photos": [],
            "resolution_status": "resolved",
            "resolution_notes": "Applied firmware update v2.4.1. Issue resolved.",
            "fault_reported_at": now - timedelta(days=5, hours=8),
            "resolved_at": now - timedelta(days=5, hours=6),
            "resolved_by": 4,
            "estimated_repair_time_hours": 2.0,
            "actual_repair_time_hours": 2.0,
            "charger_make": "Siemens",
            "charger_model": "Sicharge D",
            "created_at": now - timedelta(days=5, hours=8),
            "updated_at": now - timedelta(days=5, hours=6)
        },
        {
            "charger_id": 7,
            "station_id": 3,
            "operator_id": 2,  # operator.bangalore@demo.ev
            "city": "bangalore",
            "fault_type": "power_supply",
            "error_code": "ERR_GRID_VOLTAGE_LOW",
            "severity": "high",
            "description": "Grid voltage dropped to 190V. Charger suspended operation to protect connected vehicle.",
            "photos": [],
            "resolution_status": "in_progress",
            "resolution_notes": "Electrician investigating grid connection. ETA 2 hours.",
            "fault_reported_at": now - timedelta(hours=2),
            "resolved_at": None,
            "resolved_by": None,
            "estimated_repair_time_hours": 3.0,
            "actual_repair_time_hours": None,
            "charger_make": "ABB",
            "charger_model": "Terra 54",
            "created_at": now - timedelta(hours=2),
            "updated_at": now - timedelta(minutes=30)
        }
    ]

    faults_coll.insert_many(faults)
    print(f"✓ Inserted {len(faults)} fault reports")


def seed_audit_log(mongo_db):
    """
    Create sample audit log entries showing a successful booking and a failed concurrent attempt.
    """
    print("Seeding audit_log...")

    audit_coll = mongo_db["audit_log"]
    audit_coll.delete_many({})

    now = datetime.utcnow()

    # Successful booking (user 10, slot 42)
    tx1_time = now - timedelta(minutes=30)

    # Failed concurrent booking attempt (user 12, same slot 42)
    tx2_time = now - timedelta(minutes=30, seconds=1)  # 1 second later

    events = [
        # Transaction 1 (successful)
        {
            "event_type": "slot_check",
            "transaction_id": "tx_1729512345_abc123",
            "user_id": 10,
            "booking_id": None,
            "slot_id": 42,
            "charger_id": 2,
            "city": "bangalore",
            "success": True,
            "timestamp": tx1_time,
            "endpoint": "/api/bookings",
            "request_id": "req_xyz789",
            "created_at": tx1_time
        },
        {
            "event_type": "lock_acquired",
            "transaction_id": "tx_1729512345_abc123",
            "user_id": 10,
            "slot_id": 42,
            "charger_id": 2,
            "city": "bangalore",
            "lock_mode": "X",
            "lock_wait_time_ms": 0,
            "timestamp": tx1_time + timedelta(milliseconds=50),
            "endpoint": "/api/bookings",
            "request_id": "req_xyz789",
            "created_at": tx1_time + timedelta(milliseconds=50)
        },
        {
            "event_type": "wallet_debit",
            "transaction_id": "tx_1729512345_abc123",
            "user_id": 10,
            "slot_id": 42,
            "city": "bangalore",
            "success": True,
            "timestamp": tx1_time + timedelta(milliseconds=200),
            "endpoint": "/api/bookings",
            "request_id": "req_xyz789",
            "created_at": tx1_time + timedelta(milliseconds=200)
        },
        {
            "event_type": "booking_created",
            "transaction_id": "tx_1729512345_abc123",
            "user_id": 10,
            "booking_id": 100,
            "slot_id": 42,
            "charger_id": 2,
            "city": "bangalore",
            "success": True,
            "timestamp": tx1_time + timedelta(milliseconds=350),
            "endpoint": "/api/bookings",
            "request_id": "req_xyz789",
            "created_at": tx1_time + timedelta(milliseconds=350)
        },
        {
            "event_type": "commit",
            "transaction_id": "tx_1729512345_abc123",
            "user_id": 10,
            "booking_id": 100,
            "slot_id": 42,
            "city": "bangalore",
            "success": True,
            "timestamp": tx1_time + timedelta(milliseconds=500),
            "endpoint": "/api/bookings",
            "request_id": "req_xyz789",
            "created_at": tx1_time + timedelta(milliseconds=500)
        },

        # Transaction 2 (failed - slot already booked)
        {
            "event_type": "slot_check",
            "transaction_id": "tx_1729512346_def456",
            "user_id": 12,
            "booking_id": None,
            "slot_id": 42,
            "charger_id": 2,
            "city": "bangalore",
            "timestamp": tx2_time,
            "endpoint": "/api/bookings",
            "request_id": "req_abc123",
            "created_at": tx2_time
        },
        {
            "event_type": "lock_wait",
            "transaction_id": "tx_1729512346_def456",
            "user_id": 12,
            "slot_id": 42,
            "charger_id": 2,
            "city": "bangalore",
            "lock_mode": "X",
            "lock_wait_time_ms": 1250,  # Waited 1.25 seconds for lock
            "timestamp": tx2_time + timedelta(milliseconds=1250),
            "endpoint": "/api/bookings",
            "request_id": "req_abc123",
            "created_at": tx2_time + timedelta(milliseconds=1250)
        },
        {
            "event_type": "lock_acquired",
            "transaction_id": "tx_1729512346_def456",
            "user_id": 12,
            "slot_id": 42,
            "charger_id": 2,
            "city": "bangalore",
            "lock_mode": "X",
            "lock_wait_time_ms": 1250,
            "timestamp": tx2_time + timedelta(milliseconds=1300),
            "endpoint": "/api/bookings",
            "request_id": "req_abc123",
            "created_at": tx2_time + timedelta(milliseconds=1300)
        },
        {
            "event_type": "rollback",
            "transaction_id": "tx_1729512346_def456",
            "user_id": 12,
            "slot_id": 42,
            "city": "bangalore",
            "success": False,
            "error_message": "Slot no longer available",
            "timestamp": tx2_time + timedelta(milliseconds=1400),
            "endpoint": "/api/bookings",
            "request_id": "req_abc123",
            "created_at": tx2_time + timedelta(milliseconds=1400)
        }
    ]

    audit_coll.insert_many(events)
    print(f"✓ Inserted {len(events)} audit log events")


def main():
    """Run all seed functions"""
    print("\n" + "="*60)
    print("MongoDB Seed Script - EV Charging Network")
    print("="*60 + "\n")

    try:
        mongo_db = get_mongo_db()
        print(f"Connected to MongoDB: {settings.MONGODB_DB}\n")

        seed_charger_status(mongo_db)
        seed_charging_sessions(mongo_db)
        seed_fault_reports(mongo_db)
        seed_audit_log(mongo_db)

        print("\n" + "="*60)
        print("✓ MongoDB seeding complete!")
        print("="*60 + "\n")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
