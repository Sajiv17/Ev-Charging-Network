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


def get_plan(db: Session, city_id: int, charger_type: str, on_date: date):
    """The pricing plan in force for this city + charger type on a date (or None)."""
    return db.execute(
        text(
            """
            SELECT plan_id, rate_per_kwh, booking_fee
            FROM pricing_plans
            WHERE city_id = :city AND charger_type = :ctype
              AND effective_from <= :d
              AND (effective_to IS NULL OR effective_to >= :d)
            ORDER BY effective_from DESC
            LIMIT 1
            """
        ),
        {"city": city_id, "ctype": charger_type, "d": on_date},
    ).first()


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
    amount = Decimal(plan.booking_fee or 0) + Decimal(plan.rate_per_kwh) * energy
    return amount.quantize(_CENT, rounding=ROUND_HALF_UP)
