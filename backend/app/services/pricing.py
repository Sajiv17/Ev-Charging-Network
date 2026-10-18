"""
Pricing.

At booking time we don't know how much energy the car will take, so the
driver PREPAYS an estimate (the maximum the slot could deliver):

    prepaid = booking_fee + rate_per_kwh * min(charger_kW * slot_hours, battery_kWh)

When the session ends (phase 2), the real kWh is billed and the difference
is refunded to the wallet.
"""

from datetime import date, datetime, time
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.errors import AppError

_CENT = Decimal("0.01")


PLAN_SQL = """
    SELECT plan_id, rate_per_kwh, booking_fee
    FROM pricing_plans
    WHERE city_id = :city AND charger_type = :ctype
      AND effective_from <= :d
      AND (effective_to IS NULL OR effective_to >= :d)
    ORDER BY effective_from DESC
    LIMIT 1
"""


def get_plan(db: Session, city_id: int, charger_type: str, on_date: date):
    """The pricing plan in force for this city + charger type on a date (or None)."""
    return db.execute(text(PLAN_SQL), {"city": city_id, "ctype": charger_type, "d": on_date}).first()


def get_plan_q(q, city_id: int, charger_type: str, on_date: date):
    """Same as get_plan, for code running on a raw XA/local connection (app.services.xa.Q)."""
    return q.one(PLAN_SQL, city=city_id, ctype=charger_type, d=on_date)


def _field(plan, name):
    return plan[name] if isinstance(plan, dict) else getattr(plan, name)


def slot_hours(start: time, end: time) -> Decimal:
    secs = (datetime.combine(date.min, end) - datetime.combine(date.min, start)).total_seconds()
    if secs <= 0:
        raise AppError("Slot end time must be after start time")
    return Decimal(secs) / Decimal(3600)


def max_energy_kwh(max_power_kw, start: time, end: time, battery_kwh=None) -> Decimal:
    energy = Decimal(str(max_power_kw)) * slot_hours(start, end)
    if battery_kwh is not None:
        energy = min(energy, Decimal(str(battery_kwh)))
    return energy


def prepaid_amount(plan, max_power_kw, start: time, end: time, battery_kwh=None) -> Decimal:
    energy = max_energy_kwh(max_power_kw, start, end, battery_kwh)
    amount = Decimal(_field(plan, "booking_fee") or 0) + Decimal(_field(plan, "rate_per_kwh")) * energy
    return amount.quantize(_CENT, rounding=ROUND_HALF_UP)


def energy_cost(plan, energy_kwh) -> Decimal:
    """Final bill for a finished session: booking fee + rate x energy actually delivered."""
    amount = Decimal(_field(plan, "booking_fee") or 0) + Decimal(_field(plan, "rate_per_kwh")) * Decimal(
        str(energy_kwh)
    )
    return amount.quantize(_CENT, rounding=ROUND_HALF_UP)
