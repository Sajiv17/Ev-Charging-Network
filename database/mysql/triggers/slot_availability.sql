-- =============================================================================
-- Keep slots.is_available consistent with the bookings on the slot
-- =============================================================================
-- is_available is controlled redundancy (docs/NORMALIZATION.md): it equals
-- "no live (confirmed/active) booking on this slot", and the backend's 2PL
-- transaction locks the slot row and flips it. These triggers make the flag
-- follow the bookings table even when bookings change outside the backend
-- (mysql CLI, stored procedures, the fault trigger).
--
-- They only ever touch the booking's own slot row, which the backend's booking
-- and cancel transactions already hold an X lock on, so they add no new lock
-- and do not change the lock order (slot -> wallet).
--
-- MySQL limitation (error 1442): a statement that READS slots cannot fire a
-- trigger that WRITES slots, so use INSERT INTO bookings ... VALUES (...), not
-- INSERT INTO bookings ... SELECT ... FROM slots. The backend only uses VALUES.
-- =============================================================================

DROP TRIGGER IF EXISTS trg_bookings_slot_after_insert;
DROP TRIGGER IF EXISTS trg_bookings_slot_after_update;

DELIMITER $$

CREATE TRIGGER trg_bookings_slot_after_insert
AFTER INSERT ON bookings
FOR EACH ROW
BEGIN
    IF NEW.booking_status IN ('confirmed', 'active') THEN
        UPDATE slots SET is_available = FALSE WHERE slot_id = NEW.slot_id AND is_available = TRUE;
    END IF;
END$$

CREATE TRIGGER trg_bookings_slot_after_update
AFTER UPDATE ON bookings
FOR EACH ROW
BEGIN
    DECLARE v_charger_status VARCHAR(20);

    IF NEW.booking_status IN ('confirmed', 'active')
       AND OLD.booking_status NOT IN ('confirmed', 'active') THEN
        UPDATE slots SET is_available = FALSE WHERE slot_id = NEW.slot_id AND is_available = TRUE;

    ELSEIF NEW.booking_status = 'cancelled'
       AND OLD.booking_status IN ('confirmed', 'active') THEN
        SELECT c.status INTO v_charger_status
          FROM slots sl JOIN charger_units c ON c.charger_id = sl.charger_id
         WHERE sl.slot_id = NEW.slot_id;

        -- A faulted/maintenance charger keeps its slots closed until repaired
        -- (after_charger_fault re-opens them); past slots are never re-opened.
        IF v_charger_status IN ('available', 'occupied') THEN
            UPDATE slots sl
               SET sl.is_available = TRUE
             WHERE sl.slot_id = NEW.slot_id
               AND sl.is_available = FALSE
               AND TIMESTAMP(sl.slot_date, sl.slot_start_time) > NOW()
               -- After an (unsafe-demo) double booking another live booking may remain.
               AND NOT EXISTS (SELECT 1 FROM bookings b
                                WHERE b.slot_id = NEW.slot_id
                                  AND b.booking_status IN ('confirmed', 'active'));
        END IF;
    END IF;
END$$

DELIMITER ;
