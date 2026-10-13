"""
Station / charger / slot search.

Horizontal fragmentation in action: every query goes ONLY to the node of the
city being searched. The Bangalore node knows nothing about Delhi stations.
"""

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import text

from app.core.cities import CITIES, city_id_of, normalize_city
from app.db.mysql_connection import city_session
from app.services import pricing
from app.services.errors import NotFound


def _hhmm(t) -> str:
    # PyMySQL returns TIME columns as timedelta
    if hasattr(t, "total_seconds"):
        secs = int(t.total_seconds())
        return f"{secs // 3600:02d}:{(secs % 3600) // 60:02d}"
    return t.strftime("%H:%M")


def _as_time(t) -> time:
    if hasattr(t, "total_seconds"):
        secs = int(t.total_seconds())
        return time(secs // 3600, (secs % 3600) // 60, secs % 60)
    return t


IST = timezone(timedelta(hours=5, minutes=30))


def today_ist() -> date:
    """Today's date in India (the server/container clock may be in UTC)."""
    return datetime.now(IST).date()


def list_cities() -> list[dict]:
    return [{"key": k, "city_id": v["city_id"], "name": v["name"]} for k, v in CITIES.items()]


def search_stations(
    city: str,
    on_date: date,
    connector_type: str | None = None,
    charger_type: str | None = None,
    from_time: time | None = None,
    to_time: time | None = None,
) -> list[dict]:
    city = normalize_city(city)
    sql = """
        SELECT s.station_id, s.station_name, s.address, s.latitude, s.longitude,
               COUNT(DISTINCT c.charger_id) AS matching_chargers,
               COUNT(DISTINCT CASE WHEN sl.slot_id IS NOT NULL THEN c.charger_id END)
                                            AS available_chargers,
               COUNT(sl.slot_id)            AS available_slots,
               MAX(c.max_power_kw)          AS max_power_kw
        FROM stations s
        JOIN charger_units c
          ON c.station_id = s.station_id
         AND c.status IN ('available', 'occupied')
         AND (:conn IS NULL OR c.connector_type = :conn)
         AND (:ctype IS NULL OR c.charger_type = :ctype)
        LEFT JOIN slots sl
          ON sl.charger_id = c.charger_id
         AND sl.slot_date = :d
         AND sl.is_available = TRUE
         AND TIMESTAMP(sl.slot_date, sl.slot_start_time) > NOW()
         AND (:t_from IS NULL OR sl.slot_start_time >= :t_from)
         AND (:t_to IS NULL OR sl.slot_end_time <= :t_to)
        WHERE s.city_id = :city AND s.is_operational = TRUE
        GROUP BY s.station_id, s.station_name, s.address, s.latitude, s.longitude
        ORDER BY available_slots DESC, s.station_name
    """
    params = {
        "city": city_id_of(city),
        "d": on_date,
        "conn": connector_type,
        "ctype": charger_type,
        "t_from": from_time,
        "t_to": to_time,
    }
    with city_session(city) as db:
        rows = db.execute(text(sql), params).mappings().all()
    return [
        {
            "city": city,
            "station_id": r["station_id"],
            "station_name": r["station_name"],
            "address": r["address"],
            "latitude": float(r["latitude"]) if r["latitude"] is not None else None,
            "longitude": float(r["longitude"]) if r["longitude"] is not None else None,
            "on_date": on_date,
            "matching_chargers": r["matching_chargers"],
            "available_chargers": r["available_chargers"],
            "available_slots": r["available_slots"],
            "max_power_kw": float(r["max_power_kw"]) if r["max_power_kw"] is not None else None,
        }
        for r in rows
    ]


def get_station(city: str, station_id: int) -> dict:
    city = normalize_city(city)
    with city_session(city) as db:
        st = (
            db.execute(
                text("SELECT * FROM stations WHERE station_id = :id AND city_id = :city"),
                {"id": station_id, "city": city_id_of(city)},
            )
            .mappings()
            .first()
        )
        if not st:
            raise NotFound("Station not found in this city")
        chargers = (
            db.execute(
                text("SELECT * FROM charger_units WHERE station_id = :id ORDER BY charger_code"),
                {"id": station_id},
            )
            .mappings()
            .all()
        )
    return {
        "city": city,
        "station_id": st["station_id"],
        "station_name": st["station_name"],
        "address": st["address"],
        "latitude": float(st["latitude"]) if st["latitude"] is not None else None,
        "longitude": float(st["longitude"]) if st["longitude"] is not None else None,
        "operator_id": st["operator_id"],
        "is_operational": bool(st["is_operational"]),
        "chargers": [
            {
                "charger_id": c["charger_id"],
                "charger_code": c["charger_code"],
                "charger_type": c["charger_type"],
                "max_power_kw": float(c["max_power_kw"]),
                "connector_type": c["connector_type"],
                "status": c["status"],
            }
            for c in chargers
        ],
    }


def list_slots(
    city: str, station_id: int, on_date: date, connector_type: str | None = None, only_available: bool = True
) -> list[dict]:
    city = normalize_city(city)
    city_id = city_id_of(city)
    sql = """
        SELECT sl.slot_id, sl.charger_id, sl.slot_date, sl.slot_start_time, sl.slot_end_time,
               sl.is_available, c.charger_code, c.charger_type, c.connector_type, c.max_power_kw
        FROM slots sl
        JOIN charger_units c ON c.charger_id = sl.charger_id
        JOIN stations s ON s.station_id = c.station_id
        WHERE s.station_id = :sid AND s.city_id = :city
          AND sl.slot_date = :d
          AND TIMESTAMP(sl.slot_date, sl.slot_start_time) > NOW()
          AND c.status IN ('available', 'occupied')
          AND (:conn IS NULL OR c.connector_type = :conn)
          AND (:only_avail = FALSE OR sl.is_available = TRUE)
        ORDER BY sl.slot_start_time, c.charger_code
    """
    with city_session(city) as db:
        rows = (
            db.execute(
                text(sql),
                {
                    "sid": station_id,
                    "city": city_id,
                    "d": on_date,
                    "conn": connector_type,
                    "only_avail": only_available,
                },
            )
            .mappings()
            .all()
        )
        plans = {}
        out = []
        for r in rows:
            ctype = r["charger_type"]
            if ctype not in plans:
                plans[ctype] = pricing.get_plan(db, city_id, ctype, on_date)
            plan = plans[ctype]
            start, end = _as_time(r["slot_start_time"]), _as_time(r["slot_end_time"])
            out.append(
                {
                    "city": city,
                    "slot_id": r["slot_id"],
                    "charger_id": r["charger_id"],
                    "charger_code": r["charger_code"],
                    "charger_type": ctype,
                    "connector_type": r["connector_type"],
                    "max_power_kw": float(r["max_power_kw"]),
                    "slot_date": r["slot_date"],
                    "start_time": _hhmm(r["slot_start_time"]),
                    "end_time": _hhmm(r["slot_end_time"]),
                    "is_available": bool(r["is_available"]),
                    "estimated_max_price": float(pricing.prepaid_amount(plan, r["max_power_kw"], start, end))
                    if plan
                    else None,
                }
            )
    return out
