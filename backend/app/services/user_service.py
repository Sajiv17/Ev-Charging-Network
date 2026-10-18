"""Users, wallets and vehicles."""

from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.cities import ID_AUTHORITY_CITY, city_id_of, city_key_of
from app.core.security import hash_password, verify_password
from app.db.mysql_connection import city_session
from app.models import User, Vehicle
from app.services import audit
from app.services.errors import AppError, Conflict, NotFound
from app.services.replication import write_everywhere


def _user_dict(u: User, wallet: Decimal | None = None) -> dict:
    return {
        "user_id": u.user_id,
        "email": u.email,
        "full_name": u.full_name,
        "phone": u.phone,
        "role": u.role,
        "home_city": city_key_of(u.home_city_id),
        "wallet_balance": float(wallet if wallet is not None else u.wallet_balance),
    }


# --------------------------------------------------------------------------- users


def register_user(
    email: str, password: str, full_name: str, phone: str | None, home_city: str, role: str = "driver"
) -> dict:
    pw_hash = hash_password(password)
    home_city_id = city_id_of(home_city)

    def insert(city: str, db: Session, user_id: int | None) -> int:
        user = User(
            email=email,
            password_hash=pw_hash,
            full_name=full_name,
            phone=phone,
            role=role,
            wallet_balance=0,
            home_city_id=home_city_id,
        )
        if user_id is not None:
            user.user_id = user_id
        db.add(user)
        db.flush()  # sends the INSERT now so we learn the id / hit the UNIQUE(email) check
        return user.user_id

    try:
        user_id = write_everywhere(insert)
    except IntegrityError as exc:
        if "Duplicate" in str(exc.orig):
            raise Conflict("An account with this email already exists", code="email_taken")
        raise
    audit.record("USER_REGISTERED", city=home_city, user_id=user_id)
    return get_user(user_id)


def authenticate(email: str, password: str) -> dict | None:
    with city_session(ID_AUTHORITY_CITY) as db:
        user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if not user or not user.is_active or not verify_password(password, user.password_hash):
            return None
        return get_user(user.user_id)


def get_user(user_id: int) -> dict:
    """Profile from the authority node, wallet from the user's home node."""
    with city_session(ID_AUTHORITY_CITY) as db:
        user = db.get(User, user_id)
        if not user:
            raise NotFound("User not found")
        home = city_key_of(user.home_city_id)
    return _user_dict(user, wallet=get_wallet_balance(user_id, home))


def get_wallet_balance(user_id: int, home_city: str) -> Decimal:
    with city_session(home_city) as db:
        bal = db.execute(
            text("SELECT wallet_balance FROM users WHERE user_id = :u"), {"u": user_id}
        ).scalar_one_or_none()
    if bal is None:
        raise NotFound("User not found on home node")
    return bal


def top_up_wallet(user_id: int, home_city: str, amount: float) -> Decimal:
    """Credit the wallet on the HOME node only (the authoritative copy)."""
    amt = Decimal(str(amount)).quantize(Decimal("0.01"))
    with city_session(home_city) as db:
        try:
            # Atomic increment: no read-modify-write, so no lost update.
            res = db.execute(
                text("UPDATE users SET wallet_balance = wallet_balance + :a WHERE user_id = :u"),
                {"a": amt, "u": user_id},
            )
            if res.rowcount != 1:
                raise NotFound("User not found on home node")
            bal = db.execute(
                text("SELECT wallet_balance FROM users WHERE user_id = :u"), {"u": user_id}
            ).scalar_one()
            db.commit()
        except Exception:
            db.rollback()
            raise
    audit.record("WALLET_TOPUP", city=home_city, user_id=user_id, amount=float(amt), balance=float(bal))
    return bal


# --------------------------------------------------------------------------- vehicles


def _vehicle_dict(v: Vehicle) -> dict:
    return {
        "vehicle_id": v.vehicle_id,
        "user_id": v.user_id,
        "make": v.make,
        "model": v.model,
        "battery_capacity_kwh": float(v.battery_capacity_kwh),
        "connector_type": v.connector_type,
        "registration_number": v.registration_number,
    }


def add_vehicle(user_id: int, data: dict) -> dict:
    """Vehicles are replicated: a booking on any node references vehicle_id."""
    reg = (data.get("registration_number") or "").replace(" ", "").upper() or None

    def insert(city: str, db: Session, vehicle_id: int | None) -> int:
        v = Vehicle(user_id=user_id, **{**data, "registration_number": reg})
        if vehicle_id is not None:
            v.vehicle_id = vehicle_id
        db.add(v)
        db.flush()
        return v.vehicle_id

    try:
        vehicle_id = write_everywhere(insert)
    except IntegrityError as exc:
        if "Duplicate" in str(exc.orig):
            raise Conflict("A vehicle with this registration number already exists")
        raise
    with city_session(ID_AUTHORITY_CITY) as db:
        return _vehicle_dict(db.get(Vehicle, vehicle_id))


def list_vehicles(user_id: int) -> list[dict]:
    with city_session(ID_AUTHORITY_CITY) as db:
        rows = db.execute(
            select(Vehicle).where(Vehicle.user_id == user_id).order_by(Vehicle.vehicle_id)
        ).scalars()
        return [_vehicle_dict(v) for v in rows]


def delete_vehicle(user_id: int, vehicle_id: int) -> None:
    def delete(city: str, db: Session, _id: int | None) -> int:
        v = db.get(Vehicle, vehicle_id)
        if not v or v.user_id != user_id:
            raise NotFound("Vehicle not found")
        db.delete(v)
        db.flush()
        return vehicle_id

    try:
        write_everywhere(delete)
    except IntegrityError:
        raise AppError(
            "This vehicle has bookings and cannot be deleted", code="vehicle_in_use", status_code=409
        )
