"""Payments history, charger status, operator alerts and charger fault reporting."""

import logging

from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.core.cities import CITIES, city_id_of, normalize_city
from app.db.mysql_connection import city_session
from app.services import audit, live_status, recovery_service
from app.services.errors import AppError, Forbidden, NotFound

log = logging.getLogger("ops")


# --------------------------------------------------------------------------- payments


def list_user_payments(user_id: int) -> list[dict]:
    """Payments live next to their booking (station node), so ask every node."""
    sql = """
        SELECT p.payment_id, p.booking_id, p.amount, p.payment_method, p.payment_status,
               p.transaction_id, p.payment_timestamp, s.station_name,
               COALESCE(SUM(CASE WHEN r.refund_status = 'completed' THEN r.refund_amount END), 0) AS refunded,
               COALESCE(SUM(CASE WHEN r.refund_status = 'queued' THEN r.refund_amount END), 0) AS refund_pending
        FROM payments p
        JOIN bookings b      ON b.booking_id = p.booking_id
        JOIN slots sl        ON sl.slot_id = b.slot_id
        JOIN charger_units c ON c.charger_id = sl.charger_id
        JOIN stations s      ON s.station_id = c.station_id
        LEFT JOIN refunds r  ON r.payment_id = p.payment_id
        WHERE b.user_id = :u
        GROUP BY p.payment_id, p.booking_id, p.amount, p.payment_method, p.payment_status,
                 p.transaction_id, p.payment_timestamp, s.station_name
    """
    out = []
    for city in CITIES:
        try:
            with city_session(city) as db:
                for r in db.execute(text(sql), {"u": user_id}).mappings():
                    out.append(
                        {
                            "city": city,
                            **{
                                k: r[k]
                                for k in (
                                    "payment_id",
                                    "booking_id",
                                    "payment_method",
                                    "payment_status",
                                    "transaction_id",
                                    "payment_timestamp",
                                    "station_name",
                                )
                            },
                            "amount": float(r["amount"]),
                            "refunded": float(r["refunded"]),
                            "refund_pending": float(r["refund_pending"]),
                        }
                    )
        except OperationalError:
            log.warning("node %s unreachable while listing payments", city)
    out.sort(key=lambda p: p["payment_timestamp"], reverse=True)
    return out


# --------------------------------------------------------------------------- chargers


def get_charger(city: str, charger_id: int) -> dict:
    city = normalize_city(city)
    with city_session(city) as db:
        c = (
            db.execute(
                text(
                    "SELECT c.charger_id, c.charger_code, c.charger_type, c.connector_type, c.max_power_kw, c.status, "
                    "c.updated_at, s.station_id, s.station_name, s.operator_id "
                    "FROM charger_units c JOIN stations s ON s.station_id = c.station_id "
                    "WHERE c.charger_id = :c AND s.city_id = :city"
                ),
                {"c": charger_id, "city": city_id_of(city)},
            )
            .mappings()
            .first()
        )
        if not c:
            raise NotFound("Charger not found in this city")
        active = (
            db.execute(
                text(
                    "SELECT b.booking_id, b.session_start_time FROM bookings b JOIN slots sl ON sl.slot_id = b.slot_id "
                    "WHERE sl.charger_id = :c AND b.booking_status = 'active' LIMIT 1"
                ),
                {"c": charger_id},
            )
            .mappings()
            .first()
        )
    return {
        "city": city,
        **{
            k: c[k]
            for k in (
                "charger_id",
                "charger_code",
                "charger_type",
                "connector_type",
                "status",
                "updated_at",
                "station_id",
                "station_name",
            )
        },
        "max_power_kw": float(c["max_power_kw"]),
        "active_session": dict(active) if active else None,
        "live": live_status.charger_live(city, charger_id),  # MongoDB telemetry, None if unavailable
    }


# --------------------------------------------------------------------------- operator


def _can_manage(user: dict, operator_id: int) -> bool:
    return user["role"] == "admin" or (user["role"] == "operator" and user["user_id"] == operator_id)


def set_charger_status(user: dict, city: str, charger_id: int, status: str) -> dict:
    for attempt in range(3):
        try:
            return _set_charger_status(user, city, charger_id, status)
        except OperationalError as exc:
            # The trigger locks bookings after the charger; a session starting at the same
            # moment locks them the other way round -> MySQL may pick us as deadlock victim.
            if getattr(exc.orig, "args", [None])[0] == 1213 and attempt < 2:
                continue
            raise


def _set_charger_status(user: dict, city: str, charger_id: int, status: str) -> dict:
    """
    Operator marks a charger faulted / repaired / in maintenance.
    The UPDATE fires after_charger_fault (Vyaan's trigger): affected bookings are
    cancelled and refunded, and an operator_alerts row is written. Refunds for
    users from other cities are queued by the trigger and paid right away here
    by the recovery service (2PC to their home node).
    """
    city = normalize_city(city)
    with city_session(city) as db:
        c = (
            db.execute(
                text(
                    "SELECT c.status, s.operator_id FROM charger_units c "
                    "JOIN stations s ON s.station_id = c.station_id "
                    "WHERE c.charger_id = :c AND s.city_id = :city FOR UPDATE OF c"
                ),
                {"c": charger_id, "city": city_id_of(city)},
            )
            .mappings()
            .first()
        )
        if not c:
            raise NotFound("Charger not found in this city")
        if not _can_manage(user, c["operator_id"]):
            raise Forbidden("You do not operate this station")
        if c["status"] == status:
            raise AppError(f"Charger is already {status}", code="no_change", status_code=409)
        if status == "available" and c["status"] == "occupied":
            raise AppError("End the charging session instead", code="session_running", status_code=409)
        db.execute(
            text("UPDATE charger_units SET status = :s WHERE charger_id = :c"), {"s": status, "c": charger_id}
        )
        alert = (
            db.execute(
                text("SELECT * FROM operator_alerts WHERE charger_id = :c ORDER BY alert_id DESC LIMIT 1"),
                {"c": charger_id},
            )
            .mappings()
            .first()
        )
        db.commit()
    audit.record("CHARGER_STATUS", city=city, charger_id=charger_id, old=c["status"], new=status)
    settled = []
    if status == "faulted":
        settled = recovery_service.settle_queued_refunds()["settled"]
    return {
        "city": city,
        "charger_id": charger_id,
        "old_status": c["status"],
        "status": status,
        "alert": dict(alert) if alert and status in ("faulted", "available") else None,
        "cross_city_refunds_paid": settled,
    }


def list_alerts(user: dict, unread_only: bool = False) -> list[dict]:
    out = []
    for city in CITIES:
        try:
            with city_session(city) as db:
                rows = db.execute(
                    text(
                        "SELECT a.*, c.charger_code, s.station_name FROM operator_alerts a "
                        "JOIN charger_units c ON c.charger_id = a.charger_id "
                        "JOIN stations s ON s.station_id = c.station_id "
                        "WHERE (:admin = 1 OR a.operator_id = :u) AND (:unread = 0 OR a.acknowledged_at IS NULL) "
                        "ORDER BY a.alert_id DESC LIMIT 100"
                    ),
                    {"admin": int(user["role"] == "admin"), "u": user["user_id"], "unread": int(unread_only)},
                ).mappings()
                out.extend({"city": city, **dict(r)} for r in rows)
        except OperationalError:
            log.warning("node %s unreachable while listing alerts", city)
    out.sort(key=lambda a: a["created_at"], reverse=True)
    return out


def acknowledge_alert(user: dict, city: str, alert_id: int) -> dict:
    city = normalize_city(city)
    with city_session(city) as db:
        a = (
            db.execute(
                text("SELECT operator_id FROM operator_alerts WHERE alert_id = :a FOR UPDATE"),
                {"a": alert_id},
            )
            .mappings()
            .first()
        )
        if not a:
            raise NotFound("Alert not found")
        if not _can_manage(user, a["operator_id"]):
            raise Forbidden("Not your alert")
        db.execute(
            text(
                "UPDATE operator_alerts SET acknowledged_at = COALESCE(acknowledged_at, NOW()) "
                "WHERE alert_id = :a"
            ),
            {"a": alert_id},
        )
        db.commit()
    return {"city": city, "alert_id": alert_id, "acknowledged": True}
