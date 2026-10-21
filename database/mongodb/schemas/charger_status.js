/**
 * Collection: charger_status
 *
 * Real-time operational status for each charger unit across all cities.
 * One document per charger. Updated every 5-10 seconds by the status simulator
 * and by the backend when a charging session starts/ends.
 *
 * The backend's live_status service polls this collection to show operators
 * which chargers are available, occupied, or faulted in real time.
 */

// Example document
{
  _id: ObjectId("..."),

  // Links to MySQL charger_units table
  charger_id: 5,                    // INT - MySQL charger_units.charger_id
  station_id: 2,                    // INT - MySQL stations.station_id
  city: "bangalore",                // STRING - city name (normalized lowercase)

  // Real-time operational status
  status: "occupied",               // ENUM: "available" | "occupied" | "faulted" | "maintenance"

  // Live telemetry (only meaningful when status = "occupied")
  current_power_kw: 47.8,           // FLOAT - instantaneous power draw in kW (0 if not charging)
  session_energy_kwh: 12.3,         // FLOAT - energy delivered in current session (cumulative)

  // Fault information (only set when status = "faulted")
  fault_code: null,                 // STRING - error code (e.g., "ERR_OVERHEAT", "ERR_COMM_LOST")
  fault_message: null,              // STRING - human-readable fault description

  // Timestamps
  last_heartbeat: ISODate("2024-10-21T10:32:45.123Z"),  // Last status update received
  status_changed_at: ISODate("2024-10-21T09:15:00.000Z"), // When status last changed

  // Session tracking (links to MySQL bookings table when occupied)
  active_booking_id: 142,           // INT - booking_id from MySQL, null if not occupied
  session_started_at: ISODate("2024-10-21T09:15:00.000Z"), // When current session began

  created_at: ISODate("2024-10-13T00:00:00.000Z"),
  updated_at: ISODate("2024-10-21T10:32:45.123Z")
}

/**
 * Indexes:
 * - { charger_id: 1 } - unique, for fast charger lookup
 * - { station_id: 1, status: 1 } - for "show me all available chargers at this station"
 * - { city: 1, status: 1 } - for city-wide status queries
 * - { last_heartbeat: 1 } - to detect stale/offline chargers
 *
 * Validation rules:
 * - status must be one of: available, occupied, faulted, maintenance
 * - current_power_kw >= 0
 * - charger_id is required and unique
 */

// MongoDB shell command to create the collection with validation:
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

// Create indexes
db.charger_status.createIndex({ charger_id: 1 }, { unique: true });
db.charger_status.createIndex({ station_id: 1, status: 1 });
db.charger_status.createIndex({ city: 1, status: 1 });
db.charger_status.createIndex({ last_heartbeat: 1 });
