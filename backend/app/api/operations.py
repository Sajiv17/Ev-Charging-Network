"""Sessions, payments, chargers, operator and admin routes."""

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import get_current_user, require_role
from app.core.cities import CITIES
from app.db.mysql_connection import ENGINES
from app.services import ops_service, recovery_service, session_service, xa

sessions = APIRouter()
payments = APIRouter()
chargers = APIRouter()
operator = APIRouter()
admin = APIRouter()


class SessionStart(BaseModel):
    force: bool = Field(False, description="DEMO_MODE only: ignore the slot time window")


class SessionEnd(BaseModel):
    energy_kwh: float = Field(ge=0, le=1000, description="Energy delivered, as reported by the charger")


class ChargerStatusChange(BaseModel):
    status: Literal["faulted", "available", "maintenance"]


# ------------------------------------------------------------------- sessions


@sessions.post("/{city}/{booking_id}/start")
def start(city: str, booking_id: int, body: SessionStart | None = None, current=Depends(get_current_user)):
    """Driver scans the QR at the charger: booking -> active, charger -> occupied."""
    return session_service.start_session(current, city, booking_id, force=bool(body and body.force))


@sessions.post("/{city}/{booking_id}/end")
def end(city: str, booking_id: int, body: SessionEnd, current=Depends(get_current_user)):
    """Driver unplugs: bill actual kWh, refund the unused prepaid amount (2PC if wallet is in another city)."""
    return session_service.end_session(current, city, booking_id, body.energy_kwh)


# ------------------------------------------------------------------- payments


@payments.get("")
def my_payments(current=Depends(get_current_user)):
    """All my payments across cities, with how much of each was refunded (or is pending)."""
    return ops_service.list_user_payments(current["user_id"])


# ------------------------------------------------------------------- chargers


@chargers.get("/{city}/{charger_id}")
def charger(city: str, charger_id: int):
    """MySQL status + active session + live MongoDB telemetry (live = null if MongoDB is not up)."""
    return ops_service.get_charger(city, charger_id)


# ------------------------------------------------------------------- operator


@operator.post("/chargers/{city}/{charger_id}/status")
def set_status(
    city: str, charger_id: int, body: ChargerStatusChange, current=Depends(require_role("operator", "admin"))
):
    """Report a fault / repair. Fires the fault trigger: bookings cancelled + refunded, alert written."""
    return ops_service.set_charger_status(current, city, charger_id, body.status)


@operator.get("/alerts")
def alerts(unread_only: bool = False, current=Depends(require_role("operator", "admin"))):
    return ops_service.list_alerts(current, unread_only)


@operator.post("/alerts/{city}/{alert_id}/ack")
def ack(city: str, alert_id: int, current=Depends(require_role("operator", "admin"))):
    return ops_service.acknowledge_alert(current, city, alert_id)


# ------------------------------------------------------------------- admin


@admin.get("/nodes")
def nodes(current=Depends(require_role("admin"))):
    """Node health, prepared (in-doubt) XA branches per node, and the last recovery pass."""
    health = {}
    for city, engine in ENGINES.items():
        try:
            with engine.connect() as c:
                c.exec_driver_sql("SELECT 1")
            health[city] = "up"
        except Exception:
            health[city] = "down"
    return {
        "mysql_nodes": health,
        "in_doubt": xa.list_in_doubt(),
        "last_recovery": recovery_service.last_report(),
        "cities": list(CITIES),
    }


@admin.post("/recover")
def recover(current=Depends(require_role("admin"))):
    """Run recovery now: resolve in-doubt 2PC transactions, pay queued cross-city refunds."""
    return recovery_service.run_recovery()


@admin.get("/xa-log")
def xa_log(current=Depends(require_role("admin"))):
    """The coordinator's decision log (gtrid -> decision / done)."""
    return xa.decision_log.state()
