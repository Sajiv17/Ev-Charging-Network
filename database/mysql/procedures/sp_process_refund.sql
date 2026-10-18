-- =============================================================================
-- sp_process_refund(p_refund_id): settle a queued refund
-- =============================================================================
-- Refunds live on the station's node, next to the payment. The money goes to
-- the user's wallet, which is only authoritative on the user's HOME node.
--
--   home node = this node -> credit the wallet here, mark the refund completed.
--   home node elsewhere   -> change nothing; return what the coordinator needs
--                            to credit the home node (backend phase 2), after
--                            which it marks the refund completed here.
--
-- Always returns one row:
--   refund_id, outcome ('completed' | 'remote'), user_id, home_city_id, amount
-- Errors (refund missing, not queued) are raised with SQLSTATE 45000.
-- Runs its own transaction; do not CALL it inside an open transaction.
-- =============================================================================

DROP PROCEDURE IF EXISTS sp_process_refund;

DELIMITER $$

CREATE PROCEDURE sp_process_refund(IN p_refund_id INT)
BEGIN
    DECLARE v_status VARCHAR(20);
    DECLARE v_amount DECIMAL(10, 2);
    DECLARE v_user_id INT;
    DECLARE v_node_city INT;
    DECLARE v_home_city INT;
    DECLARE v_msg VARCHAR(128);

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    START TRANSACTION;

    -- Lock the refund row so two workers cannot pay the same refund twice.
    SELECT r.refund_status, r.refund_amount, b.user_id, s.city_id
      INTO v_status, v_amount, v_user_id, v_node_city
      FROM refunds r
      JOIN payments p      ON p.payment_id = r.payment_id
      JOIN bookings b      ON b.booking_id = p.booking_id
      JOIN slots sl        ON sl.slot_id = b.slot_id
      JOIN charger_units c ON c.charger_id = sl.charger_id
      JOIN stations s      ON s.station_id = c.station_id
     WHERE r.refund_id = p_refund_id
       FOR UPDATE OF r;

    IF v_status IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Refund not found on this node';
    END IF;
    IF v_status <> 'queued' THEN
        SET v_msg = CONCAT('Refund ', p_refund_id, ' is already ', v_status);
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = v_msg;
    END IF;

    -- home_city_id is replicated and never changes, so any node's copy can answer this.
    SELECT home_city_id INTO v_home_city FROM users WHERE user_id = v_user_id;

    IF v_home_city = v_node_city THEN
        UPDATE users SET wallet_balance = wallet_balance + v_amount WHERE user_id = v_user_id;
        UPDATE refunds SET refund_status = 'completed', processed_at = NOW() WHERE refund_id = p_refund_id;
        COMMIT;
        SELECT p_refund_id AS refund_id, 'completed' AS outcome,
               v_user_id AS user_id, v_home_city AS home_city_id, v_amount AS amount;
    ELSE
        COMMIT;  -- nothing written; just releases the row lock
        SELECT p_refund_id AS refund_id, 'remote' AS outcome,
               v_user_id AS user_id, v_home_city AS home_city_id, v_amount AS amount;
    END IF;
END$$

DELIMITER ;
