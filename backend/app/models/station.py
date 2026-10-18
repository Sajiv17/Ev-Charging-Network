"""Station tables - horizontally fragmented: each node only has its own city's rows."""

from sqlalchemy import (
    DECIMAL,
    TIMESTAMP,
    Boolean,
    Column,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import relationship

from app.db.mysql_connection import Base


class Station(Base):
    __tablename__ = "stations"

    station_id = Column(Integer, primary_key=True, autoincrement=True)
    station_name = Column(String(255), nullable=False)
    city_id = Column(Integer, ForeignKey("cities.city_id"), nullable=False)
    address = Column(Text, nullable=False)
    latitude = Column(DECIMAL(10, 8))
    longitude = Column(DECIMAL(11, 8))
    operator_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    is_operational = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    chargers = relationship("ChargerUnit", back_populates="station", lazy="selectin")


class ChargerUnit(Base):
    __tablename__ = "charger_units"

    charger_id = Column(Integer, primary_key=True, autoincrement=True)
    station_id = Column(Integer, ForeignKey("stations.station_id", ondelete="CASCADE"), nullable=False)
    charger_code = Column(String(50), nullable=False)
    charger_type = Column(Enum("AC", "DC"), nullable=False)
    max_power_kw = Column(DECIMAL(5, 2), nullable=False)
    connector_type = Column(Enum("CCS2", "CHAdeMO", "Type2"), nullable=False)
    status = Column(Enum("available", "occupied", "faulted", "maintenance"), default="available")
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    station = relationship("Station", back_populates="chargers")
