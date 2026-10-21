/**
 * Collection: fault_reports
 *
 * Operator-submitted fault reports with photos, error descriptions, and resolution logs.
 * This is unstructured data that doesn't fit MySQL's rigid schema — each charger model
 * has different error codes, operators may attach multiple photos, descriptions vary in length.
 *
 * When a charger faults, the MySQL trigger creates a refund and operator_alerts row.
 * The operator then uses the web UI to file a detailed fault report here, which MongoDB
 * stores flexibly.
 */

// Example document
{
  _id: ObjectId("..."),

  // Links to MySQL
  charger_id: 5,
  station_id: 2,
  operator_id: 8,                   // INT - user_id of the operator who filed this
  city: "bangalore",

  // Fault details
  fault_type: "hardware_failure",   // STRING - category (not enforced enum, operators pick freely)
  error_code: "ERR_OVERHEAT_CPU",   // STRING - charger-specific error code
  severity: "critical",             // ENUM: "low" | "medium" | "high" | "critical"

  // Description (free-form text)
  description: "Charger CPU temperature reached 95°C. Automatic shutdown triggered. Visual inspection shows dust buildup in cooling fan.",

  // Attachments (photos of the fault)
  photos: [
    {
      filename: "charger_5_fault_20241021_1.jpg",
      url: "https://storage.example.com/faults/charger_5_fault_20241021_1.jpg",
      uploaded_at: ISODate("2024-10-21T10:45:00.000Z")
    },
    {
      filename: "charger_5_fault_20241021_2.jpg",
      url: "https://storage.example.com/faults/charger_5_fault_20241021_2.jpg",
      uploaded_at: ISODate("2024-10-21T10:46:00.000Z")
    }
  ],

  // Resolution tracking
  resolution_status: "in_progress",  // ENUM: "open" | "in_progress" | "resolved" | "escalated"
  resolution_notes: "Technician dispatched. ETA 2 hours.",
  resolved_at: null,                // ISODate when resolved
  resolved_by: null,                // INT - user_id of technician/operator who resolved it

  // Downtime tracking
  fault_reported_at: ISODate("2024-10-21T10:30:00.000Z"),
  estimated_repair_time_hours: 4,  // FLOAT - operator's estimate
  actual_repair_time_hours: null,  // FLOAT - calculated when resolved

  // Metadata
  charger_make: "ABB",
  charger_model: "Terra 184",

  created_at: ISODate("2024-10-21T10:30:00.000Z"),
  updated_at: ISODate("2024-10-21T10:50:00.000Z")
}

/**
 * Indexes:
 * - { charger_id: 1, fault_reported_at: -1 } - fault history per charger
 * - { station_id: 1, resolution_status: 1 } - open faults per station
 * - { operator_id: 1 } - faults filed by operator
 * - { resolution_status: 1, fault_reported_at: -1 } - prioritize unresolved faults
 * - { city: 1, severity: 1 } - critical faults per city
 */

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
