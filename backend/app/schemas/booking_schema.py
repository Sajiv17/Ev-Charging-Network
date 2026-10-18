from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.user_schema import CityName


class BookingCreate(BaseModel):
    city: CityName = Field(description="City of the station (decides which MySQL node)")
    slot_id: int
    vehicle_id: int


class DemoBookingCreate(BookingCreate):
    mode: Literal["locked", "unsafe", "wrong_order"] = "locked"
    delay_ms: int = Field(
        default=0, ge=0, le=5000, description="Pause inside the transaction to widen the race window"
    )
    lock_gap_ms: int = Field(default=0, ge=0, le=5000, description="Pause between the first and second lock")
    fail_point: Literal["after_prepare", "after_decision"] | None = Field(
        default=None, description="Simulate a 2PC coordinator crash (recovery demo)"
    )


class BookingResponse(BaseModel):
    city: str
    booking_id: int
    booking_status: str
    booking_amount: float
    slot_id: int
    vehicle_id: int
    charger_id: int | None = None
    charger_code: str | None = None
    station_id: int | None = None
    station_name: str | None = None
    slot_date: date | None = None
    start_time: str | None = None
    end_time: str | None = None
    payment_id: int | None = None
    payment_status: str | None = None
    transaction_id: str | None = None
    wallet_balance_after: float | None = None
    created_at: datetime | None = None
    # Only for cross-city bookings: {"gtrid", "wallet_node", "pending_commit"}
    distributed: dict | None = None


class CancelResponse(BaseModel):
    city: str
    booking_id: int
    booking_status: str
    refund_amount: float
    wallet_balance_after: float
