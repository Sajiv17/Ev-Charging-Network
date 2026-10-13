from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.schemas.booking_schema import BookingCreate, BookingResponse, CancelResponse
from app.services import booking_service

router = APIRouter()


@router.post("", response_model=BookingResponse, status_code=201)
def create_booking(body: BookingCreate, current=Depends(get_current_user)):
    """
    Book a slot. One atomic transaction on the station's city node:
    lock slot -> check -> lock wallet -> debit -> booking + payment -> commit.
    409 slot_unavailable if someone else got it first.
    """
    return booking_service.create_booking_with_lock(current, body.city, body.slot_id, body.vehicle_id)


@router.get("", response_model=list[BookingResponse])
def my_bookings(current=Depends(get_current_user)):
    return booking_service.list_user_bookings(current["user_id"])


@router.get("/{city}/{booking_id}", response_model=BookingResponse)
def get_booking(city: str, booking_id: int, current=Depends(get_current_user)):
    return booking_service.get_booking(current, city, booking_id)


@router.post("/{city}/{booking_id}/cancel", response_model=CancelResponse)
def cancel(city: str, booking_id: int, current=Depends(get_current_user)):
    """Cancel before the slot starts: full refund to wallet, slot freed."""
    return booking_service.cancel_booking(current, city, booking_id)
