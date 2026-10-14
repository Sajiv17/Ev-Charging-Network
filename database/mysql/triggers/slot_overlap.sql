-- =============================================================================
-- No two slots on the same charger may overlap in time
-- =============================================================================
-- unique_slot only stops two slots with the SAME start time; 10:00-11:00 and
-- 10:30-11:30 would both pass it. Intervals are half-open [start, end), so
-- back-to-back slots (10:00-11:00, 11:00-12:00) are fine; that is what
-- sp_generate_slots and the backend's demo_service.create_fresh_slot produce.
--
-- The probe is a plain (non-locking) read, so two sessions inserting
-- overlapping slots at the same instant could both pass. Slots are created by
-- one admin job at a time, so we accept that rather than take gap locks that
-- would make concurrent slot generation deadlock-prone.
-- =============================================================================

DROP TRIGGER IF EXISTS trg_slots_no_overlap_insert;
DROP TRIGGER IF EXISTS trg_slots_no_overlap_update;

DELIMITER $$

CREATE TRIGGER trg_slots_no_overlap_insert
BEFORE INSERT ON slots
FOR EACH ROW
BEGIN
    IF EXISTS (SELECT 1 FROM slots s
                WHERE s.charger_id = NEW.charger_id
                  AND s.slot_date = NEW.slot_date
                  AND s.slot_start_time < NEW.slot_end_time
                  AND s.slot_end_time > NEW.slot_start_time) THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Slot overlaps an existing slot on the same charger and date';
    END IF;
END$$

CREATE TRIGGER trg_slots_no_overlap_update
BEFORE UPDATE ON slots
FOR EACH ROW
BEGIN
    -- The 2PL booking flips is_available on every booking; only re-check when the interval moves.
    IF NOT (NEW.charger_id <=> OLD.charger_id AND NEW.slot_date <=> OLD.slot_date
            AND NEW.slot_start_time <=> OLD.slot_start_time AND NEW.slot_end_time <=> OLD.slot_end_time) THEN
        IF EXISTS (SELECT 1 FROM slots s
                    WHERE s.charger_id = NEW.charger_id
                      AND s.slot_date = NEW.slot_date
                      AND s.slot_id <> NEW.slot_id
                      AND s.slot_start_time < NEW.slot_end_time
                      AND s.slot_end_time > NEW.slot_start_time) THEN
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'Slot overlaps an existing slot on the same charger and date';
        END IF;
    END IF;
END$$

DELIMITER ;
