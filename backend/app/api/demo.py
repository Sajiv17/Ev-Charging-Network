"""
Demo-only endpoints for the concurrency presentation.
Mounted only when DEMO_MODE=true. Turn it off for anything real.
"""

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_user
from app.schemas.booking_schema import BookingResponse, DemoBookingCreate
from app.services import audit, booking_service, demo_service

router = APIRouter()


@router.post("/book", response_model=BookingResponse, status_code=201)
def demo_book(body: DemoBookingCreate, current=Depends(get_current_user)):
    """
    mode=locked -> the real booking transaction (2PL)
    mode=unsafe -> no locks: shows double booking
    delay_ms    -> pause inside the transaction to make the race visible
    """
    fn = (
        booking_service.create_booking_with_lock
        if body.mode == "locked"
        else booking_service.create_booking_unsafe
    )
    return fn(current, body.city, body.slot_id, body.vehicle_id, delay_ms=body.delay_ms)


@router.post("/fresh-slot")
def fresh_slot(city: str = "bangalore", connector_type: str = "CCS2"):
    """Create a new empty slot to race on."""
    return demo_service.create_fresh_slot(city, connector_type)


@router.get("/slot-report/{city}/{slot_id}")
def slot_report(city: str, slot_id: int):
    """confirmed_bookings > 1 means the slot was double booked."""
    return demo_service.slot_report(city, slot_id)


@router.get("/audit-log")
def audit_log(after_seq: int = 0, limit: int = Query(200, le=2000), txn: str | None = None):
    """Live transaction log. Poll with after_seq=<last seq you saw>."""
    return audit.recent(limit=limit, after_seq=after_seq, txn=txn)


@router.delete("/audit-log", status_code=204)
def clear_audit_log():
    audit.clear()
