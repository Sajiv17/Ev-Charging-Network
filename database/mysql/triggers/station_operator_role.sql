-- =============================================================================
-- A station can only be run by a user in the OPERATOR (or ADMIN) subclass
-- =============================================================================
-- EER: USER is specialized (disjoint, total) into DRIVER, OPERATOR and ADMIN,
-- mapped to one users table with a `role` discriminator (docs/ER_DIAGRAM.md).
-- The OPERATES relationship belongs to the OPERATOR subclass only. With a
-- single table, the foreign key alone cannot say that, so this trigger does.
-- Admins are allowed too: they run the network and may take over a station.
-- =============================================================================

DROP TRIGGER IF EXISTS trg_stations_operator_role_before_insert;
DROP TRIGGER IF EXISTS trg_stations_operator_role_before_update;

DELIMITER $$

CREATE TRIGGER trg_stations_operator_role_before_insert
BEFORE INSERT ON stations
FOR EACH ROW
BEGIN
    -- Unknown user: leave it to fk_stations_operator to reject with its own error.
    IF (SELECT role FROM users WHERE user_id = NEW.operator_id) NOT IN ('operator', 'admin') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'stations.operator_id must be a user with role operator or admin';
    END IF;
END$$

CREATE TRIGGER trg_stations_operator_role_before_update
BEFORE UPDATE ON stations
FOR EACH ROW
BEGIN
    IF NOT (NEW.operator_id <=> OLD.operator_id)
       AND (SELECT role FROM users WHERE user_id = NEW.operator_id) NOT IN ('operator', 'admin') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'stations.operator_id must be a user with role operator or admin';
    END IF;
END$$

DELIMITER ;
