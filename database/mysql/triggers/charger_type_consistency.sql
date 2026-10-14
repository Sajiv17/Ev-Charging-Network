-- =============================================================================
-- charger_units.charger_type must agree with connector_types.current_type
-- =============================================================================
-- charger_type is a deliberate denormalization (connector_type -> current_type
-- is a transitive dependency, see docs/NORMALIZATION.md). It is kept because the
-- backend's queries and pricing_plans filter on it directly. These triggers make
-- the redundant copy impossible to get wrong: CCS2/CHAdeMO must be DC, Type2 AC.
-- =============================================================================

DROP TRIGGER IF EXISTS trg_charger_type_before_insert;
DROP TRIGGER IF EXISTS trg_charger_type_before_update;

DELIMITER $$

CREATE TRIGGER trg_charger_type_before_insert
BEFORE INSERT ON charger_units
FOR EACH ROW
BEGIN
    DECLARE v_current VARCHAR(2);
    SELECT current_type INTO v_current FROM connector_types WHERE connector_type = NEW.connector_type;
    -- Unknown connector: leave it to fk_chargers_connector to reject with its own error.
    IF v_current IS NOT NULL AND v_current <> NEW.charger_type THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'charger_type does not match connector_type (CCS2/CHAdeMO are DC, Type2 is AC)';
    END IF;
END$$

CREATE TRIGGER trg_charger_type_before_update
BEFORE UPDATE ON charger_units
FOR EACH ROW
BEGIN
    DECLARE v_current VARCHAR(2);
    -- Status flips (fault/repair) are the common update; skip the lookup for them.
    IF NOT (NEW.connector_type <=> OLD.connector_type AND NEW.charger_type <=> OLD.charger_type) THEN
        SELECT current_type INTO v_current FROM connector_types WHERE connector_type = NEW.connector_type;
        IF v_current IS NOT NULL AND v_current <> NEW.charger_type THEN
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'charger_type does not match connector_type (CCS2/CHAdeMO are DC, Type2 is AC)';
        END IF;
    END IF;
END$$

DELIMITER ;
