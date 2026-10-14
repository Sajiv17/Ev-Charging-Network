-- =============================================================================
-- OPTIONAL: database-level guard against double booking
-- =============================================================================
-- NOT loaded by init.sh. Apply by hand on a node (or a scratch database):
--   docker exec -i ev-mysql-bangalore mysql -uroot -pevcharge_root_2024 ev_bangalore \
--     < database/mysql/optional/double_booking_guard.sql
--
-- Why it is not on by default: the backend's concurrency demo runs an UNSAFE
-- booking path to show a real double booking. With this guard the second
-- booking would fail with a duplicate-key error (1062) instead, and the anomaly
-- the demo is meant to show could not happen.
--
-- Why you would want it in production: defence in depth. The 2PL booking
-- transaction already prevents double booking; this makes it impossible even if
-- some future code path forgets to lock the slot.
--
-- How it works: a STORED generated column holds slot_id only while the booking
-- is live (confirmed/active) and NULL otherwise. A UNIQUE index allows many NULLs,
-- so any number of cancelled/completed bookings may share a slot, but at most
-- one live booking can.
-- =============================================================================

ALTER TABLE bookings
    ADD COLUMN live_slot_id INT
        AS (CASE WHEN booking_status IN ('confirmed', 'active') THEN slot_id END) STORED
        COMMENT 'slot_id while the booking is live, else NULL (see optional/double_booking_guard.sql)',
    ADD UNIQUE KEY uq_one_live_booking_per_slot (live_slot_id);

-- To remove it again:
--   ALTER TABLE bookings DROP INDEX uq_one_live_booking_per_slot, DROP COLUMN live_slot_id;
