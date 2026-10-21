#!/usr/bin/env python3
"""
Real-Time Charger Status Simulator

This script continuously updates MongoDB's charger_status collection to simulate
live charger telemetry. It runs in the background and updates every 5 seconds.

What it does:
1. Updates last_heartbeat for all chargers every cycle
2. Simulates realistic power draw for occupied chargers (40-50 kW for DC, 6-8 kW for AC)
3. Increments session_energy_kwh for active charging sessions
4. Randomly transitions some chargers between states (realistic charge durations)

Usage:
    python backend/scripts/simulate_realtime_status.py

Or run in Docker:
    docker exec -d ev-backend python backend/scripts/simulate_realtime_status.py
"""

import sys
import time
import random
from pathlib import Path
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pymongo import MongoClient
from app.core.config import settings
from app.db.mysql_connection import get_city_session


class StatusSimulator:
    def __init__(self):
        """Initialize connections to MongoDB and MySQL"""
        self.mongo_client = MongoClient(settings.mongodb_url)
        self.mongo_db = self.mongo_client[settings.MONGODB_DB]

        self.charger_status_coll = self.mongo_db["charger_status"]
        self.sessions_coll = self.mongo_db["charging_sessions"]

        print(f"Connected to MongoDB: {settings.MONGODB_DB}")
        print(f"Charger status collection: {self.charger_status_coll.count_documents({})} chargers")
        print(f"Active sessions: {self.sessions_coll.count_documents({'status': 'active'})}")
        print()

    def get_charger_type(self, charger_id: int, city: str) -> str:
        """Get charger type (AC/DC) from MySQL"""
        db = get_city_session(city)
        try:
            result = db.execute(
                "SELECT charger_type FROM charger_units WHERE charger_id = :cid",
                {"cid": charger_id}
            ).fetchone()
            return result[0] if result else "DC"
        finally:
            db.close()

    def simulate_power_draw(self, charger_type: str, session_duration_minutes: float) -> float:
        """
        Simulate realistic power draw that decreases as battery approaches full charge.

        DC fast chargers: Start at 48-50 kW, taper to 20-30 kW near end
        AC chargers: Steady 6-8 kW throughout
        """
        if charger_type == "DC":
            # DC fast charging: high power initially, tapers off as battery fills
            if session_duration_minutes < 10:
                # First 10 minutes: max power (48-50 kW)
                return random.uniform(48.0, 50.0)
            elif session_duration_minutes < 30:
                # 10-30 minutes: tapering (35-45 kW)
                return random.uniform(35.0, 45.0)
            else:
                # 30+ minutes: slow charge near full (20-30 kW)
                return random.uniform(20.0, 30.0)
        else:
            # AC charging: steady power throughout
            return random.uniform(6.5, 7.5)

    def update_heartbeats(self):
        """Update last_heartbeat for all chargers to show they're online"""
        now = datetime.utcnow()
        result = self.charger_status_coll.update_many(
            {},
            {"$set": {"last_heartbeat": now, "updated_at": now}}
        )
        return result.modified_count

    def update_occupied_chargers(self):
        """
        Update power draw and energy for all occupied chargers.
        Also increment session energy in charging_sessions collection.
        """
        occupied = list(self.charger_status_coll.find({"status": "occupied"}))

        for charger in occupied:
            charger_id = charger["charger_id"]
            city = charger["city"]
            session_started_at = charger.get("session_started_at")

            if not session_started_at:
                continue

            # Calculate how long this session has been running
            session_duration = datetime.utcnow() - session_started_at
            session_minutes = session_duration.total_seconds() / 60

            # Get charger type to determine power profile
            charger_type = self.get_charger_type(charger_id, city)

            # Simulate current power draw
            current_power_kw = self.simulate_power_draw(charger_type, session_minutes)

            # Calculate energy increment for this 5-second update
            # Energy (kWh) = Power (kW) × Time (hours)
            # 5 seconds = 5/3600 hours
            energy_increment_kwh = current_power_kw * (5.0 / 3600.0)

            # Update charger status in MongoDB
            new_energy = charger.get("session_energy_kwh", 0.0) + energy_increment_kwh

            self.charger_status_coll.update_one(
                {"charger_id": charger_id},
                {
                    "$set": {
                        "current_power_kw": round(current_power_kw, 2),
                        "session_energy_kwh": round(new_energy, 2),
                        "updated_at": datetime.utcnow()
                    }
                }
            )

            # Also update the charging_sessions collection
            booking_id = charger.get("active_booking_id")
            if booking_id:
                self.sessions_coll.update_one(
                    {"booking_id": booking_id, "status": "active"},
                    {
                        "$set": {
                            "session_energy_kwh": round(new_energy, 2),
                            "updated_at": datetime.utcnow()
                        },
                        "$push": {
                            "power_samples": {
                                "$each": [{
                                    "timestamp": datetime.utcnow(),
                                    "power_kw": round(current_power_kw, 2)
                                }],
                                "$slice": -100  # Keep only last 100 samples
                            }
                        }
                    }
                )

    def randomly_transition_chargers(self):
        """
        Randomly transition some chargers to simulate realistic behavior:
        - Some available chargers become occupied (new sessions start)
        - Some occupied chargers become available (sessions end)

        This happens rarely (low probability per cycle) to simulate organic usage.
        """
        # 5% chance per cycle to end a long-running session
        occupied = list(self.charger_status_coll.find({"status": "occupied"}))
        for charger in occupied:
            session_started_at = charger.get("session_started_at")
            if session_started_at:
                session_duration = datetime.utcnow() - session_started_at
                session_minutes = session_duration.total_seconds() / 60

                # If session has been running for 30+ minutes, 5% chance to end it
                if session_minutes > 30 and random.random() < 0.05:
                    self.end_session(charger)

    def end_session(self, charger: dict):
        """
        End a charging session:
        1. Set charger status to available
        2. Close the charging_session document
        """
        charger_id = charger["charger_id"]
        booking_id = charger.get("active_booking_id")
        final_energy = charger.get("session_energy_kwh", 0.0)

        # Update charger_status: back to available
        self.charger_status_coll.update_one(
            {"charger_id": charger_id},
            {
                "$set": {
                    "status": "available",
                    "current_power_kw": 0.0,
                    "session_energy_kwh": 0.0,
                    "active_booking_id": None,
                    "session_started_at": None,
                    "status_changed_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
            }
        )

        # Close the session in charging_sessions
        if booking_id:
            session = self.sessions_coll.find_one({"booking_id": booking_id})
            if session:
                rate_per_kwh = session.get("rate_per_kwh", 12.50)
                energy_cost = round(final_energy * rate_per_kwh, 2)

                self.sessions_coll.update_one(
                    {"booking_id": booking_id},
                    {
                        "$set": {
                            "status": "completed",
                            "session_ended_at": datetime.utcnow(),
                            "final_energy_kwh": final_energy,
                            "energy_cost": energy_cost,
                            "updated_at": datetime.utcnow()
                        }
                    }
                )

                print(f"  Session ended: Charger {charger_id}, {final_energy:.2f} kWh, ₹{energy_cost:.2f}")

    def print_status_summary(self):
        """Print a summary of current charger statuses"""
        total = self.charger_status_coll.count_documents({})
        available = self.charger_status_coll.count_documents({"status": "available"})
        occupied = self.charger_status_coll.count_documents({"status": "occupied"})
        faulted = self.charger_status_coll.count_documents({"status": "faulted"})
        maintenance = self.charger_status_coll.count_documents({"status": "maintenance"})

        active_sessions = self.sessions_coll.count_documents({"status": "active"})

        # Show a few active chargers with their current power
        active_chargers = list(self.charger_status_coll.find(
            {"status": "occupied"},
            {"charger_id": 1, "city": 1, "current_power_kw": 1, "session_energy_kwh": 1}
        ).limit(3))

        print(f"[{datetime.now().strftime('%H:%M:%S')}] "
              f"Total: {total} | Available: {available} | Occupied: {occupied} | "
              f"Faulted: {faulted} | Maintenance: {maintenance} | Active Sessions: {active_sessions}")

        if active_chargers:
            for ch in active_chargers:
                print(f"  Charger {ch['charger_id']} ({ch['city']}): "
                      f"{ch['current_power_kw']:.1f} kW, {ch['session_energy_kwh']:.2f} kWh")

    def run(self, update_interval_seconds: int = 5):
        """
        Main loop: continuously update charger status every N seconds.

        Args:
            update_interval_seconds: How often to update (default: 5 seconds)
        """
        print("="*70)
        print("Real-Time Charger Status Simulator")
        print("="*70)
        print(f"Update interval: {update_interval_seconds} seconds")
        print("Press Ctrl+C to stop")
        print("="*70)
        print()

        cycle = 0

        try:
            while True:
                cycle += 1

                # Update all chargers
                heartbeats_updated = self.update_heartbeats()

                # Update occupied chargers (power draw + energy)
                self.update_occupied_chargers()

                # Randomly transition some chargers (low probability)
                if cycle % 10 == 0:  # Check every 10 cycles (50 seconds)
                    self.randomly_transition_chargers()

                # Print status summary
                self.print_status_summary()

                # Wait for next cycle
                time.sleep(update_interval_seconds)

        except KeyboardInterrupt:
            print("\n")
            print("="*70)
            print("Simulator stopped by user")
            print("="*70)
            self.mongo_client.close()


def main():
    """Entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="Real-time charger status simulator")
    parser.add_argument(
        "--interval",
        type=int,
        default=5,
        help="Update interval in seconds (default: 5)"
    )

    args = parser.parse_args()

    try:
        simulator = StatusSimulator()
        simulator.run(update_interval_seconds=args.interval)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
