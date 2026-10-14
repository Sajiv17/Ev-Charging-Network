-- =============================================================================
-- sp_create_booking: the single-node booking transaction, in SQL
-- =============================================================================
-- NOT CALLED BY THE BACKEND. booking_service.create_booking_with_lock is the
-- production path. This procedure is the same Strict 2PL transaction written in
-- SQL, for the DB-side viva demonstration and for scripts/db/run_db_tests.sh.
--
-- Same lock order as the backend: slot row first, then the user's wallet row.
-- Same checks: slot exists, is available, is in the future, charger in service,
-- vehicle belongs to the user and fits the connector, pricing plan exists,
-- wallet covers the prepaid amount.
-- Same price: booking_fee + rate_per_kwh * min(max_power_kw * slot_hours, battery_kwh).
--
-- Single-node only: the user's home node must be this node (the wallet is only
-- authoritative there). Cross-city bookings need the coordinator's 2PC.
--
-- Runs its own transaction: do not CALL it inside an open transaction
-- (START TRANSACTION would implicitly commit the caller's work).
-- Any error rolls everything back and is re-raised to the caller.
-- =============================================================================

DROP PROCEDURE IF EXISTS sp_create_booking;

DELIMITER $$

CREATE PROCEDURE sp_create_booking(
    IN  p_user_id    INT,
    IN  p_slot_id    INT,
    IN  p_vehicle_id INT,
    OUT p_booking_id INT,
    OUT p_amount     DECIMAL(10, 2)
)
BEGIN
    DECLARE v_slot_date DATE;
    DECLARE v_start TIME;
    DECLARE v_end TIME;
    DECLARE v_available BOOLEAN;
    DECLARE v_is_future BOOLEAN;
    DECLARE v_charger_status VARCHAR(20);
    DECLARE v_charger_type VARCHAR(2);
    DECLARE v_connector VARCHAR(10);
    DECLARE v_power DECIMAL(5, 2);
    DECLARE v_operational BOOLEAN;
    DECLARE v_city INT;
    DECLARE v_vehicle_user INT;
    DECLARE v_vehicle_connector VARCHAR(10);
    DECLARE v_battery DECIMAL(5, 2);
    DECLARE v_rate DECIMAL(6, 2);
    DECLARE v_fee DECIMAL(6, 2);
    DECLARE v_balance DECIMAL(10, 2);
    DECLARE v_home_city INT;
    DECLARE v_amount DECIMAL(10, 2);
    DECLARE v_msg VARCHAR(128);

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;  -- releases every lock taken so far
        RESIGNAL;
    END;

    SET p_booking_id = NULL, p_amount = NULL;

    START TRANSACTION;

    -- ---- Growing phase, lock 1: the slot row (X) ---------------------------------
    SELECT sl.slot_date, sl.slot_start_time, sl.slot_end_time, sl.is_available,
           TIMESTAMP(sl.slot_date, sl.slot_start_time) > NOW(),
           c.status, c.charger_type, c.connector_type, c.max_power_kw,
           s.is_operational, s.city_id
      INTO v_slot_date, v_start, v_end, v_available, v_is_future,
           v_charger_status, v_charger_type, v_connector, v_power,
           v_operational, v_city
      FROM slots sl
      JOIN charger_units c ON c.charger_id = sl.charger_id
      JOIN stations s      ON s.station_id = c.station_id
     WHERE sl.slot_id = p_slot_id
       FOR UPDATE OF sl;

    IF v_slot_date IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Slot not found on this node';
    END IF;
    IF NOT v_available THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Slot already booked';
    END IF;
    IF NOT v_is_future THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Slot start time has already passed';
    END IF;
    IF v_charger_status IN ('faulted', 'maintenance') OR NOT v_operational THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Charger is out of service';
    END IF;

    SELECT user_id, connector_type, battery_capacity_kwh
      INTO v_vehicle_user, v_vehicle_connector, v_battery
      FROM vehicles WHERE vehicle_id = p_vehicle_id;

    IF v_vehicle_user IS NULL OR v_vehicle_user <> p_user_id THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Vehicle not found';
    END IF;
    IF v_vehicle_connector <> v_connector THEN
        SET v_msg = CONCAT('Vehicle connector ', v_vehicle_connector, ' does not fit this charger (', v_connector, ')');
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = v_msg;
    END IF;

    -- Same query as pricing.get_plan.
    SELECT rate_per_kwh, booking_fee INTO v_rate, v_fee
      FROM pricing_plans
     WHERE city_id = v_city AND charger_type = v_charger_type
       AND effective_from <= v_slot_date
       AND (effective_to IS NULL OR effective_to >= v_slot_date)
     ORDER BY effective_from DESC
     LIMIT 1;

    IF v_rate IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'No pricing plan for this charger type';
    END IF;

    -- Same formula as pricing.prepaid_amount (ROUND on DECIMAL is half-up, like ROUND_HALF_UP).
    SET v_amount = ROUND(
        COALESCE(v_fee, 0)
        + v_rate * LEAST(v_power * TIME_TO_SEC(TIMEDIFF(v_end, v_start)) / 3600, v_battery),
        2);

    -- ---- Growing phase, lock 2: the wallet row (X) -------------------------------
    SELECT wallet_balance, home_city_id INTO v_balance, v_home_city
      FROM users WHERE user_id = p_user_id
       FOR UPDATE;

    IF v_balance IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'User not found on this node';
    END IF;
    IF v_home_city <> v_city THEN
        -- The copy of the wallet on this node is not authoritative.
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Cross-city booking: wallet is on another node (needs 2PC)';
    END IF;
    IF v_balance < v_amount THEN
        SET v_msg = CONCAT('Wallet balance Rs ', v_balance, ' is less than the booking amount Rs ', v_amount);
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = v_msg;
    END IF;

    -- ---- All checks passed: writes -----------------------------------------------
    UPDATE users SET wallet_balance = wallet_balance - v_amount WHERE user_id = p_user_id;

    INSERT INTO bookings (user_id, slot_id, vehicle_id, booking_status, booking_amount)
    VALUES (p_user_id, p_slot_id, p_vehicle_id, 'confirmed', v_amount);
    SET p_booking_id = LAST_INSERT_ID();

    -- 'SP-' prefix tells these apart from the backend's 'WLT-' references.
    INSERT INTO payments (booking_id, amount, payment_method, payment_status, transaction_id)
    VALUES (p_booking_id, v_amount, 'wallet', 'completed',
            CONCAT('SP-', UPPER(LEFT(REPLACE(UUID(), '-', ''), 16))));

    UPDATE slots SET is_available = FALSE WHERE slot_id = p_slot_id;

    -- ---- Shrinking phase: COMMIT releases all locks at once ----------------------
    COMMIT;
    SET p_amount = v_amount;
END$$

DELIMITER ;
