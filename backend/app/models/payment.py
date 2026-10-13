"""Payment tables - horizontally fragmented by city (live next to the booking)."""

from sqlalchemy import DECIMAL, TIMESTAMP, Column, Enum, ForeignKey, Integer, String, Text, func

from app.db.mysql_connection import Base


class Payment(Base):
    __tablename__ = "payments"

    payment_id = Column(Integer, primary_key=True, autoincrement=True)
    booking_id = Column(Integer, ForeignKey("bookings.booking_id", ondelete="CASCADE"), nullable=False)
    amount = Column(DECIMAL(10, 2), nullable=False)
    payment_method = Column(Enum("wallet", "upi", "card", "netbanking"), nullable=False)
    payment_status = Column(Enum("pending", "completed", "failed", "refunded"), default="pending")
    transaction_id = Column(String(255), unique=True)
    payment_timestamp = Column(TIMESTAMP, server_default=func.now())


class Refund(Base):
    __tablename__ = "refunds"

    refund_id = Column(Integer, primary_key=True, autoincrement=True)
    payment_id = Column(Integer, ForeignKey("payments.payment_id"), nullable=False)
    refund_amount = Column(DECIMAL(10, 2), nullable=False)
    refund_reason = Column(Text)
    refund_status = Column(Enum("queued", "processing", "completed", "failed"), default="queued")
    created_at = Column(TIMESTAMP, server_default=func.now())
    processed_at = Column(TIMESTAMP)
