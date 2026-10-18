"""
Cross-city operations: the station lives on one node, the user's wallet on another.

    Bangalore user books a Chennai charger
      Chennai node   (station node) : lock slot, insert booking + payment, close slot
      Bangalore node (home node)    : lock wallet, debit
    -> one global transaction, committed with 2PC (app.services.xa).

Both nodes still use strict 2PL locally (SELECT ... FOR UPDATE, locks held to
the end), and the GLOBAL lock order is the same as the single-node rule:
slot (station node) first, wallet (home node) second.

Why that matters: InnoDB detects deadlocks only inside one node. A cycle that
spans two nodes (T1 holds Chennai slot + waits for Bangalore wallet, T2 the
reverse) is invisible to both, and would only end by lock-wait timeout
(error 1205). A single global lock order means such a cycle cannot form; the
timeout + retry is the safety net.
"""

import time
import uuid
from decimal import Decimal

from app.core.cities import city_id_of, normalize_city
from app.services import audit, pricing, xa
from app.services.errors import AppError, InsufficientBalance, NotFound, SlotUnavailable
from app.services.station_service import _as_time, _hhmm

MAX_ATTEMPTS = 3
RETRYABLE = (1213, 1205)  # deadlock victim, lock wait timeout

SLOT_SQL = """
    SELECT sl.slot_id, sl.slot_date, sl.slot_start_time, sl.slot_end_time, sl.is_available,
           (TIMESTAMP(sl.slot_date, sl.slot_start_time) > NOW()) AS is_future,
           c.charger_id, c.charger_code, c.charger_type, c.connector_type, c.max_power_kw,
           c.status AS charger_status,
           s.station_id, s.station_name, s.city_id, s.is_operational
    FROM slots sl
    JOIN charger_units c ON c.charger_id = sl.charger_id
    JOIN stations s      ON s.station_id = c.station_id
    WHERE sl.slot_id = :slot_id
    FOR UPDATE OF sl
"""


def _ms(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)


def lock_wallet(q: xa.Q, user_id: int, city: str, txn: str) -> Decimal:
    audit.record("LOCK_REQUEST", txn=txn, city=city, resource=f"users[{user_id}].wallet", lock="X")
    t0 = time.perf_counter()
    bal = q.scalar("SELECT wallet_balance FROM users WHERE user_id = :u FOR UPDATE", u=user_id)
    audit.record("LOCK_ACQUIRED", txn=txn, city=city, resource=f"users[{user_id}].wallet", waited_ms=_ms(t0))
    if bal is None:
        raise NotFound("User not found on home node")
    return bal


def _with_retry(fn, txn: str, label: str):
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return fn(attempt)
        except xa.CoordinatorCrash as crash:
            raise AppError(
                f"Simulated coordinator crash ({crash.point}). Transaction {crash.gtrid} is left "
                "prepared on the nodes; run recovery to finish it.",
                code="coordinator_crash_simulated",
                status_code=500,
            )
        except Exception as exc:
            errno = xa.mysql_errno(exc)
            if errno in RETRYABLE and attempt < MAX_ATTEMPTS:
                audit.record(
                    "RETRY",
                    txn=txn,
                    op=label,
                    attempt=attempt,
                    mysql_errno=errno,
                    reason="deadlock victim" if errno == 1213 else "lock wait timeout",
                )
                time.sleep(0.05 * (2**attempt))
                continue
            if errno == 1205:
                raise AppError("System busy, please try again", code="lock_timeout", status_code=503)
            raise


# =============================================================================
# Cross-city booking
# =============================================================================


def create_cross_city_booking(
    user: dict,
    city: str,
    slot_id: int,
    vehicle_id: int,
    txn: str | None = None,
    fail_point: str | None = None,
    delay_ms: int = 0,
) -> dict:
    station_city, home_city = normalize_city(city), user["home_city"]
    txn = txn or audit.new_txn_id()
    user_id = user["user_id"]
    city_id = city_id_of(station_city)

    def run(attempt: int) -> dict:
        with xa.transaction(station_city, home_city, "cross_city_booking", txn, fail_point) as t:
            audit.record(
                "BEGIN",
                txn=txn,
                mode="2PC",
                station_node=station_city,
                wallet_node=home_city,
                user_id=user_id,
                slot_id=slot_id,
                attempt=attempt,
                gtrid=t.gtrid,
            )
            s = t.branch(station_city)

            # lock 1 (station node): the slot
            audit.record("LOCK_REQUEST", txn=txn, city=station_city, resource=f"slots[{slot_id}]", lock="X")
            t0 = time.perf_counter()
            slot = s.q.one(SLOT_SQL, slot_id=slot_id)
            audit.record(
                "LOCK_ACQUIRED", txn=txn, city=station_city, resource=f"slots[{slot_id}]", waited_ms=_ms(t0)
            )
            if not slot or slot["city_id"] != city_id:
                raise NotFound("Slot not found in this city")
            if not slot["is_available"]:
                raise SlotUnavailable("Slot already booked")
            if not slot["is_future"]:
                raise SlotUnavailable("Slot start time has already passed", code="slot_in_past")
            if slot["charger_status"] in ("faulted", "maintenance") or not slot["is_operational"]:
                raise SlotUnavailable("Charger is out of service", code="charger_unavailable")

            vehicle = s.q.one(
                "SELECT user_id, connector_type, battery_capacity_kwh FROM vehicles " "WHERE vehicle_id = :v",
                v=vehicle_id,
            )
            if not vehicle or vehicle["user_id"] != user_id:
                raise NotFound("Vehicle not found")
            if vehicle["connector_type"] != slot["connector_type"]:
                raise AppError(
                    f"Vehicle connector {vehicle['connector_type']} does not fit this charger "
                    f"({slot['connector_type']})",
                    code="connector_mismatch",
                )
            plan = pricing.get_plan_q(s.q, city_id, slot["charger_type"], slot["slot_date"])
            if not plan:
                raise AppError("No pricing plan for this charger type", code="no_pricing_plan")
            amount = pricing.prepaid_amount(
                plan,
                slot["max_power_kw"],
                _as_time(slot["slot_start_time"]),
                _as_time(slot["slot_end_time"]),
                vehicle["battery_capacity_kwh"],
            )

            # lock 2 (home node): the wallet
            h = t.branch(home_city)
            balance = lock_wallet(h.q, user_id, home_city, txn)
            if balance < amount:
                raise InsufficientBalance(
                    f"Wallet balance Rs {balance} is less than the booking amount Rs {amount}"
                )
            if delay_ms:
                audit.record("HOLDING_LOCKS", txn=txn, delay_ms=delay_ms)
                time.sleep(delay_ms / 1000)
            h.q.exec(
                "UPDATE users SET wallet_balance = wallet_balance - :a WHERE user_id = :u",
                a=amount,
                u=user_id,
            )
            audit.record("WALLET_DEBIT", txn=txn, city=home_city, user_id=user_id, amount=float(amount))

            # writes on the station node
            _, booking_id = s.q.exec(
                "INSERT INTO bookings (user_id, slot_id, vehicle_id, booking_status, booking_amount) "
                "VALUES (:u, :s, :v, 'confirmed', :a)",
                u=user_id,
                s=slot_id,
                v=vehicle_id,
                a=amount,
            )
            ref = "WLT-" + uuid.uuid4().hex[:16].upper()
            _, payment_id = s.q.exec(
                "INSERT INTO payments (booking_id, amount, payment_method, payment_status, transaction_id) "
                "VALUES (:b, :a, 'wallet', 'completed', :r)",
                b=booking_id,
                a=amount,
                r=ref,
            )
            s.q.exec("UPDATE slots SET is_available = FALSE WHERE slot_id = :s", s=slot_id)
            audit.record(
                "BOOKING_WRITTEN", txn=txn, city=station_city, booking_id=booking_id, payment_id=payment_id
            )

            t.commit()

        return {
            "city": station_city,
            "booking_id": booking_id,
            "booking_status": "confirmed",
            "booking_amount": float(amount),
            "slot_id": slot_id,
            "vehicle_id": vehicle_id,
            "charger_id": slot["charger_id"],
            "charger_code": slot["charger_code"],
            "station_id": slot["station_id"],
            "station_name": slot["station_name"],
            "slot_date": slot["slot_date"],
            "start_time": _hhmm(slot["slot_start_time"]),
            "end_time": _hhmm(slot["slot_end_time"]),
            "payment_id": payment_id,
            "payment_status": "completed",
            "transaction_id": ref,
            "wallet_balance_after": float(balance - amount),
            "distributed": {"gtrid": t.gtrid, "wallet_node": home_city, "pending_commit": t.pending_commit},
        }

    return _with_retry(run, txn, "cross_city_booking")


# =============================================================================
# Cancel (works for same-city and cross-city; used for cross-city)
# =============================================================================


def cancel_cross_city(user: dict, city: str, booking_id: int) -> dict:
    station_city, home_city = normalize_city(city), user["home_city"]
    txn = audit.new_txn_id()
    user_id = user["user_id"]

    def run(attempt: int) -> dict:
        with xa.transaction(station_city, home_city, "cross_city_cancel", txn) as t:
            s = t.branch(station_city)
            b = s.q.one(
                "SELECT b.booking_id, b.user_id, b.slot_id, b.booking_status, b.booking_amount, "
                "(TIMESTAMP(sl.slot_date, sl.slot_start_time) > NOW()) AS is_future "
                "FROM bookings b JOIN slots sl ON sl.slot_id = b.slot_id "
                "WHERE b.booking_id = :b FOR UPDATE",
                b=booking_id,
            )
            if not b or b["user_id"] != user_id:
                raise NotFound("Booking not found")
            if b["booking_status"] != "confirmed":
                raise AppError(
                    f"Booking is already {b['booking_status']}", code="not_cancellable", status_code=409
                )
            if not b["is_future"]:
                raise AppError("Slot has already started", code="not_cancellable", status_code=409)
            amount = b["booking_amount"]
            s.q.exec("UPDATE bookings SET booking_status = 'cancelled' WHERE booking_id = :b", b=booking_id)
            s.q.exec("UPDATE slots SET is_available = TRUE WHERE slot_id = :s", s=b["slot_id"])
            pay = s.q.scalar(
                "SELECT payment_id FROM payments WHERE booking_id = :b AND payment_status = 'completed' "
                "FOR UPDATE",
                b=booking_id,
            )
            if pay is not None:
                s.q.exec("UPDATE payments SET payment_status = 'refunded' WHERE payment_id = :p", p=pay)
                s.q.exec(
                    "INSERT INTO refunds (payment_id, refund_amount, refund_reason, refund_status, processed_at) "
                    "VALUES (:p, :a, 'Cancelled by user', 'completed', NOW())",
                    p=pay,
                    a=amount,
                )

            h = t.branch(home_city)
            balance = lock_wallet(h.q, user_id, home_city, txn)
            h.q.exec(
                "UPDATE users SET wallet_balance = wallet_balance + :a WHERE user_id = :u",
                a=amount,
                u=user_id,
            )
            t.commit()
        return {
            "city": station_city,
            "booking_id": booking_id,
            "booking_status": "cancelled",
            "refund_amount": float(amount),
            "wallet_balance_after": float(balance + amount),
        }

    return _with_retry(run, txn, "cross_city_cancel")
