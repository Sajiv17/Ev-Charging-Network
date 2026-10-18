-- =============================================================================
-- sp_generate_slots(p_days) + daily event
-- =============================================================================
-- For every charger on THIS node, create 1-hour slots 06:00-22:00 for each day
-- from today to today + p_days (inclusive). Hours that already have a slot (or
-- any slot overlapping them) are skipped, so the call is idempotent and never
-- trips trg_slots_no_overlap_insert.
--
-- Called by each city seed (CALL sp_generate_slots(7)) and by the daily event
-- below, so the demo always has a week of future slots.
-- =============================================================================

DROP PROCEDURE IF EXISTS sp_generate_slots;
DROP EVENT IF EXISTS ev_daily_slot_generation;

DELIMITER $$

CREATE PROCEDURE sp_generate_slots(IN p_days INT)
BEGIN
    DECLARE v_created INT DEFAULT 0;

    -- Recursive CTE depth is capped by cte_max_recursion_depth (default 1000).
    IF p_days IS NULL OR p_days < 0 OR p_days > 365 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'p_days must be between 0 and 365';
    END IF;

    INSERT INTO slots (charger_id, slot_date, slot_start_time, slot_end_time, is_available)
    WITH RECURSIVE
        days (n) AS (SELECT 0 UNION ALL SELECT n + 1 FROM days WHERE n < p_days),
        hours (h) AS (SELECT 6 UNION ALL SELECT h + 1 FROM hours WHERE h < 21)
    SELECT c.charger_id,
           CURDATE() + INTERVAL d.n DAY,
           MAKETIME(hr.h, 0, 0),
           MAKETIME(hr.h + 1, 0, 0),
           TRUE
      FROM charger_units c
     CROSS JOIN days d
     CROSS JOIN hours hr
     WHERE NOT EXISTS (SELECT 1 FROM slots s
                        WHERE s.charger_id = c.charger_id
                          AND s.slot_date = CURDATE() + INTERVAL d.n DAY
                          AND s.slot_start_time < MAKETIME(hr.h + 1, 0, 0)
                          AND s.slot_end_time > MAKETIME(hr.h, 0, 0));

    SET v_created = ROW_COUNT();
    SELECT v_created AS slots_created;
END$$

DELIMITER ;

-- CURDATE() is IST: the event stores the creating session's time zone, and every
-- node runs with --default-time-zone=+05:30. 00:05 so "today" has just rolled over.
CREATE EVENT ev_daily_slot_generation
    ON SCHEDULE EVERY 1 DAY
    STARTS (CURRENT_DATE + INTERVAL 1 DAY + INTERVAL 5 MINUTE)
    ON COMPLETION PRESERVE
    COMMENT 'Keeps a rolling 7-day window of future slots on this node'
    DO CALL sp_generate_slots(7);
