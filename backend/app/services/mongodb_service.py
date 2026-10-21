"""
MongoDB service layer for real-time data operations.

This module provides CRUD operations for MongoDB collections:
- charger_status: Real-time charger operational status
- charging_sessions: Session logs with energy consumption
- fault_reports: Operator-submitted fault reports
- audit_log: Transaction event logging

Used by the backend API and the status simulator.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any

from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError

from app.db.mongodb_connection import (
    charger_status_collection,
    charging_sessions_collection,
    fault_reports_collection,
    audit_log_collection
)


# ============================================================================
# Charger Status Operations
# ============================================================================

def get_charger_status(charger_id: int) -> Optional[Dict[str, Any]]:
    """
    Get current real-time status of a charger.
    Returns None if charger not found.
    """
    return charger_status_collection.find_one({"charger_id": charger_id}, {"_id": 0})


def get_station_chargers_status(station_id: int) -> List[Dict[str, Any]]:
    """
    Get real-time status of all chargers at a station.
    """
    return list(charger_status_collection.find(
        {"station_id": station_id},
        {"_id": 0}
    ).sort("charger_id", 1))


def get_city_chargers_status(city: str, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Get all chargers in a city, optionally filtered by status.

    Args:
        city: "bangalore", "chennai", or "delhi"
        status_filter: Optional - "available", "occupied", "faulted", "maintenance"
    """
    query = {"city": city.lower()}
    if status_filter:
        query["status"] = status_filter

    return list(charger_status_collection.find(query, {"_id": 0}).sort("charger_id", 1))


def update_charger_status(
    charger_id: int,
    status: str,
    current_power_kw: float = 0.0,
    session_energy_kwh: float = 0.0,
    active_booking_id: Optional[int] = None,
    session_started_at: Optional[datetime] = None,
    fault_code: Optional[str] = None,
    fault_message: Optional[str] = None
) -> bool:
    """
    Update a charger's real-time status.

    Args:
        charger_id: The charger to update
        status: "available", "occupied", "faulted", "maintenance"
        current_power_kw: Current power draw (kW)
        session_energy_kwh: Cumulative energy delivered in current session
        active_booking_id: Booking ID if occupied
        session_started_at: When the current session started
        fault_code: Error code if faulted
        fault_message: Human-readable fault description

    Returns:
        True if updated, False if charger not found
    """
    now = datetime.utcnow()

    update_fields = {
        "status": status,
        "current_power_kw": current_power_kw,
        "session_energy_kwh": session_energy_kwh,
        "last_heartbeat": now,
        "updated_at": now
    }

    # Only update status_changed_at if status actually changed
    existing = charger_status_collection.find_one({"charger_id": charger_id}, {"status": 1})
    if existing and existing.get("status") != status:
        update_fields["status_changed_at"] = now

    # Update session tracking
    if status == "occupied":
        update_fields["active_booking_id"] = active_booking_id
        update_fields["session_started_at"] = session_started_at or now
    else:
        update_fields["active_booking_id"] = None
        update_fields["session_started_at"] = None

    # Update fault info
    if status == "faulted":
        update_fields["fault_code"] = fault_code
        update_fields["fault_message"] = fault_message
    else:
        update_fields["fault_code"] = None
        update_fields["fault_message"] = None

    result = charger_status_collection.update_one(
        {"charger_id": charger_id},
        {"$set": update_fields}
    )

    return result.modified_count > 0


def create_charger_status(
    charger_id: int,
    station_id: int,
    city: str,
    status: str = "available"
) -> bool:
    """
    Create initial charger status document.
    Called when seeding MongoDB or adding new chargers.
    """
    now = datetime.utcnow()

    doc = {
        "charger_id": charger_id,
        "station_id": station_id,
        "city": city.lower(),
        "status": status,
        "current_power_kw": 0.0,
        "session_energy_kwh": 0.0,
        "fault_code": None,
        "fault_message": None,
        "last_heartbeat": now,
        "status_changed_at": now,
        "active_booking_id": None,
        "session_started_at": None,
        "created_at": now,
        "updated_at": now
    }

    try:
        charger_status_collection.insert_one(doc)
        return True
    except DuplicateKeyError:
        # Charger already exists
        return False


# ============================================================================
# Charging Sessions Operations
# ============================================================================

def create_charging_session(
    booking_id: int,
    charger_id: int,
    user_id: int,
    station_id: int,
    city: str,
    rate_per_kwh: float,
    charger_type: str,
    vehicle_make: str,
    vehicle_model: str
) -> Dict[str, Any]:
    """
    Start a new charging session.
    Called when a driver plugs in and starts charging.
    """
    now = datetime.utcnow()

    session = {
        "booking_id": booking_id,
        "charger_id": charger_id,
        "user_id": user_id,
        "station_id": station_id,
        "city": city.lower(),
        "status": "active",
        "session_started_at": now,
        "session_ended_at": None,
        "session_energy_kwh": 0.0,
        "final_energy_kwh": None,
        "power_samples": [],
        "rate_per_kwh": rate_per_kwh,
        "energy_cost": None,
        "charger_type": charger_type,
        "vehicle_make": vehicle_make,
        "vehicle_model": vehicle_model,
        "created_at": now,
        "updated_at": now
    }

    charging_sessions_collection.insert_one(session)
    return session


def update_session_energy(
    booking_id: int,
    energy_kwh: float,
    power_kw: float
) -> bool:
    """
    Update cumulative energy for an active session.
    Called by the status simulator every 5-10 seconds.

    Also adds a power sample for graphing.
    """
    now = datetime.utcnow()

    result = charging_sessions_collection.update_one(
        {"booking_id": booking_id, "status": "active"},
        {
            "$set": {
                "session_energy_kwh": energy_kwh,
                "updated_at": now
            },
            "$push": {
                "power_samples": {
                    "timestamp": now,
                    "power_kw": power_kw
                }
            }
        }
    )

    return result.modified_count > 0


def end_charging_session(
    booking_id: int,
    final_energy_kwh: float,
    status: str = "completed"
) -> Optional[Dict[str, Any]]:
    """
    End a charging session and calculate final cost.

    Args:
        booking_id: The session to end
        final_energy_kwh: Final energy delivered
        status: "completed" or "interrupted"

    Returns:
        The updated session document with final_energy_kwh and energy_cost
    """
    session = charging_sessions_collection.find_one({"booking_id": booking_id})
    if not session:
        return None

    now = datetime.utcnow()
    energy_cost = round(final_energy_kwh * session["rate_per_kwh"], 2)

    charging_sessions_collection.update_one(
        {"booking_id": booking_id},
        {
            "$set": {
                "status": status,
                "session_ended_at": now,
                "final_energy_kwh": final_energy_kwh,
                "energy_cost": energy_cost,
                "updated_at": now
            }
        }
    )

    return charging_sessions_collection.find_one({"booking_id": booking_id}, {"_id": 0})


def get_active_sessions(city: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Get all currently active charging sessions.
    Optionally filter by city.
    """
    query = {"status": "active"}
    if city:
        query["city"] = city.lower()

    return list(charging_sessions_collection.find(query, {"_id": 0}).sort("session_started_at", -1))


def get_user_sessions(user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Get a user's recent charging sessions.
    """
    return list(charging_sessions_collection.find(
        {"user_id": user_id},
        {"_id": 0}
    ).sort("session_started_at", -1).limit(limit))


# ============================================================================
# Fault Reports Operations
# ============================================================================

def create_fault_report(
    charger_id: int,
    station_id: int,
    operator_id: int,
    city: str,
    fault_type: str,
    error_code: str,
    severity: str,
    description: str,
    charger_make: str,
    charger_model: str,
    estimated_repair_time_hours: Optional[float] = None
) -> Dict[str, Any]:
    """
    File a new fault report.
    Called by the operator when investigating a faulted charger.
    """
    now = datetime.utcnow()

    report = {
        "charger_id": charger_id,
        "station_id": station_id,
        "operator_id": operator_id,
        "city": city.lower(),
        "fault_type": fault_type,
        "error_code": error_code,
        "severity": severity,
        "description": description,
        "photos": [],
        "resolution_status": "open",
        "resolution_notes": None,
        "fault_reported_at": now,
        "resolved_at": None,
        "resolved_by": None,
        "estimated_repair_time_hours": estimated_repair_time_hours,
        "actual_repair_time_hours": None,
        "charger_make": charger_make,
        "charger_model": charger_model,
        "created_at": now,
        "updated_at": now
    }

    result = fault_reports_collection.insert_one(report)
    report["_id"] = str(result.inserted_id)
    return report


def update_fault_status(
    fault_id: str,
    resolution_status: str,
    resolution_notes: Optional[str] = None,
    resolved_by: Optional[int] = None
) -> bool:
    """
    Update a fault report's resolution status.

    Args:
        fault_id: MongoDB ObjectId as string
        resolution_status: "open", "in_progress", "resolved", "escalated"
        resolution_notes: Notes from operator/technician
        resolved_by: User ID of who resolved it
    """
    from bson import ObjectId

    now = datetime.utcnow()
    update_fields = {
        "resolution_status": resolution_status,
        "updated_at": now
    }

    if resolution_notes:
        update_fields["resolution_notes"] = resolution_notes

    if resolution_status == "resolved":
        update_fields["resolved_at"] = now
        if resolved_by:
            update_fields["resolved_by"] = resolved_by

        # Calculate actual repair time
        fault = fault_reports_collection.find_one({"_id": ObjectId(fault_id)}, {"fault_reported_at": 1})
        if fault:
            duration = now - fault["fault_reported_at"]
            update_fields["actual_repair_time_hours"] = round(duration.total_seconds() / 3600, 2)

    result = fault_reports_collection.update_one(
        {"_id": ObjectId(fault_id)},
        {"$set": update_fields}
    )

    return result.modified_count > 0


def get_station_faults(station_id: int, resolution_status: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Get fault reports for a station.
    Optionally filter by resolution status.
    """
    query = {"station_id": station_id}
    if resolution_status:
        query["resolution_status"] = resolution_status

    faults = list(fault_reports_collection.find(query).sort("fault_reported_at", -1))

    # Convert ObjectId to string for JSON serialization
    for fault in faults:
        fault["_id"] = str(fault["_id"])

    return faults


# ============================================================================
# Audit Log Operations
# ============================================================================

def log_transaction_event(
    event_type: str,
    transaction_id: str,
    user_id: Optional[int] = None,
    booking_id: Optional[int] = None,
    slot_id: Optional[int] = None,
    charger_id: Optional[int] = None,
    city: Optional[str] = None,
    lock_mode: Optional[str] = None,
    lock_wait_time_ms: Optional[float] = None,
    success: Optional[bool] = None,
    error_message: Optional[str] = None,
    endpoint: Optional[str] = None,
    request_id: Optional[str] = None,
    xa_global_id: Optional[str] = None,
    participant_cities: Optional[List[str]] = None
) -> None:
    """
    Log a transaction event to the audit log.

    Called by booking_service.py for every significant transaction event.
    This creates the audit trail for concurrency demos.
    """
    now = datetime.utcnow()

    event = {
        "event_type": event_type,
        "transaction_id": transaction_id,
        "timestamp": now,
        "created_at": now
    }

    # Add optional fields only if provided
    if user_id is not None:
        event["user_id"] = user_id
    if booking_id is not None:
        event["booking_id"] = booking_id
    if slot_id is not None:
        event["slot_id"] = slot_id
    if charger_id is not None:
        event["charger_id"] = charger_id
    if city:
        event["city"] = city.lower()
    if lock_mode:
        event["lock_mode"] = lock_mode
    if lock_wait_time_ms is not None:
        event["lock_wait_time_ms"] = lock_wait_time_ms
    if success is not None:
        event["success"] = success
    if error_message:
        event["error_message"] = error_message
    if endpoint:
        event["endpoint"] = endpoint
    if request_id:
        event["request_id"] = request_id
    if xa_global_id:
        event["xa_global_id"] = xa_global_id
    if participant_cities:
        event["participant_cities"] = participant_cities

    audit_log_collection.insert_one(event)


def get_transaction_audit_trail(transaction_id: str) -> List[Dict[str, Any]]:
    """
    Get all events for a single transaction, chronologically.
    Useful for debugging and the concurrency demo.
    """
    events = list(audit_log_collection.find(
        {"transaction_id": transaction_id},
        {"_id": 0}
    ).sort("timestamp", 1))

    return events


def get_slot_contention_log(slot_id: int, limit: int = 20) -> List[Dict[str, Any]]:
    """
    Get recent transaction events for a specific slot.
    Shows which transactions tried to book it and which succeeded.
    """
    events = list(audit_log_collection.find(
        {"slot_id": slot_id},
        {"_id": 0}
    ).sort("timestamp", -1).limit(limit))

    return events


def get_recent_audit_events(limit: int = 50) -> List[Dict[str, Any]]:
    """
    Get most recent audit events across all transactions.
    For live monitoring dashboard.
    """
    events = list(audit_log_collection.find(
        {},
        {"_id": 0}
    ).sort("timestamp", -1).limit(limit))

    return events
