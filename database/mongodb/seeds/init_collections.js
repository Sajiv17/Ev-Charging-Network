// MongoDB initialization script
// Creates collections with validation and indexes
// Run this once when starting MongoDB for the first time

print("Initializing MongoDB collections for EV Charging Network...");

// Switch to database
db = db.getSiblingDB('ev_realtime');

// ============================================================================
// Collection 1: charger_status
// ============================================================================

print("Creating collection: charger_status");

db.createCollection("charger_status", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["charger_id", "station_id", "city", "status", "last_heartbeat"],
      properties: {
        charger_id: { bsonType: "int", minimum: 1 },
        station_id: { bsonType: "int", minimum: 1 },
        city: { bsonType: "string", enum: ["bangalore", "chennai", "delhi"] },
        status: { bsonType: "string", enum: ["available", "occupied", "faulted", "maintenance"] },
        current_power_kw: { bsonType: ["double", "int"], minimum: 0 },
        session_energy_kwh: { bsonType: ["double", "int"], minimum: 0 },
        fault_code: { bsonType: ["string", "null"] },
        fault_message: { bsonType: ["string", "null"] },
        last_heartbeat: { bsonType: "date" },
        status_changed_at: { bsonType: "date" },
        active_booking_id: { bsonType: ["int", "null"] },
        session_started_at: { bsonType: ["date", "null"] }
      }
    }
  }
});

db.charger_status.createIndex({ charger_id: 1 }, { unique: true });
db.charger_status.createIndex({ station_id: 1, status: 1 });
db.charger_status.createIndex({ city: 1, status: 1 });
db.charger_status.createIndex({ last_heartbeat: 1 });

print("✓ charger_status created with indexes");

// ============================================================================
// Collection 2: charging_sessions
// ============================================================================

print("Creating collection: charging_sessions");

db.createCollection("charging_sessions", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["booking_id", "charger_id", "user_id", "station_id", "city", "status", "session_started_at"],
      properties: {
        booking_id: { bsonType: "int", minimum: 1 },
        charger_id: { bsonType: "int", minimum: 1 },
        user_id: { bsonType: "int", minimum: 1 },
        station_id: { bsonType: "int", minimum: 1 },
        city: { bsonType: "string", enum: ["bangalore", "chennai", "delhi"] },
        status: { bsonType: "string", enum: ["active", "completed", "interrupted"] },
        session_energy_kwh: { bsonType: ["double", "int"], minimum: 0 },
        final_energy_kwh: { bsonType: ["double", "int", "null"], minimum: 0 },
        rate_per_kwh: { bsonType: ["double", "int"], minimum: 0 },
        energy_cost: { bsonType: ["double", "int", "null"], minimum: 0 }
      }
    }
  }
});

db.charging_sessions.createIndex({ booking_id: 1 }, { unique: true });
db.charging_sessions.createIndex({ charger_id: 1, status: 1 });
db.charging_sessions.createIndex({ user_id: 1, session_started_at: -1 });
db.charging_sessions.createIndex({ city: 1, session_started_at: -1 });
db.charging_sessions.createIndex({ status: 1, session_started_at: -1 });

print("✓ charging_sessions created with indexes");

// ============================================================================
// Collection 3: fault_reports
// ============================================================================

print("Creating collection: fault_reports");

db.createCollection("fault_reports", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["charger_id", "station_id", "operator_id", "city", "fault_type", "severity", "resolution_status", "fault_reported_at"],
      properties: {
        charger_id: { bsonType: "int", minimum: 1 },
        station_id: { bsonType: "int", minimum: 1 },
        operator_id: { bsonType: "int", minimum: 1 },
        city: { bsonType: "string", enum: ["bangalore", "chennai", "delhi"] },
        severity: { bsonType: "string", enum: ["low", "medium", "high", "critical"] },
        resolution_status: { bsonType: "string", enum: ["open", "in_progress", "resolved", "escalated"] },
        fault_reported_at: { bsonType: "date" },
        resolved_at: { bsonType: ["date", "null"] },
        estimated_repair_time_hours: { bsonType: ["double", "int", "null"], minimum: 0 },
        actual_repair_time_hours: { bsonType: ["double", "int", "null"], minimum: 0 }
      }
    }
  }
});

db.fault_reports.createIndex({ charger_id: 1, fault_reported_at: -1 });
db.fault_reports.createIndex({ station_id: 1, resolution_status: 1 });
db.fault_reports.createIndex({ operator_id: 1 });
db.fault_reports.createIndex({ resolution_status: 1, fault_reported_at: -1 });
db.fault_reports.createIndex({ city: 1, severity: 1 });

print("✓ fault_reports created with indexes");

// ============================================================================
// Collection 4: audit_log
// ============================================================================

print("Creating collection: audit_log");

db.createCollection("audit_log", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["event_type", "transaction_id", "timestamp"],
      properties: {
        event_type: {
          bsonType: "string",
          enum: ["lock_acquired", "lock_wait", "lock_timeout", "slot_check", "wallet_debit",
                 "booking_created", "commit", "rollback", "xa_prepare", "xa_commit", "xa_rollback"]
        },
        transaction_id: { bsonType: "string" },
        user_id: { bsonType: ["int", "null"], minimum: 1 },
        booking_id: { bsonType: ["int", "null"], minimum: 1 },
        slot_id: { bsonType: ["int", "null"], minimum: 1 },
        charger_id: { bsonType: ["int", "null"], minimum: 1 },
        city: { bsonType: ["string", "null"] },
        success: { bsonType: ["bool", "null"] },
        lock_wait_time_ms: { bsonType: ["double", "int", "null"], minimum: 0 },
        timestamp: { bsonType: "date" }
      }
    }
  }
});

db.audit_log.createIndex({ transaction_id: 1 });
db.audit_log.createIndex({ slot_id: 1, timestamp: 1 });
db.audit_log.createIndex({ user_id: 1, timestamp: -1 });
db.audit_log.createIndex({ event_type: 1, timestamp: -1 });
db.audit_log.createIndex({ timestamp: -1 });
db.audit_log.createIndex({ request_id: 1 });

print("✓ audit_log created with indexes");

print("\n========================================");
print("MongoDB initialization complete!");
print("Collections created: 4");
print("Indexes created: 21");
print("========================================\n");
