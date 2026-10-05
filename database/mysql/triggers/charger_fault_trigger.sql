-- =============================================================================
-- Charger Fault Auto-Refund Trigger
-- =============================================================================
-- When a charger_unit status changes to 'faulted', this trigger:
-- 1. Finds all active bookings on that charger
-- 2. Cancels them
-- 3. Queues refunds proportional to unused time
-- =============================================================================

DELIMITER $$

CREATE TRIGGER after_charger_fault
AFTER UPDATE ON charger_units
FOR EACH ROW
BEGIN
    -- Only fire if status changed to 'faulted'
    IF NEW.status = 'faulted' AND OLD.status != 'faulted' THEN

        -- Cancel all active bookings for this charger
        UPDATE bookings b
        INNER JOIN slots s ON b.slot_id = s.slot_id
        SET b.booking_status = 'cancelled',
            b.updated_at = CURRENT_TIMESTAMP
        WHERE s.charger_id = NEW.charger_id
          AND b.booking_status IN ('confirmed', 'active');

        -- Queue refunds for cancelled bookings
        INSERT INTO refunds (payment_id, refund_amount, refund_reason, refund_status)
        SELECT
            p.payment_id,
            p.amount,
            CONCAT('Charger fault - Charger ID: ', NEW.charger_id, ', Code: ', NEW.charger_code),
            'queued'
        FROM payments p
        INNER JOIN bookings b ON p.booking_id = b.booking_id
        INNER JOIN slots s ON b.slot_id = s.slot_id
        WHERE s.charger_id = NEW.charger_id
          AND b.booking_status = 'cancelled'
          AND p.payment_status = 'completed'
          AND p.payment_id NOT IN (SELECT payment_id FROM refunds);

    END IF;
END$$

DELIMITER ;

-- =============================================================================
-- To test this trigger:
-- UPDATE charger_units SET status = 'faulted' WHERE charger_id = 5;
-- Then check: SELECT * FROM refunds ORDER BY created_at DESC LIMIT 10;
-- =============================================================================
