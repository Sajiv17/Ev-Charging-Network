"""Global catalog tables - replicated identically on all city nodes."""

from sqlalchemy import DATE, DECIMAL, TIMESTAMP, Column, Enum, ForeignKey, Integer, String, func

from app.db.mysql_connection import Base


class City(Base):
    __tablename__ = "cities"

    city_id = Column(Integer, primary_key=True, autoincrement=True)
    city_name = Column(String(100), nullable=False, unique=True)
    state = Column(String(100), nullable=False)
    country = Column(String(100), default="India")
    created_at = Column(TIMESTAMP, server_default=func.now())


class PricingPlan(Base):
    __tablename__ = "pricing_plans"

    plan_id = Column(Integer, primary_key=True, autoincrement=True)
    city_id = Column(Integer, ForeignKey("cities.city_id", ondelete="CASCADE"), nullable=False)
    charger_type = Column(Enum("AC", "DC"), nullable=False)
    rate_per_kwh = Column(DECIMAL(6, 2), nullable=False)
    booking_fee = Column(DECIMAL(6, 2), default=0)
    effective_from = Column(DATE, nullable=False)
    effective_to = Column(DATE)
    created_at = Column(TIMESTAMP, server_default=func.now())
