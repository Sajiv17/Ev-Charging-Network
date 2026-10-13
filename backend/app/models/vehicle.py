from sqlalchemy import DECIMAL, TIMESTAMP, Column, Enum, ForeignKey, Integer, String, func

from app.db.mysql_connection import Base


class Vehicle(Base):
    """Replicated on every node with the same vehicle_id (bookings.vehicle_id FK)."""

    __tablename__ = "vehicles"

    vehicle_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    make = Column(String(100), nullable=False)
    model = Column(String(100), nullable=False)
    battery_capacity_kwh = Column(DECIMAL(5, 2), nullable=False)
    connector_type = Column(Enum("CCS2", "CHAdeMO", "Type2"), nullable=False)
    registration_number = Column(String(20), unique=True)
    created_at = Column(TIMESTAMP, server_default=func.now())
