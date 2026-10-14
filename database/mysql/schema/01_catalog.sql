-- =============================================================================
-- EV Charging Network - MySQL schema, part 1: global catalog
-- Database Systems Project (BACSE202)
-- =============================================================================
-- Applied to ALL three city nodes (Bangalore, Chennai, Delhi) by init.sh.
-- Every table in this file is REPLICATED: identical rows with identical IDs on
-- every node, loaded from seeds/common/.
--   cities, connector_types, pricing_plans, corridors
-- Fragmented tables (one city's rows per node) live in 02_core.sql.
-- =============================================================================

-- The entrypoint creates the database with the server default (utf8mb4_0900_ai_ci).
-- Trigger/procedure variables inherit the DATABASE collation, so align it with the
-- tables; otherwise comparing a variable with a column fails with "Illegal mix of collations".
ALTER DATABASE CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- FK checks off so the drops work in any order, even with 02_core tables present.
SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS corridors;
DROP TABLE IF EXISTS pricing_plans;
DROP TABLE IF EXISTS connector_types;
DROP TABLE IF EXISTS cities;
SET FOREIGN_KEY_CHECKS = 1;

-- -----------------------------------------------------------------------------
-- cities: one row per node. city_id must match backend/app/core/cities.py
-- (Bangalore=1, Chennai=2, Delhi=3), so the seed inserts explicit IDs.
-- -----------------------------------------------------------------------------
CREATE TABLE cities (
    city_id INT AUTO_INCREMENT PRIMARY KEY,
    city_name VARCHAR(100) NOT NULL UNIQUE,
    state VARCHAR(100) NOT NULL,
    country VARCHAR(100) DEFAULT 'India',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------------------------------
-- connector_types: catalog of plug standards. Removes the transitive dependency
-- connector_type -> current_type from charger_units (see docs/NORMALIZATION.md).
-- VARCHAR key instead of ENUM so a new standard is one INSERT, not three ALTERs.
-- -----------------------------------------------------------------------------
CREATE TABLE connector_types (
    connector_type VARCHAR(10) PRIMARY KEY,
    current_type ENUM('AC', 'DC') NOT NULL COMMENT 'AC or DC charging, fixed by the plug standard',
    description VARCHAR(255) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------------------------------
-- pricing_plans: one plan per city x AC/DC x validity period.
-- charger_type here is the AC/DC current type (pricing.get_plan filters on it).
-- -----------------------------------------------------------------------------
CREATE TABLE pricing_plans (
    plan_id INT AUTO_INCREMENT PRIMARY KEY,
    city_id INT NOT NULL,
    charger_type ENUM('AC', 'DC') NOT NULL,
    rate_per_kwh DECIMAL(6, 2) NOT NULL COMMENT 'Price per kWh in INR',
    booking_fee DECIMAL(6, 2) DEFAULT 0.00 COMMENT 'Fixed booking fee',
    effective_from DATE NOT NULL,
    effective_to DATE DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- RESTRICT: removing a city must not silently drop its price history.
    CONSTRAINT fk_pricing_city FOREIGN KEY (city_id) REFERENCES cities(city_id) ON DELETE RESTRICT,
    CONSTRAINT chk_pricing_rate CHECK (rate_per_kwh > 0),
    CONSTRAINT chk_pricing_fee CHECK (booking_fee >= 0),
    CONSTRAINT chk_pricing_period CHECK (effective_to IS NULL OR effective_to >= effective_from),
    -- Candidate key (one plan per city, type and start date), and it matches pricing.get_plan:
    -- equality on (city, type), then ORDER BY effective_from DESC reads the index backwards
    -- instead of sorting (see docs/INDEXES.md).
    UNIQUE KEY uq_plan_period (city_id, charger_type, effective_from)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------------------------------
-- corridors: named highway routes (catalog). Which stations lie on a corridor is
-- fragmented data, kept per node in corridor_stations (02_core.sql).
-- -----------------------------------------------------------------------------
CREATE TABLE corridors (
    corridor_id INT AUTO_INCREMENT PRIMARY KEY,
    corridor_name VARCHAR(150) NOT NULL UNIQUE,
    highway VARCHAR(50) NOT NULL COMMENT 'e.g. NH-275',
    origin_city_id INT NOT NULL COMMENT 'km_marker 0 is at this city',
    destination VARCHAR(100) NOT NULL COMMENT 'Free text: the far end need not be a node city',
    length_km DECIMAL(6, 1) NOT NULL,
    CONSTRAINT fk_corridor_origin FOREIGN KEY (origin_city_id) REFERENCES cities(city_id),
    CONSTRAINT chk_corridor_length CHECK (length_km > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
