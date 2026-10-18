-- =============================================================================
-- Charger fault -> cancel + refund, and charger repair -> re-open slots
-- =============================================================================
-- AFTER UPDATE on charger_units, two branches:
--
-- 1. status changes TO 'faulted'
--    Affected bookings on this charger:
--      * every 'active' booking (charging session in progress), and
--      * every 'confirmed' booking whose slot has not ended yet.
--    Bookings cancelled earlier are never touched.
--    For each affected booking:
--      * active    -> refund the unused share of the slot:
--                     (slot_end - NOW()) / (slot_end - session start) x amount paid
--                     (session start = session_start_time, or slot start if NULL)
--      * confirmed -> full refund
--      * booking -> 'cancelled', its completed payment -> 'refunded'
--      * refund row, in the same shape as booking_service.cancel_booking:
--          - user's home node is THIS node (users.home_city_id = station city):
--            wallet credited here, refund 'completed' with processed_at = NOW()
--          - otherwise: refund 'queued'; the coordinator applies it on the
--            home node (backend phase 2, see sp_process_refund)
--    Slots of the cancelled bookings stay is_available = FALSE: the backend
--    already refuses faulted chargers, and the slots re-open on repair.
--
-- 2. status changes from 'faulted' TO 'available'
--    Re-open this charger's future slots that have no live booking.
--
-- Both branches end by writing one operator_alerts row for the station's
-- operator (the "operator alerted" step): bookings cancelled, amount refunded
-- here, amount queued for other nodes, slots re-opened. That row is also the
-- trigger's own log for the demo: SELECT * FROM operator_alerts.
--
-- NOW() is IST because every node runs with --default-time-zone=+05:30, so the
-- refund is the same whether the fault is fired by the backend or the mysql CLI.
-- =============================================================================

DROP TRIGGER IF EXISTS after_charger_fault;

DELIMITER $$

CREATE TRIGGER after_charger_fault
AFTER UPDATE ON charger_units
FOR EACH ROW
BEGIN
    DECLARE v_ids JSON;
    DECLARE v_n INT DEFAULT 0;
    DECLARE v_i INT DEFAULT 0;
    DECLARE v_booking_id INT;
    DECLARE v_status VARCHAR(20);
    DECLARE v_user_id INT;
    DECLARE v_station_city INT;
    DECLARE v_home_city INT;
    DECLARE v_slot_start DATETIME;
    DECLARE v_slot_end DATETIME;
    DECLARE v_session_start DATETIME;
    DECLARE v_total_s BIGINT;
    DECLARE v_unused_s BIGINT;
    DECLARE v_payment_id INT;
    DECLARE v_paid DECIMAL(10, 2);
    DECLARE v_refund DECIMAL(10, 2);
    DECLARE v_operator_id INT;
    DECLARE v_refunded DECIMAL(10, 2) DEFAULT 0;
    DECLARE v_queued DECIMAL(10, 2) DEFAULT 0;
    DECLARE v_reopened INT DEFAULT 0;

    SELECT city_id, operator_id INTO v_station_city, v_operator_id
      FROM stations WHERE station_id = NEW.station_id;

    IF NEW.status = 'faulted' AND OLD.status <> 'faulted' THEN

        -- Capture the affected IDs first, so the later UPDATEs (which change
        -- booking_status) cannot change which bookings we act on.
        SELECT JSON_ARRAYAGG(b.booking_id) INTO v_ids
        FROM bookings b
        JOIN slots sl ON sl.slot_id = b.slot_id
        WHERE sl.charger_id = NEW.charger_id
          AND (b.booking_status = 'active'
               OR (b.booking_status = 'confirmed'
                   AND TIMESTAMP(sl.slot_date, sl.slot_end_time) > NOW()));

        SET v_n = COALESCE(JSON_LENGTH(v_ids), 0);

        WHILE v_i < v_n DO
            SET v_booking_id = JSON_EXTRACT(v_ids, CONCAT('$[', v_i, ']'));

            SELECT b.booking_status, b.user_id, b.session_start_time,
                   TIMESTAMP(sl.slot_date, sl.slot_start_time),
                   TIMESTAMP(sl.slot_date, sl.slot_end_time)
              INTO v_status, v_user_id, v_session_start, v_slot_start, v_slot_end
              FROM bookings b
              JOIN slots sl ON sl.slot_id = b.slot_id
             WHERE b.booking_id = v_booking_id;

            -- Reset first: SELECT ... INTO leaves variables unchanged when no row matches.
            SET v_payment_id = NULL, v_paid = NULL, v_refund = 0;
            SELECT payment_id, amount INTO v_payment_id, v_paid
              FROM payments
             WHERE booking_id = v_booking_id AND payment_status = 'completed'
             ORDER BY payment_id
             LIMIT 1;

            IF v_payment_id IS NOT NULL THEN
                IF v_status = 'active' THEN
                    SET v_total_s = TIMESTAMPDIFF(SECOND, COALESCE(v_session_start, v_slot_start), v_slot_end);
                    SET v_unused_s = TIMESTAMPDIFF(SECOND, NOW(), v_slot_end);
                    -- Clamp to [0, total]: a fault before the session starts refunds 100%,
                    -- a fault after the slot ended refunds nothing.
                    IF v_total_s > 0 THEN
                        SET v_refund = ROUND(v_paid * GREATEST(0, LEAST(v_unused_s, v_total_s)) / v_total_s, 2);
                    END IF;
                ELSE
                    SET v_refund = v_paid;
                END IF;
            END IF;

            UPDATE bookings
               SET booking_status = 'cancelled',
                   -- An interrupted session ends now (GREATEST keeps chk_booking_session valid).
                   session_end_time = IF(v_status = 'active' AND session_start_time IS NOT NULL,
                                         GREATEST(NOW(), session_start_time), session_end_time)
             WHERE booking_id = v_booking_id;

            -- chk_refund_amount requires > 0, so a zero refund leaves the payment 'completed'.
            IF v_refund > 0 THEN
                UPDATE payments SET payment_status = 'refunded' WHERE payment_id = v_payment_id;

                SELECT home_city_id INTO v_home_city FROM users WHERE user_id = v_user_id;

                IF v_home_city = v_station_city THEN
                    -- This node holds the authoritative wallet: settle immediately.
                    UPDATE users SET wallet_balance = wallet_balance + v_refund WHERE user_id = v_user_id;
                    INSERT INTO refunds (payment_id, refund_amount, refund_reason, refund_status, processed_at)
                    VALUES (v_payment_id, v_refund,
                            CONCAT('Charger fault: ', NEW.charger_code, ' (charger ', NEW.charger_id, '), ',
                                   IF(v_status = 'active', 'unused session time', 'slot not started')),
                            'completed', NOW());
                    SET v_refunded = v_refunded + v_refund;
                ELSE
                    -- Wallet lives on another node; a local credit would hit a non-authoritative copy.
                    INSERT INTO refunds (payment_id, refund_amount, refund_reason, refund_status)
                    VALUES (v_payment_id, v_refund,
                            CONCAT('Charger fault: ', NEW.charger_code, ' (charger ', NEW.charger_id, '), ',
                                   IF(v_status = 'active', 'unused session time', 'slot not started'),
                                   '; wallet on node ', v_home_city),
                            'queued');
                    SET v_queued = v_queued + v_refund;
                END IF;
            END IF;

            SET v_i = v_i + 1;
        END WHILE;

        INSERT INTO operator_alerts (charger_id, operator_id, alert_type, bookings_cancelled,
                                     refunded_amount, queued_refund_amount, message)
        VALUES (NEW.charger_id, v_operator_id, 'charger_faulted', v_n, v_refunded, v_queued,
                CONCAT('Charger ', NEW.charger_code, ' (', NEW.charger_id, ') faulted: ', v_n,
                       ' booking(s) cancelled, Rs ', v_refunded, ' refunded, Rs ', v_queued,
                       ' queued for other nodes'));

    ELSEIF OLD.status = 'faulted' AND NEW.status = 'available' THEN

        UPDATE slots sl
           SET sl.is_available = TRUE
         WHERE sl.charger_id = NEW.charger_id
           AND sl.is_available = FALSE
           AND TIMESTAMP(sl.slot_date, sl.slot_start_time) > NOW()
           AND NOT EXISTS (SELECT 1 FROM bookings b
                            WHERE b.slot_id = sl.slot_id
                              AND b.booking_status IN ('confirmed', 'active'));
        SET v_reopened = ROW_COUNT();

        INSERT INTO operator_alerts (charger_id, operator_id, alert_type, slots_reopened, message)
        VALUES (NEW.charger_id, v_operator_id, 'charger_repaired', v_reopened,
                CONCAT('Charger ', NEW.charger_code, ' (', NEW.charger_id, ') repaired: ',
                       v_reopened, ' future slot(s) re-opened'));

    END IF;
END$$

DELIMITER ;

-- =============================================================================
-- Try it:
--   UPDATE charger_units SET status = 'faulted' WHERE charger_id = 5;
--   SELECT * FROM refunds ORDER BY created_at DESC LIMIT 10;
--   SELECT * FROM operator_alerts ORDER BY alert_id DESC LIMIT 5;
--   UPDATE charger_units SET status = 'available' WHERE charger_id = 5;
-- =============================================================================
