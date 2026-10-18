"""Booking tables - horizontally fragmented by city."""

from sqlalchemy import (
    DATE,
    DATETIME,
    DECIMAL,
    TIME,
    TIMESTAMP,
    Boolean,
    Column,
    Enum,
    ForeignKey,
    Integer,
    func,
)

from app.db.mysql_connection import Base


class Slot(Base):
    __tablename__ = "slots"

    slot_id = Column(Integer, primary_key=True, autoincrement=True)
    charger_id = Column(Integer, ForeignKey("charger_units.charger_id", ondelete="CASCADE"), nullable=False)
    slot_date = Column(DATE, nullable=False)
    slot_start_time = Column(TIME, nullable=False)
    slot_end_time = Column(TIME, nullable=False)
    is_available = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, server_default=func.now())


class Booking(Base):
    __tablename__ = "bookings"

    booking_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    slot_id = Column(Integer, ForeignKey("slots.slot_id"), nullable=False)
    vehicle_id = Column(Integer, ForeignKey("vehicles.vehicle_id"), nullable=False)
    booking_status = Column(Enum("confirmed", "active", "completed", "cancelled"), default="confirmed")
    booking_amount = Column(DECIMAL(10, 2), nullable=False)
    energy_consumed_kwh = Column(DECIMAL(8, 2))
    session_start_time = Column(DATETIME)
    session_end_time = Column(DATETIME)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
