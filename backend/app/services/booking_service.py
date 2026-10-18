"""
Booking transactions - the heart of the concurrency-control part of the project.

create_booking_with_lock()  -> correct version, uses Strict Two-Phase Locking
                               (wallet on another node -> 2PC, see cross_city.py)
create_booking_unsafe()     -> deliberately broken version for the demo
                               (no locks -> double booking + lost update)
cancel_booking()            -> cancel + refund, same locking rules


STRICT TWO-PHASE LOCKING (2PL), as InnoDB implements it
-------------------------------------------------------
Growing phase : the transaction acquires locks as it goes
                (SELECT ... FOR UPDATE = exclusive row lock) and never
                releases any of them early.
Shrinking phase: ALL locks are released together at COMMIT/ROLLBACK.
                Releasing only at the end is what makes it *strict* 2PL:
                nobody can read our uncommitted changes, so there are no
                cascading rollbacks.

Lock order is ALWAYS: slot row -> wallet (user) row.
Every transaction that needs both takes them in this order, so two booking
transactions can never wait on each other in a cycle (= no deadlock between
our own transactions). MySQL can still pick a deadlock victim in rare
cases (gap locks, foreign-key checks), so we also retry on error 1213.
"""

import logging
import time
import uuid
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.cities import city_id_of, normalize_city
from app.db.mysql_connection import city_session
from app.services import audit, cross_city, pricing
from app.services.errors import (
    AppError,
    Forbidden,
    InsufficientBalance,
    NotFound,
    SlotUnavailable,
)
from app.services.station_service import _as_time, _hhmm

log = logging.getLogger("booking")

MYSQL_DEADLOCK = 1213  # "Deadlock found when trying to get lock"
MYSQL_LOCK_WAIT_TIMEOUT = 1205  # "Lock wait timeout exceeded"
MAX_ATTEMPTS = 3
LOCK_WAIT_TIMEOUT_S = 10


def _mysql_errno(exc: OperationalError) -> int | None:
    orig = getattr(exc, "orig", None)
    return orig.args[0] if orig is not None and orig.args else None


def _reason(exc: Exception) -> str:
    """Short, readable rollback reason for the audit log."""
    if getattr(exc, "message", None):
        return exc.message
    orig = getattr(exc, "orig", None)
    if orig is not None and getattr(orig, "args", None) and len(orig.args) >= 2:
        return f"MySQL {orig.args[0]}: {orig.args[1]}"
    return repr(exc)[:200]


def _ms_since(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)


def _require_same_city(user: dict, city: str) -> None:
    if user["home_city"] != city:
        raise AppError(
            f"The UNSAFE demo path only books in your home city ({user['home_city']}); "
            "cross-city bookings always use 2PC (mode=locked).",
            code="unsafe_same_city_only",
        )


# =============================================================================
# Shared SQL
# =============================================================================

_SLOT_SQL = """
    SELECT sl.slot_id, sl.slot_date, sl.slot_start_time, sl.slot_end_time, sl.is_available,
           (TIMESTAMP(sl.slot_date, sl.slot_start_time) > NOW()) AS is_future,
           c.charger_id, c.charger_code, c.charger_type, c.connector_type, c.max_power_kw,
           c.status AS charger_status,
           s.station_id, s.station_name, s.city_id, s.is_operational
    FROM slots sl
    JOIN charger_units c ON c.charger_id = sl.charger_id
    JOIN stations s      ON s.station_id = c.station_id
    WHERE sl.slot_id = :slot_id
"""


def _check_slot(slot, city_id: int) -> None:
    if not slot or slot["city_id"] != city_id:
        raise NotFound("Slot not found in this city")
    if not slot["is_available"]:
        raise SlotUnavailable("Slot already booked")
    if not slot["is_future"]:
        raise SlotUnavailable("Slot start time has already passed", code="slot_in_past")
    if slot["charger_status"] in ("faulted", "maintenance") or not slot["is_operational"]:
        raise SlotUnavailable("Charger is out of service", code="charger_unavailable")


def _load_vehicle(db: Session, user_id: int, vehicle_id: int, connector_type: str):
    v = (
        db.execute(
            text(
                "SELECT vehicle_id, user_id, connector_type, battery_capacity_kwh "
                "FROM vehicles WHERE vehicle_id = :v"
            ),
            {"v": vehicle_id},
        )
        .mappings()
        .first()
    )
    if not v or v["user_id"] != user_id:
        raise NotFound("Vehicle not found")
    if v["connector_type"] != connector_type:
        raise AppError(
            f"Vehicle connector {v['connector_type']} does not fit this charger ({connector_type})",
            code="connector_mismatch",
        )
    return v


def _price(db: Session, slot, vehicle, city_id: int) -> Decimal:
    plan = pricing.get_plan(db, city_id, slot["charger_type"], slot["slot_date"])
    if not plan:
        raise AppError("No pricing plan for this charger type", code="no_pricing_plan")
    return pricing.prepaid_amount(
        plan,
        slot["max_power_kw"],
        _as_time(slot["slot_start_time"]),
        _as_time(slot["slot_end_time"]),
        vehicle["battery_capacity_kwh"],
    )


def _insert_booking_and_payment(
    db: Session, user_id: int, slot, vehicle_id: int, amount: Decimal
) -> tuple[int, int, str]:
    booking_id = db.execute(
        text(
            "INSERT INTO bookings (user_id, slot_id, vehicle_id, booking_status, booking_amount) "
            "VALUES (:u, :s, :v, 'confirmed', :amt)"
        ),
        {"u": user_id, "s": slot["slot_id"], "v": vehicle_id, "amt": amount},
    ).lastrowid
    txn_ref = "WLT-" + uuid.uuid4().hex[:16].upper()
    payment_id = db.execute(
        text(
            "INSERT INTO payments (booking_id, amount, payment_method, payment_status, transaction_id) "
            "VALUES (:b, :amt, 'wallet', 'completed', :ref)"
        ),
        {"b": booking_id, "amt": amount, "ref": txn_ref},
    ).lastrowid
    return booking_id, payment_id, txn_ref


def _result(city: str, slot, booking_id, payment_id, txn_ref, amount, vehicle_id, balance_after):
    return {
        "city": city,
        "booking_id": booking_id,
        "booking_status": "confirmed",
        "booking_amount": float(amount),
        "slot_id": slot["slot_id"],
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
        "transaction_id": txn_ref,
        "wallet_balance_after": float(balance_after),
    }


# =============================================================================
# 1. CORRECT VERSION - Strict 2PL with row locks
# =============================================================================


def create_booking_with_lock(
    user: dict,
    city: str,
    slot_id: int,
    vehicle_id: int,
    delay_ms: int = 0,
    txn: str | None = None,
    lock_order: str = "slot_first",
    lock_gap_ms: int = 0,
    fail_point: str | None = None,
) -> dict:
    """
    Book a slot atomically. Retries automatically if MySQL picks this
    transaction as a deadlock victim.

    Wallet on another node (user's home city != station city) -> two-phase
    commit across both nodes, see app/services/cross_city.py.

    Demo-only knobs:
      delay_ms    sleep while HOLDING both locks, so the second transaction
                  can be seen waiting in the audit log.
      lock_order  "wallet_first" breaks the global lock-order rule on purpose
                  (deadlock demo). Never used by the real API.
      lock_gap_ms sleep between the first and the second lock, so two
                  transactions each grab their first lock before either
                  asks for its second one.
      fail_point  simulate a coordinator crash during 2PC (recovery demo).
    """
    city = normalize_city(city)
    txn = txn or audit.new_txn_id()
    if user["home_city"] != city or fail_point:
        return cross_city.create_cross_city_booking(
            user, city, slot_id, vehicle_id, txn=txn, fail_point=fail_point, delay_ms=delay_ms
        )

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return _locked_booking_txn(
                user, city, slot_id, vehicle_id, delay_ms, txn, attempt, lock_order, lock_gap_ms
            )
        except OperationalError as exc:
            errno = _mysql_errno(exc)
            if errno in (MYSQL_DEADLOCK, MYSQL_LOCK_WAIT_TIMEOUT) and attempt < MAX_ATTEMPTS:
                backoff = 0.05 * (2**attempt)
                audit.record(
                    "RETRY",
                    txn=txn,
                    city=city,
                    attempt=attempt,
                    mysql_errno=errno,
                    reason="deadlock victim" if errno == MYSQL_DEADLOCK else "lock wait timeout",
                    backoff_ms=int(backoff * 1000),
                )
                time.sleep(backoff)
                continue
            if errno == MYSQL_LOCK_WAIT_TIMEOUT:
                raise AppError("System busy, please try again", code="lock_timeout", status_code=503)
            raise
    raise AppError("Could not complete booking", code="retry_exhausted", status_code=503)


def _lock_wallet(db, txn, city, user_id):
    audit.record("LOCK_REQUEST", txn=txn, city=city, resource=f"users[{user_id}].wallet", lock="X")
    t0 = time.perf_counter()
    balance = db.execute(
        text("SELECT wallet_balance FROM users WHERE user_id = :u FOR UPDATE"), {"u": user_id}
    ).scalar_one_or_none()
    audit.record(
        "LOCK_ACQUIRED", txn=txn, city=city, resource=f"users[{user_id}].wallet", waited_ms=_ms_since(t0)
    )
    return balance


def _locked_booking_txn(
    user, city, slot_id, vehicle_id, delay_ms, txn, attempt, lock_order="slot_first", lock_gap_ms=0
) -> dict:
    user_id = user["user_id"]
    city_id = city_id_of(city)
    with city_session(city) as db:
        try:
            db.execute(text(f"SET SESSION innodb_lock_wait_timeout = {LOCK_WAIT_TIMEOUT_S}"))
            audit.record(
                "BEGIN",
                txn=txn,
                city=city,
                mode="locked" if lock_order == "slot_first" else "WRONG_LOCK_ORDER",
                user_id=user_id,
                slot_id=slot_id,
                attempt=attempt,
            )

            balance = None
            if lock_order == "wallet_first":
                # DEADLOCK DEMO ONLY: wallet before slot breaks the global lock order.
                balance = _lock_wallet(db, txn, city, user_id)
                if lock_gap_ms:
                    time.sleep(lock_gap_ms / 1000)

            # ---- GROWING PHASE: lock 1 = the slot row ----------------------------
            # FOR UPDATE OF sl -> exclusive lock on the slots row only (not the
            # joined charger/station rows). If another transaction holds it, we
            # WAIT here until it commits, then read the NEW committed value.
            audit.record("LOCK_REQUEST", txn=txn, city=city, resource=f"slots[{slot_id}]", lock="X")
            t0 = time.perf_counter()
            slot = db.execute(text(_SLOT_SQL + " FOR UPDATE OF sl"), {"slot_id": slot_id}).mappings().first()
            audit.record(
                "LOCK_ACQUIRED", txn=txn, city=city, resource=f"slots[{slot_id}]", waited_ms=_ms_since(t0)
            )

            _check_slot(slot, city_id)
            vehicle = _load_vehicle(db, user_id, vehicle_id, slot["connector_type"])
            amount = _price(db, slot, vehicle, city_id)

            # ---- GROWING PHASE: lock 2 = the wallet row ---------------------------
            if lock_order == "slot_first":
                if lock_gap_ms:
                    time.sleep(lock_gap_ms / 1000)
                balance = _lock_wallet(db, txn, city, user_id)
            if balance is None:
                raise NotFound("User not found on this node")
            if balance < amount:
                raise InsufficientBalance(
                    f"Wallet balance Rs {balance} is less than the booking amount Rs {amount}"
                )

            if delay_ms:
                audit.record("HOLDING_LOCKS", txn=txn, city=city, delay_ms=delay_ms)
                time.sleep(delay_ms / 1000)

            # ---- All checks passed: do the writes ---------------------------------
            db.execute(
                text("UPDATE users SET wallet_balance = wallet_balance - :amt WHERE user_id = :u"),
                {"amt": amount, "u": user_id},
            )
            audit.record("WALLET_DEBIT", txn=txn, city=city, user_id=user_id, amount=float(amount))

            booking_id, payment_id, txn_ref = _insert_booking_and_payment(
                db, user_id, slot, vehicle_id, amount
            )
            db.execute(text("UPDATE slots SET is_available = FALSE WHERE slot_id = :s"), {"s": slot_id})
            audit.record("BOOKING_WRITTEN", txn=txn, city=city, booking_id=booking_id, payment_id=payment_id)

            # ---- SHRINKING PHASE: commit releases ALL locks at once ---------------
            db.commit()
            audit.record("COMMIT", txn=txn, city=city, booking_id=booking_id, locks_released=True)
            return _result(city, slot, booking_id, payment_id, txn_ref, amount, vehicle_id, balance - amount)

        except Exception as exc:
            db.rollback()
            audit.record(
                "ROLLBACK",
                txn=txn,
                city=city,
                reason=_reason(exc),
                locks_released=True,
            )
            raise


# =============================================================================
# 2. BROKEN VERSION - for the demo only. NEVER used by the real API.
# =============================================================================


def create_booking_unsafe(
    user: dict, city: str, slot_id: int, vehicle_id: int, delay_ms: int = 0, txn: str | None = None
) -> dict:
    """
    Same steps, but with NO concurrency control:
      - reads the slot with a plain SELECT (no lock), so two transactions
        can both see "available"  -> DOUBLE BOOKING
      - reads the balance, computes the new value in Python and writes it
        back (read-modify-write)    -> LOST UPDATE on the wallet
    delay_ms widens the gap between "check" and "write" so the race
    happens every time in the demo, not just sometimes.
    """
    city = normalize_city(city)
    _require_same_city(user, city)
    txn = txn or audit.new_txn_id()
    user_id = user["user_id"]
    city_id = city_id_of(city)

    with city_session(city) as db:
        try:
            audit.record("BEGIN", txn=txn, city=city, mode="UNSAFE", user_id=user_id, slot_id=slot_id)

            slot = db.execute(text(_SLOT_SQL), {"slot_id": slot_id}).mappings().first()  # no lock!
            audit.record(
                "READ_NO_LOCK",
                txn=txn,
                city=city,
                resource=f"slots[{slot_id}]",
                saw_available=bool(slot and slot["is_available"]),
            )
            _check_slot(slot, city_id)
            vehicle = _load_vehicle(db, user_id, vehicle_id, slot["connector_type"])
            amount = _price(db, slot, vehicle, city_id)

            balance = db.execute(
                text("SELECT wallet_balance FROM users WHERE user_id = :u"), {"u": user_id}
            ).scalar_one()  # no lock!
            if balance < amount:
                raise InsufficientBalance(f"Wallet balance Rs {balance} is less than Rs {amount}")

            if delay_ms:
                audit.record("RACE_WINDOW", txn=txn, city=city, delay_ms=delay_ms)
                time.sleep(delay_ms / 1000)

            new_balance = balance - amount  # computed from a value that may be stale
            db.execute(
                text("UPDATE users SET wallet_balance = :b WHERE user_id = :u"),
                {"b": new_balance, "u": user_id},
            )
            # Slot is updated BEFORE the booking insert on purpose: the booking's
            # foreign key check takes a shared lock on the slot row, and taking
            # S-then-X in two transactions would deadlock and hide the anomaly.
            db.execute(text("UPDATE slots SET is_available = FALSE WHERE slot_id = :s"), {"s": slot_id})
            booking_id, payment_id, txn_ref = _insert_booking_and_payment(
                db, user_id, slot, vehicle_id, amount
            )
            db.commit()
            audit.record("COMMIT", txn=txn, city=city, booking_id=booking_id, mode="UNSAFE")
            return _result(city, slot, booking_id, payment_id, txn_ref, amount, vehicle_id, new_balance)
        except Exception as exc:
            db.rollback()
            audit.record("ROLLBACK", txn=txn, city=city, reason=_reason(exc))
            raise


# =============================================================================
# 3. Cancel + refund
# =============================================================================


def cancel_booking(user: dict, city: str, booking_id: int) -> dict:
    """
    Cancel before the slot starts -> full refund to wallet, slot freed.
    Lock order: booking -> slot -> wallet (slot before wallet, same as booking).
    """
    city = normalize_city(city)
    if user["home_city"] != city:
        return cross_city.cancel_cross_city(user, city, booking_id)
    txn = audit.new_txn_id()
    user_id = user["user_id"]

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with city_session(city) as db:
                try:
                    db.execute(text(f"SET SESSION innodb_lock_wait_timeout = {LOCK_WAIT_TIMEOUT_S}"))
                    audit.record("BEGIN", txn=txn, city=city, op="cancel", booking_id=booking_id)
                    b = (
                        db.execute(
                            text(
                                "SELECT b.booking_id, b.user_id, b.slot_id, b.booking_status, b.booking_amount, "
                                "(TIMESTAMP(sl.slot_date, sl.slot_start_time) > NOW()) AS is_future "
                                "FROM bookings b JOIN slots sl ON sl.slot_id = b.slot_id "
                                "WHERE b.booking_id = :b FOR UPDATE"
                            ),
                            {"b": booking_id},
                        )
                        .mappings()
                        .first()
                    )
                    if not b or b["user_id"] != user_id:
                        raise NotFound("Booking not found")
                    if b["booking_status"] != "confirmed":
                        raise AppError(
                            f"Booking is already {b['booking_status']}",
                            code="not_cancellable",
                            status_code=409,
                        )
                    if not b["is_future"]:
                        raise AppError("Slot has already started", code="not_cancellable", status_code=409)
                    audit.record(
                        "LOCK_ACQUIRED",
                        txn=txn,
                        city=city,
                        resource=f"bookings[{booking_id}] + slots[{b['slot_id']}]",
                    )

                    balance = db.execute(
                        text("SELECT wallet_balance FROM users WHERE user_id = :u FOR UPDATE"), {"u": user_id}
                    ).scalar_one()
                    amount = b["booking_amount"]

                    db.execute(
                        text("UPDATE bookings SET booking_status = 'cancelled' WHERE booking_id = :b"),
                        {"b": booking_id},
                    )
                    db.execute(
                        text("UPDATE slots SET is_available = TRUE WHERE slot_id = :s"), {"s": b["slot_id"]}
                    )
                    db.execute(
                        text("UPDATE users SET wallet_balance = wallet_balance + :a WHERE user_id = :u"),
                        {"a": amount, "u": user_id},
                    )
                    pay = db.execute(
                        text(
                            "SELECT payment_id FROM payments WHERE booking_id = :b "
                            "AND payment_status = 'completed' FOR UPDATE"
                        ),
                        {"b": booking_id},
                    ).scalar_one_or_none()
                    if pay is not None:
                        db.execute(
                            text("UPDATE payments SET payment_status = 'refunded' WHERE payment_id = :p"),
                            {"p": pay},
                        )
                        db.execute(
                            text(
                                "INSERT INTO refunds (payment_id, refund_amount, refund_reason, refund_status, "
                                "processed_at) VALUES (:p, :a, 'Cancelled by user', 'completed', NOW())"
                            ),
                            {"p": pay, "a": amount},
                        )
                    db.commit()
                    audit.record("COMMIT", txn=txn, city=city, op="cancel", refund=float(amount))
                    return {
                        "city": city,
                        "booking_id": booking_id,
                        "booking_status": "cancelled",
                        "refund_amount": float(amount),
                        "wallet_balance_after": float(balance + amount),
                    }
                except Exception as exc:
                    db.rollback()
                    audit.record(
                        "ROLLBACK",
                        txn=txn,
                        city=city,
                        reason=_reason(exc),
                    )
                    raise
        except OperationalError as exc:
            if _mysql_errno(exc) == MYSQL_DEADLOCK and attempt < MAX_ATTEMPTS:
                audit.record("RETRY", txn=txn, city=city, attempt=attempt, reason="deadlock victim")
                time.sleep(0.05 * (2**attempt))
                continue
            raise
    raise AppError("Could not cancel booking", code="retry_exhausted", status_code=503)


# =============================================================================
# 4. Reads
# =============================================================================

_BOOKING_LIST_SQL = """
    SELECT b.booking_id, b.booking_status, b.booking_amount, b.slot_id, b.vehicle_id, b.created_at,
           sl.slot_date, sl.slot_start_time, sl.slot_end_time,
           c.charger_id, c.charger_code, s.station_id, s.station_name,
           p.payment_id, p.payment_status, p.transaction_id
    FROM bookings b
    JOIN slots sl         ON sl.slot_id = b.slot_id
    JOIN charger_units c  ON c.charger_id = sl.charger_id
    JOIN stations s       ON s.station_id = c.station_id
    LEFT JOIN payments p  ON p.booking_id = b.booking_id
"""


def _booking_row(city: str, r) -> dict:
    return {
        "city": city,
        "booking_id": r["booking_id"],
        "booking_status": r["booking_status"],
        "booking_amount": float(r["booking_amount"]),
        "slot_id": r["slot_id"],
        "vehicle_id": r["vehicle_id"],
        "charger_id": r["charger_id"],
        "charger_code": r["charger_code"],
        "station_id": r["station_id"],
        "station_name": r["station_name"],
        "slot_date": r["slot_date"],
        "start_time": _hhmm(r["slot_start_time"]),
        "end_time": _hhmm(r["slot_end_time"]),
        "payment_id": r["payment_id"],
        "payment_status": r["payment_status"],
        "transaction_id": r["transaction_id"],
        "created_at": r["created_at"],
    }


def list_user_bookings(user_id: int) -> list[dict]:
    """Bookings live on the station's node, so ask every node and merge."""
    from app.core.cities import CITIES

    out = []
    for city in CITIES:
        try:
            with city_session(city) as db:
                rows = db.execute(
                    text(_BOOKING_LIST_SQL + " WHERE b.user_id = :u"), {"u": user_id}
                ).mappings()
                out.extend(_booking_row(city, r) for r in rows)
        except OperationalError:
            log.warning("node %s unreachable while listing bookings", city)
    out.sort(key=lambda b: (b["slot_date"], b["start_time"]), reverse=True)
    return out


def get_booking(user: dict, city: str, booking_id: int) -> dict:
    city = normalize_city(city)
    with city_session(city) as db:
        r = (
            db.execute(text(_BOOKING_LIST_SQL + " WHERE b.booking_id = :b"), {"b": booking_id})
            .mappings()
            .first()
        )
        owner = db.execute(
            text("SELECT user_id FROM bookings WHERE booking_id = :b"), {"b": booking_id}
        ).scalar_one_or_none()
    if not r:
        raise NotFound("Booking not found")
    if owner != user["user_id"] and user["role"] != "admin":
        raise Forbidden("Not your booking")
    return _booking_row(city, r)
