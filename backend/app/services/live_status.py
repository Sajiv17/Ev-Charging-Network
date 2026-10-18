"""
Optional link to MongoDB (Person 3's real-time data).

The backend only READS live charger status and WRITES charging-session
documents. Every call is best effort with a short timeout: if MongoDB is down
or not set up yet, bookings and sessions still work on MySQL alone.

Uses its own client (2 s timeout) so a missing MongoDB never blocks a request
for 30 s, and so app/db/mongodb_connection.py stays Person 3's file.
"""

import logging
import time
from datetime import datetime, timezone

from app.core.config import settings

log = logging.getLogger("live_status")

_client = None
_disabled_until = 0.0


def _db():
    global _client, _disabled_until
    if time.monotonic() < _disabled_until:
        return None
    try:
        if _client is None:
            from pymongo import MongoClient

            _client = MongoClient(settings.mongodb_url, serverSelectionTimeoutMS=2000, connectTimeoutMS=2000)
        return _client[settings.MONGODB_DB]
    except Exception:
        _disabled_until = time.monotonic() + 60
        return None


def _call(fn):
    global _disabled_until
    db = _db()
    if db is None:
        return None
    try:
        return fn(db)
    except Exception as exc:
        _disabled_until = time.monotonic() + 60
        log.warning("MongoDB unavailable (%s); continuing with MySQL only for 60s", exc.__class__.__name__)
        return None


def charger_live(city: str, charger_id: int) -> dict | None:
    """Latest telemetry document for a charger, or None if MongoDB has nothing / is down."""

    def q(db):
        doc = db["charger_status"].find_one({"charger_id": charger_id, "city": city}) or db[
            "charger_status"
        ].find_one({"charger_id": charger_id})
        if doc:
            doc.pop("_id", None)
        return doc

    return _call(q)


def session_started(city: str, booking: dict) -> None:
    now = datetime.now(timezone.utc)
    _call(
        lambda db: db["charging_sessions"].update_one(
            {"city": city, "booking_id": booking["booking_id"]},
            {
                "$set": {
                    "city": city,
                    "booking_id": booking["booking_id"],
                    "charger_id": booking["charger_id"],
                    "user_id": booking["user_id"],
                    "status": "active",
                    "started_at": now,
                    "energy_kwh": 0.0,
                    "readings": [],
                }
            },
            upsert=True,
        )
    )


def session_ended(city: str, booking_id: int, energy_kwh: float, cost: float) -> None:
    _call(
        lambda db: db["charging_sessions"].update_one(
            {"city": city, "booking_id": booking_id},
            {
                "$set": {
                    "status": "closed",
                    "ended_at": datetime.now(timezone.utc),
                    "energy_kwh": energy_kwh,
                    "final_cost": cost,
                }
            },
        )
    )
