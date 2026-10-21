/**
 * Collection: audit_log
 *
 * Transaction event log for concurrency demo and debugging. Every booking attempt,
 * lock acquisition, commit, and rollback is logged here with microsecond timestamps.
 *
 * This is the "black box" for the concurrency demo — when two users try to book the
 * same slot simultaneously, this log shows exactly which transaction acquired the lock
 * first, which one waited, and which one failed.
 *
 * The backend's audit.py service writes to this collection.
 */

// Example document
{
  _id: ObjectId("..."),

  // Event identification
  event_type: "lock_acquired",      // STRING - type of event (see Event Types below)
  transaction_id: "tx_1729512345_abc123", // STRING - unique transaction ID

  // Context
  user_id: 23,                      // INT - who initiated the transaction
  booking_id: 142,                  // INT - the booking this event relates to (null for failed attempts)
  slot_id: 87,                      // INT - the slot being contested
  charger_id: 5,                    // INT
  city: "bangalore",

  // Lock details (for lock_acquired / lock_wait events)
  lock_mode: "X",                   // STRING - "X" (exclusive) or "S" (shared)
  lock_wait_time_ms: 1250,          // FLOAT - how long this tx waited for the lock (0 if immediate)

  // Transaction outcome (for commit / rollback events)
  success: true,                    // BOOLEAN - did the transaction commit successfully?
  error_message: null,              // STRING - error if failed (e.g., "Slot no longer available")

  // Timing (microsecond precision for concurrency analysis)
  timestamp: ISODate("2024-10-21T10:32:45.123Z"),

  // Additional metadata
  endpoint: "/api/bookings",        // STRING - API endpoint that triggered this
  request_id: "req_xyz789",         // STRING - HTTP request ID (for correlation)

  // XA transaction details (for cross-city bookings)
  xa_global_id: null,               // STRING - XA global transaction ID (if this was a distributed tx)
  participant_cities: null,         // ARRAY - ["bangalore", "chennai"] for cross-city bookings

  created_at: ISODate("2024-10-21T10:32:45.123Z")
}

/**
 * Event Types:
 * - "lock_acquired" - transaction acquired exclusive lock on slot
 * - "lock_wait" - transaction is waiting for lock (another tx holds it)
 * - "lock_timeout" - transaction gave up waiting
 * - "slot_check" - checked if slot is available
 * - "wallet_debit" - debited payment from wallet
 * - "booking_created" - booking record inserted
 * - "commit" - transaction committed successfully
 * - "rollback" - transaction rolled back (error or conflict)
 * - "xa_prepare" - XA transaction prepared (cross-city booking)
 * - "xa_commit" - XA transaction committed globally
 * - "xa_rollback" - XA transaction rolled back globally
 */

/**
 * Indexes:
 * - { transaction_id: 1 } - trace all events for one transaction
 * - { slot_id: 1, timestamp: 1 } - timeline of all attempts on a slot
 * - { user_id: 1, timestamp: -1 } - user's transaction history
 * - { event_type: 1, timestamp: -1 } - all lock acquisitions, chronologically
 * - { timestamp: -1 } - recent events first (for live monitoring)
 * - { request_id: 1 } - correlate all events from one HTTP request
 */

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
        city: { bsonType: ["string", "null"], enum: ["bangalore", "chennai", "delhi", null] },
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
