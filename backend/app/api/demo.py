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
    mode=locked      -> the real booking transaction (2PL; 2PC if the wallet is on another node)
    mode=unsafe      -> no locks: shows double booking / lost update
    mode=wrong_order -> locks wallet BEFORE slot: with a locked request at the same time -> deadlock
    delay_ms         -> pause while holding the locks
    lock_gap_ms      -> pause between the first and the second lock
    fail_point       -> after_prepare / after_decision: simulate a coordinator crash during 2PC
    """
    if body.mode == "unsafe":
        return booking_service.create_booking_unsafe(
            current, body.city, body.slot_id, body.vehicle_id, delay_ms=body.delay_ms
        )
    return booking_service.create_booking_with_lock(
        current,
        body.city,
        body.slot_id,
        body.vehicle_id,
        delay_ms=body.delay_ms,
        lock_order="wallet_first" if body.mode == "wrong_order" else "slot_first",
        lock_gap_ms=body.lock_gap_ms,
        fail_point=body.fail_point,
    )


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
