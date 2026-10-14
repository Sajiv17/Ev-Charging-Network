-- =============================================================================
-- sp_get_station_load(p_station_id, p_date): hourly load for the dashboards
-- =============================================================================
-- One row per hour that has slots at the station on that date:
--   hour_of_day, total_slots, booked_slots, bookings, utilisation_pct
-- A slot counts as booked if it has a confirmed, active or completed booking;
-- cancelled bookings are ignored. bookings can exceed booked_slots only after
-- an unsafe-mode double booking, which makes the demo anomaly visible here too.
-- =============================================================================

DROP PROCEDURE IF EXISTS sp_get_station_load;

DELIMITER $$

CREATE PROCEDURE sp_get_station_load(IN p_station_id INT, IN p_date DATE)
BEGIN
    IF NOT EXISTS (SELECT 1 FROM stations WHERE station_id = p_station_id) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Station not found on this node';
    END IF;

    SELECT HOUR(sl.slot_start_time)                                       AS hour_of_day,
           COUNT(DISTINCT sl.slot_id)                                     AS total_slots,
           COUNT(DISTINCT CASE WHEN b.booking_id IS NOT NULL THEN sl.slot_id END) AS booked_slots,
           COUNT(b.booking_id)                                            AS bookings,
           ROUND(100 * COUNT(DISTINCT CASE WHEN b.booking_id IS NOT NULL THEN sl.slot_id END)
                 / COUNT(DISTINCT sl.slot_id), 1)                         AS utilisation_pct
      FROM slots sl
      JOIN charger_units c ON c.charger_id = sl.charger_id
      LEFT JOIN bookings b ON b.slot_id = sl.slot_id
                          AND b.booking_status IN ('confirmed', 'active', 'completed')
     WHERE c.station_id = p_station_id
       AND sl.slot_date = p_date
     GROUP BY HOUR(sl.slot_start_time)
     ORDER BY hour_of_day;
END$$

DELIMITER ;
