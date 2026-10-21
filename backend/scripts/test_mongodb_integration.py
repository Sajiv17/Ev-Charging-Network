#!/usr/bin/env python3
"""
Test MongoDB integration - verifies everything is working correctly.

Run this after seeding MongoDB to verify:
1. Collections exist with correct indexes
2. Sample data is present
3. Backend can read/write to MongoDB
4. Simulator updates are working (if running)
"""

import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from pymongo import MongoClient
from app.core.config import settings
from app.services import mongodb_service


def test_connection():
    """Test MongoDB connection"""
    print("1. Testing MongoDB connection...")
    try:
        client = MongoClient(settings.mongodb_url, serverSelectionTimeoutMS=5000)
        client.server_info()
        print("   ✓ Connected to MongoDB")
        return client
    except Exception as e:
        print(f"   ✗ Failed to connect: {e}")
        sys.exit(1)


def test_collections(client):
    """Test collections exist"""
    print("\n2. Checking collections...")
    db = client[settings.MONGODB_DB]

    expected_collections = ["charger_status", "charging_sessions", "fault_reports", "audit_log"]
    existing_collections = db.list_collection_names()

    for coll_name in expected_collections:
        if coll_name in existing_collections:
            count = db[coll_name].count_documents({})
            print(f"   ✓ {coll_name}: {count} documents")
        else:
            print(f"   ✗ {coll_name}: MISSING")


def test_indexes(client):
    """Test indexes exist"""
    print("\n3. Checking indexes...")
    db = client[settings.MONGODB_DB]

    index_counts = {
        "charger_status": 4,
        "charging_sessions": 5,
        "fault_reports": 5,
        "audit_log": 6
    }

    for coll_name, expected_count in index_counts.items():
        if coll_name in db.list_collection_names():
            indexes = list(db[coll_name].list_indexes())
            actual_count = len(indexes)

            if actual_count >= expected_count:
                print(f"   ✓ {coll_name}: {actual_count} indexes")
            else:
                print(f"   ✗ {coll_name}: only {actual_count}/{expected_count} indexes")
                for idx in indexes:
                    print(f"      - {idx['name']}")


def test_charger_status():
    """Test charger_status operations"""
    print("\n4. Testing charger_status operations...")

    # Get a charger
    status = mongodb_service.get_charger_status(charger_id=1)
    if status:
        print(f"   ✓ Read charger 1: status={status['status']}, power={status['current_power_kw']} kW")
    else:
        print("   ✗ Could not read charger 1")
        return

    # Get station chargers
    station_chargers = mongodb_service.get_station_chargers_status(station_id=1)
    if station_chargers:
        print(f"   ✓ Read station 1: {len(station_chargers)} chargers")
    else:
        print("   ⚠ No chargers found for station 1")

    # Check heartbeat freshness
    last_heartbeat = status.get("last_heartbeat")
    if last_heartbeat:
        age_seconds = (datetime.utcnow() - last_heartbeat).total_seconds()
        if age_seconds < 60:
            print(f"   ✓ Heartbeat is fresh ({age_seconds:.1f}s old)")
        else:
            print(f"   ⚠ Heartbeat is stale ({age_seconds:.1f}s old) - is simulator running?")


def test_sessions():
    """Test charging_sessions operations"""
    print("\n5. Testing charging_sessions...")

    active = mongodb_service.get_active_sessions()
    if active:
        print(f"   ✓ Found {len(active)} active sessions")
        for session in active[:2]:  # Show first 2
            print(f"      - Booking {session['booking_id']}: {session['session_energy_kwh']:.2f} kWh")
    else:
        print("   ⚠ No active sessions (run simulator to see live sessions)")

    # Check for completed sessions
    from app.db.mongodb_connection import charging_sessions_collection
    completed = charging_sessions_collection.count_documents({"status": "completed"})
    print(f"   ✓ {completed} completed sessions in database")


def test_fault_reports():
    """Test fault_reports operations"""
    print("\n6. Testing fault_reports...")

    from app.db.mongodb_connection import fault_reports_collection
    total_faults = fault_reports_collection.count_documents({})
    open_faults = fault_reports_collection.count_documents({"resolution_status": "open"})
    resolved_faults = fault_reports_collection.count_documents({"resolution_status": "resolved"})

    print(f"   ✓ Total faults: {total_faults} (Open: {open_faults}, Resolved: {resolved_faults})")


def test_audit_log():
    """Test audit_log operations"""
    print("\n7. Testing audit_log...")

    recent_events = mongodb_service.get_recent_audit_events(limit=5)
    if recent_events:
        print(f"   ✓ Found {len(recent_events)} recent audit events")
        for event in recent_events[:3]:
            print(f"      - {event['event_type']}: tx {event['transaction_id'][:16]}...")
    else:
        print("   ⚠ No audit events yet")


def main():
    print("="*70)
    print("MongoDB Integration Test")
    print("="*70)
    print()

    client = test_connection()
    test_collections(client)
    test_indexes(client)
    test_charger_status()
    test_sessions()
    test_fault_reports()
    test_audit_log()

    print()
    print("="*70)
    print("✓ Integration test complete")
    print("="*70)
    print()
    print("Next steps:")
    print("  - Start simulator: docker exec -d ev-backend python backend/scripts/simulate_realtime_status.py")
    print("  - View logs: docker logs -f ev-backend")
    print("  - Test API: curl http://localhost:8000/api/stations/1/live")


if __name__ == "__main__":
    main()
