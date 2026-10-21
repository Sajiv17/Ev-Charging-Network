/**
 * Collection: charging_sessions
 *
 * Detailed logs of active and completed charging sessions. Each session captures
 * the continuous energy delivery data that doesn't fit well in MySQL's structured
 * booking table.
 *
 * When a driver starts charging, a document is created here with status "active".
 * The status simulator updates session_energy_kwh and power samples every 5-10 seconds.
 * When the session ends, status → "completed" and final billing data is recorded.
 *
 * The backend uses this for:
 * - Real-time session monitoring (how much energy delivered so far)
 * - Energy consumption graphs for the driver
 * - Billing calculations (kWh consumed × rate)
 */

// Example document
{
  _id: ObjectId("..."),

  // Links to MySQL
  booking_id: 142,                  // INT - MySQL bookings.booking_id
  charger_id: 5,                    // INT - MySQL charger_units.charger_id
  user_id: 23,                      // INT - MySQL users.user_id
  station_id: 2,                    // INT - MySQL stations.station_id
  city: "bangalore",

  // Session lifecycle
  status: "active",                 // ENUM: "active" | "completed" | "interrupted"

  // Timestamps
  session_started_at: ISODate("2024-10-21T09:15:00.000Z"),
  session_ended_at: null,           // ISODate when completed/interrupted, null while active

  // Energy tracking
  session_energy_kwh: 12.3,         // FLOAT - cumulative energy delivered (updated live)
  final_energy_kwh: null,           // FLOAT - locked when session ends

  // Power samples (optional: for graphing charge curve)
  power_samples: [
    { timestamp: ISODate("2024-10-21T09:15:00Z"), power_kw: 48.2 },
    { timestamp: ISODate("2024-10-21T09:20:00Z"), power_kw: 47.8 },
    { timestamp: ISODate("2024-10-21T09:25:00Z"), power_kw: 45.1 }
    // ... sampled every 5 minutes
  ],

  // Billing (calculated when session ends)
  rate_per_kwh: 12.50,              // FLOAT - price per kWh (from MySQL pricing_plans)
  energy_cost: null,                // FLOAT - final_energy_kwh × rate (set when session ends)

  // Metadata
  charger_type: "DC",               // ENUM: "AC" | "DC" (copied from MySQL for analytics)
  vehicle_make: "Tata",             // STRING - for analytics
  vehicle_model: "Nexon EV",

  created_at: ISODate("2024-10-21T09:15:00.000Z"),
  updated_at: ISODate("2024-10-21T10:32:45.123Z")
}

/**
 * Indexes:
 * - { booking_id: 1 } - unique, to find session by booking
 * - { charger_id: 1, status: 1 } - active sessions on a charger
 * - { user_id: 1, session_started_at: -1 } - user's session history
 * - { city: 1, session_started_at: -1 } - city-wide session logs
 * - { status: 1, session_started_at: -1 } - find stale active sessions
 */

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
