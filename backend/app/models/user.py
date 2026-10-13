from sqlalchemy import DECIMAL, TIMESTAMP, Boolean, Column, Enum, ForeignKey, Integer, String, func

from app.db.mysql_connection import Base


class User(Base):
    """
    Replicated on every city node with the SAME user_id (needed because
    bookings.user_id has a foreign key to users on the station's node).

    wallet_balance is only authoritative on the user's HOME node
    (home_city_id). The copies on other nodes are never read for money.
    """

    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    phone = Column(String(20))
    role = Column(Enum("driver", "operator", "admin"), default="driver")
    wallet_balance = Column(DECIMAL(10, 2), default=0)
    home_city_id = Column(Integer, ForeignKey("cities.city_id"), nullable=False, default=1)
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
