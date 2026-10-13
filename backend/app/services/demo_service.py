"""Helpers for the live concurrency demo (only reachable when DEMO_MODE=true)."""

from datetime import date, datetime, time, timedelta

from sqlalchemy import text

from app.core.cities import city_id_of, normalize_city
from app.db.mysql_connection import city_session
from app.services.errors import NotFound

DEMO_DATE_START = date(2030, 1, 1)  # far future: demo slots never clash with real ones


def create_fresh_slot(city: str, connector_type: str = "CCS2") -> dict:
    """Make a brand-new available slot so every demo run starts clean."""
    city = normalize_city(city)
    with city_session(city) as db:
        charger = (
            db.execute(
                text(
                    """
                SELECT c.charger_id, c.charger_code, c.connector_type, s.station_id, s.station_name
                FROM charger_units c JOIN stations s ON s.station_id = c.station_id
                WHERE s.city_id = :city AND c.connector_type = :conn
                  AND c.status IN ('available', 'occupied')
                ORDER BY c.charger_id LIMIT 1
            """
                ),
                {"city": city_id_of(city), "conn": connector_type},
            )
            .mappings()
            .first()
        )
        if not charger:
            raise NotFound(f"No {connector_type} charger in {city}; run the seed script first")

        last = db.execute(
            text(
                "SELECT MAX(TIMESTAMP(slot_date, slot_start_time)) FROM slots "
                "WHERE charger_id = :c AND slot_date >= :d"
            ),
            {"c": charger["charger_id"], "d": DEMO_DATE_START},
        ).scalar()
        start = last + timedelta(hours=1) if last else datetime.combine(DEMO_DATE_START, time(6, 0))
        if start.hour >= 22:  # keep slots inside one day
            start = start.replace(hour=6) + timedelta(days=1)
        end = start + timedelta(hours=1)
        slot_id = db.execute(
            text(
                "INSERT INTO slots (charger_id, slot_date, slot_start_time, slot_end_time, is_available) "
                "VALUES (:c, :d, :s, :e, TRUE)"
            ),
            {"c": charger["charger_id"], "d": start.date(), "s": start.time(), "e": end.time()},
        ).lastrowid
        db.commit()
    return {
        "city": city,
        "slot_id": slot_id,
        "charger_id": charger["charger_id"],
        "charger_code": charger["charger_code"],
        "connector_type": charger["connector_type"],
        "station_name": charger["station_name"],
        "slot_date": start.date(),
        "start_time": start.strftime("%H:%M"),
        "end_time": end.strftime("%H:%M"),
    }


def slot_report(city: str, slot_id: int) -> dict:
    """How many confirmed bookings does this slot have? (>1 = double booked)"""
    city = normalize_city(city)
    with city_session(city) as db:
        avail = db.execute(text("SELECT is_available FROM slots WHERE slot_id = :s"), {"s": slot_id}).scalar()
        if avail is None:
            raise NotFound("Slot not found")
        rows = (
            db.execute(
                text(
                    "SELECT booking_id, user_id, booking_amount, created_at FROM bookings "
                    "WHERE slot_id = :s AND booking_status = 'confirmed' ORDER BY booking_id"
                ),
                {"s": slot_id},
            )
            .mappings()
            .all()
        )
    return {
        "city": city,
        "slot_id": slot_id,
        "is_available": bool(avail),
        "confirmed_bookings": len(rows),
        "double_booked": len(rows) > 1,
        "bookings": [dict(r) for r in rows],
    }
