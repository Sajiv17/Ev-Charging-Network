"""
Charging sessions: the driver arrives (start) and unplugs (end).

START  (one node: the station's)
  lock booking (+ slot) -> must be 'confirmed', yours, and inside the slot window
  lock charger           -> must not be faulted / busy
  booking -> 'active', session_start_time = NOW(); charger -> 'occupied'

END    (station node + home node: 2PC if they differ)
  lock booking -> must be 'active'
  final bill   = booking_fee + rate_per_kwh x energy actually delivered
                 (never more than what was prepaid)
  refund       = prepaid - final bill  -> refunds row on the station node,
                                          wallet credit on the home node
  booking -> 'completed' with energy_consumed_kwh; charger -> 'available'

Lock order everywhere: booking/slot, then charger, then wallet.
"""

from decimal import ROUND_HALF_UP, Decimal

from app.core.cities import city_id_of, normalize_city
from app.core.config import settings
from app.services import audit, live_status, pricing, xa
from app.services.cross_city import _with_retry, lock_wallet
from app.services.errors import AppError, NotFound
from app.services.station_service import _as_time

EARLY_START_MIN = 15  # driver may plug in up to 15 minutes before the slot


_BOOKING_SQL = """
    SELECT b.booking_id, b.user_id, b.vehicle_id, b.booking_status, b.booking_amount,
           b.session_start_time,
           sl.slot_id, sl.slot_date, sl.slot_start_time, sl.slot_end_time,
           (NOW() >= TIMESTAMP(sl.slot_date, sl.slot_start_time) - INTERVAL :early MINUTE) AS window_open,
           (NOW() < TIMESTAMP(sl.slot_date, sl.slot_end_time)) AS window_not_over,
           c.charger_id, c.charger_code, c.charger_type, c.max_power_kw, c.status AS charger_status,
           v.battery_capacity_kwh
    FROM bookings b
    JOIN slots sl         ON sl.slot_id = b.slot_id
    JOIN charger_units c  ON c.charger_id = sl.charger_id
    JOIN vehicles v       ON v.vehicle_id = b.vehicle_id
    WHERE b.booking_id = :b
    FOR UPDATE OF b, sl
"""


def start_session(user: dict, city: str, booking_id: int, force: bool = False) -> dict:
    city = normalize_city(city)
    txn = audit.new_txn_id()
    if force and not settings.DEMO_MODE:
        raise AppError("force is only allowed in DEMO_MODE", code="forbidden", status_code=403)

    def run(attempt):
        with xa.LocalTxn(city, "session_start", txn) as t:
            q = t.branch(city).q
            b = q.one(_BOOKING_SQL, b=booking_id, early=EARLY_START_MIN)
            if not b or (b["user_id"] != user["user_id"] and user["role"] != "admin"):
                raise NotFound("Booking not found")
            if b["booking_status"] != "confirmed":
                raise AppError(
                    f"Booking is {b['booking_status']}, cannot start", code="not_startable", status_code=409
                )
            if not force and not (b["window_open"] and b["window_not_over"]):
                raise AppError(
                    f"You can start between {EARLY_START_MIN} min before the slot and its end",
                    code="outside_slot_window",
                    status_code=409,
                )
            charger = q.one(
                "SELECT status FROM charger_units WHERE charger_id = :c FOR UPDATE", c=b["charger_id"]
            )
            if charger["status"] in ("faulted", "maintenance"):
                raise AppError("Charger is out of service", code="charger_unavailable", status_code=409)
            busy = q.scalar(
                "SELECT COUNT(*) FROM bookings bb JOIN slots s2 ON s2.slot_id = bb.slot_id "
                "WHERE s2.charger_id = :c AND bb.booking_status = 'active'",
                c=b["charger_id"],
            )
            if busy:
                raise AppError("Another vehicle is still charging here", code="charger_busy", status_code=409)

            q.exec(
                "UPDATE bookings SET booking_status = 'active', session_start_time = NOW() "
                "WHERE booking_id = :b",
                b=booking_id,
            )
            q.exec("UPDATE charger_units SET status = 'occupied' WHERE charger_id = :c", c=b["charger_id"])
            started = q.scalar("SELECT session_start_time FROM bookings WHERE booking_id = :b", b=booking_id)
            t.commit()
        audit.record("SESSION_STARTED", txn=txn, city=city, booking_id=booking_id, charger_id=b["charger_id"])
        live_status.session_started(city, {**b, "booking_id": booking_id})
        return {
            "city": city,
            "booking_id": booking_id,
            "booking_status": "active",
            "charger_id": b["charger_id"],
            "charger_code": b["charger_code"],
            "session_start_time": started,
        }

    return _with_retry(run, txn, "session_start")


def end_session(user: dict, city: str, booking_id: int, energy_kwh: float) -> dict:
    city = normalize_city(city)
    txn = audit.new_txn_id()
    home_city = user["home_city"]
    energy = Decimal(str(energy_kwh)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def run(attempt):
        with xa.transaction(city, home_city, "session_end", txn) as t:
            s = t.branch(city)
            b = s.q.one(_BOOKING_SQL, b=booking_id, early=EARLY_START_MIN)
            if not b or b["user_id"] != user["user_id"]:
                raise NotFound("Booking not found")
            if b["booking_status"] != "active":
                raise AppError(
                    f"Booking is {b['booking_status']}, no session to end", code="not_active", status_code=409
                )
            max_kwh = pricing.max_energy_kwh(
                b["max_power_kw"],
                _as_time(b["slot_start_time"]),
                _as_time(b["slot_end_time"]),
                b["battery_capacity_kwh"],
            )
            if energy > max_kwh:
                raise AppError(
                    f"{energy} kWh is more than this slot can deliver ({max_kwh.quantize(Decimal('0.01'))} kWh)",
                    code="energy_too_high",
                )
            plan = pricing.get_plan_q(s.q, city_id_of(city), b["charger_type"], b["slot_date"])
            paid = Decimal(b["booking_amount"])
            cost = min(pricing.energy_cost(plan, energy), paid) if plan else paid
            refund = (paid - cost).quantize(Decimal("0.01"))

            s.q.exec(
                "UPDATE bookings SET booking_status = 'completed', energy_consumed_kwh = :e, "
                "session_end_time = GREATEST(NOW(), session_start_time) WHERE booking_id = :b",
                e=energy,
                b=booking_id,
            )
            s.q.exec(
                "UPDATE charger_units SET status = 'available' WHERE charger_id = :c AND status = 'occupied'",
                c=b["charger_id"],
            )
            balance_after = None
            if refund > 0:
                pay = s.q.scalar(
                    "SELECT payment_id FROM payments WHERE booking_id = :b AND payment_status = "
                    "'completed' ORDER BY payment_id LIMIT 1 FOR UPDATE",
                    b=booking_id,
                )
                if pay is not None:
                    s.q.exec(
                        "INSERT INTO refunds (payment_id, refund_amount, refund_reason, refund_status, "
                        "processed_at) VALUES (:p, :a, :r, 'completed', NOW())",
                        p=pay,
                        a=refund,
                        r=f"Unused prepaid energy: billed {energy} kWh",
                    )
                h = t.branch(home_city)
                bal = lock_wallet(h.q, user["user_id"], home_city, txn)
                h.q.exec(
                    "UPDATE users SET wallet_balance = wallet_balance + :a WHERE user_id = :u",
                    a=refund,
                    u=user["user_id"],
                )
                balance_after = bal + refund
            t.commit()
        audit.record(
            "SESSION_ENDED",
            txn=txn,
            city=city,
            booking_id=booking_id,
            energy_kwh=float(energy),
            final_cost=float(cost),
            refund=float(refund),
        )
        live_status.session_ended(city, booking_id, float(energy), float(cost))
        return {
            "city": city,
            "booking_id": booking_id,
            "booking_status": "completed",
            "energy_consumed_kwh": float(energy),
            "prepaid": float(paid),
            "final_cost": float(cost),
            "refund_amount": float(refund),
            "wallet_balance_after": float(balance_after) if balance_after is not None else None,
        }

    return _with_retry(run, txn, "session_end")
