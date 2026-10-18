-- =============================================================================
-- Readable error for a negative wallet
-- =============================================================================
-- chk_wallet_non_negative (02_core.sql) is the real guarantee. This trigger only
-- replaces MySQL's generic "Check constraint ... is violated" with a message
-- that names the user, for the mysql CLI and stored-procedure demos.
-- =============================================================================

DROP TRIGGER IF EXISTS trg_users_wallet_guard;

DELIMITER $$

CREATE TRIGGER trg_users_wallet_guard
BEFORE UPDATE ON users
FOR EACH ROW
BEGIN
    DECLARE v_msg VARCHAR(128);
    IF NEW.wallet_balance < 0 THEN
        SET v_msg = CONCAT('Insufficient wallet balance: user ', NEW.user_id,
                           ' would go to Rs ', NEW.wallet_balance);
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = v_msg;
    END IF;
END$$

DELIMITER ;
