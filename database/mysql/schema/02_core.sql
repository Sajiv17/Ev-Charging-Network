-- =============================================================================
-- EV Charging Network - MySQL schema, part 2: users and city data
-- =============================================================================
-- REPLICATED (same rows, same IDs on every node; Bangalore issues the IDs):
--   users, vehicles
-- FRAGMENTED (each node stores only its own city's rows; IDs repeat across
-- nodes, so the API always addresses rows as (city, id)):
--   stations, charger_units, slots, bookings, payments, refunds, corridor_stations
-- =============================================================================

SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS corridor_stations;
DROP TABLE IF EXISTS refunds;
DROP TABLE IF EXISTS payments;
DROP TABLE IF EXISTS bookings;
DROP TABLE IF EXISTS slots;
DROP TABLE IF EXISTS charger_units;
DROP TABLE IF EXISTS stations;
DROP TABLE IF EXISTS vehicles;
DROP TABLE IF EXISTS users;
SET FOREIGN_KEY_CHECKS = 1;

-- =============================================================================
-- USERS AND VEHICLES (replicated)
-- =============================================================================

CREATE TABLE users (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    phone VARCHAR(20),
    role ENUM('driver', 'operator', 'admin') DEFAULT 'driver',
    -- Replicated, but only the copy on the home node (home_city_id) is authoritative.
    wallet_balance DECIMAL(10, 2) DEFAULT 0.00,
    home_city_id INT NOT NULL DEFAULT 1
        COMMENT 'City node that holds the authoritative wallet_balance',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_users_home_city FOREIGN KEY (home_city_id) REFERENCES cities(city_id),
    -- The real guarantee against overdraft; trg_users_wallet_guard only adds a readable message.
    CONSTRAINT chk_wallet_non_negative CHECK (wallet_balance >= 0),
    INDEX idx_role (role),
    INDEX idx_home_city (home_city_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE vehicles (
    vehicle_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    make VARCHAR(100) NOT NULL COMMENT 'e.g., Tata, MG, Hyundai',
    model VARCHAR(100) NOT NULL COMMENT 'e.g., Nexon EV, ZS EV',
    battery_capacity_kwh DECIMAL(5, 2) NOT NULL COMMENT 'Battery size in kWh',
    connector_type VARCHAR(10) NOT NULL,
    registration_number VARCHAR(20) UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- CASCADE is safe: bookings -> vehicles is RESTRICT, so a user with bookings cannot be removed.
    CONSTRAINT fk_vehicles_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    CONSTRAINT fk_vehicles_connector FOREIGN KEY (connector_type) REFERENCES connector_types(connector_type),
    CONSTRAINT chk_vehicle_battery CHECK (battery_capacity_kwh > 0),
    INDEX idx_user_id (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================================================
-- STATIONS AND CHARGERS (fragmented by city)
-- =============================================================================

CREATE TABLE stations (
    station_id INT AUTO_INCREMENT PRIMARY KEY,
    station_name VARCHAR(255) NOT NULL,
    city_id INT NOT NULL,
    address TEXT NOT NULL,
    latitude DECIMAL(10, 8),
    longitude DECIMAL(11, 8),
    operator_id INT NOT NULL COMMENT 'User who manages this station',
    is_operational BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_stations_city FOREIGN KEY (city_id) REFERENCES cities(city_id),
    CONSTRAINT fk_stations_operator FOREIGN KEY (operator_id) REFERENCES users(user_id),
    CONSTRAINT chk_station_lat CHECK (latitude BETWEEN -90 AND 90),
    CONSTRAINT chk_station_lon CHECK (longitude BETWEEN -180 AND 180),
    -- Also serves the city_id FK; a separate idx_city_id would be a left prefix of it.
    INDEX idx_station_city_status (city_id, is_operational),
    INDEX idx_operator_id (operator_id),
    INDEX idx_coordinates (latitude, longitude)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE charger_units (
    charger_id INT AUTO_INCREMENT PRIMARY KEY,
    station_id INT NOT NULL,
    charger_code VARCHAR(50) NOT NULL COMMENT 'Physical identifier (e.g., CHG-001)',
    -- Deliberate denormalization: derivable from connector_types.current_type, kept so
    -- the backend and pricing can filter on it without a join; trg_charger_type_* guard it.
    charger_type ENUM('AC', 'DC') NOT NULL,
    max_power_kw DECIMAL(5, 2) NOT NULL COMMENT 'Max charging power in kW',
    connector_type VARCHAR(10) NOT NULL,
    status ENUM('available', 'occupied', 'faulted', 'maintenance') DEFAULT 'available',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    -- CASCADE stops at bookings: bookings -> slots is RESTRICT, so a station with bookings stays.
    CONSTRAINT fk_chargers_station FOREIGN KEY (station_id) REFERENCES stations(station_id) ON DELETE CASCADE,
    CONSTRAINT fk_chargers_connector FOREIGN KEY (connector_type) REFERENCES connector_types(connector_type),
    CONSTRAINT chk_charger_power CHECK (max_power_kw > 0),
    -- Also serves the station_id FK, so no separate idx_station_id.
    UNIQUE KEY unique_charger (station_id, charger_code),
    INDEX idx_status (status),
    INDEX idx_connector_type (connector_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================================================
-- SLOTS AND BOOKINGS (fragmented by city)
-- =============================================================================

CREATE TABLE slots (
    slot_id INT AUTO_INCREMENT PRIMARY KEY,
    charger_id INT NOT NULL,
    slot_date DATE NOT NULL,
    slot_start_time TIME NOT NULL,
    slot_end_time TIME NOT NULL,
    -- Controlled redundancy: derivable from "no live booking on this slot". Kept because the
    -- 2PL booking transaction locks this row and flips the flag; triggers keep it consistent.
    is_available BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_slots_charger FOREIGN KEY (charger_id) REFERENCES charger_units(charger_id) ON DELETE CASCADE,
    -- Slots never cross midnight (06:00-22:00 grid), so end > start on the same date.
    CONSTRAINT chk_slot_times CHECK (slot_end_time > slot_start_time),
    -- Serves the charger_id FK, the overlap trigger and every "slots of charger X on day D" query.
    UNIQUE KEY unique_slot (charger_id, slot_date, slot_start_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE bookings (
    booking_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    slot_id INT NOT NULL,
    vehicle_id INT NOT NULL,
    booking_status ENUM('confirmed', 'active', 'completed', 'cancelled') DEFAULT 'confirmed',
    -- Prepaid estimate from pricing.prepaid_amount; final kWh settlement is backend phase 2.
    booking_amount DECIMAL(10, 2) NOT NULL,
    energy_consumed_kwh DECIMAL(8, 2) DEFAULT NULL COMMENT 'Actual energy consumed',
    session_start_time DATETIME DEFAULT NULL,
    session_end_time DATETIME DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    -- All RESTRICT: a booking is a financial record and must never disappear by cascade.
    -- user_service.delete_vehicle relies on the vehicle FK error to return 409 vehicle_in_use.
    CONSTRAINT fk_bookings_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE RESTRICT,
    CONSTRAINT fk_bookings_slot FOREIGN KEY (slot_id) REFERENCES slots(slot_id) ON DELETE RESTRICT,
    CONSTRAINT fk_bookings_vehicle FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id) ON DELETE RESTRICT,
    CONSTRAINT chk_booking_amount CHECK (booking_amount > 0),
    CONSTRAINT chk_booking_energy CHECK (energy_consumed_kwh >= 0),
    CONSTRAINT chk_booking_session CHECK (session_end_time >= session_start_time),
    -- No UNIQUE "one live booking per slot" here on purpose: the backend's unsafe-mode demo
    -- must be able to show a real double booking. See optional/double_booking_guard.sql.
    INDEX idx_slot_id (slot_id),
    INDEX idx_status (booking_status),
    INDEX idx_session_times (session_start_time, session_end_time),
    -- Also serves the user_id FK, so no separate idx_user_id.
    INDEX idx_booking_user_status (user_id, booking_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================================================
-- PAYMENTS AND REFUNDS (fragmented by city, stored next to the booking)
-- =============================================================================

CREATE TABLE payments (
    payment_id INT AUTO_INCREMENT PRIMARY KEY,
    booking_id INT NOT NULL,
    amount DECIMAL(10, 2) NOT NULL,
    payment_method ENUM('wallet', 'upi', 'card', 'netbanking') NOT NULL,
    payment_status ENUM('pending', 'completed', 'failed', 'refunded') DEFAULT 'pending',
    transaction_id VARCHAR(255) UNIQUE,
    payment_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- RESTRICT (was CASCADE): deleting a booking must never erase its payment trail.
    CONSTRAINT fk_payments_booking FOREIGN KEY (booking_id) REFERENCES bookings(booking_id) ON DELETE RESTRICT,
    CONSTRAINT chk_payment_amount CHECK (amount > 0),
    INDEX idx_booking_id (booking_id),
    INDEX idx_status (payment_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE refunds (
    refund_id INT AUTO_INCREMENT PRIMARY KEY,
    payment_id INT NOT NULL,
    refund_amount DECIMAL(10, 2) NOT NULL,
    refund_reason TEXT,
    -- queued = owed to a wallet on another node; completed = wallet already credited.
    refund_status ENUM('queued', 'processing', 'completed', 'failed') DEFAULT 'queued',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP NULL,
    CONSTRAINT fk_refunds_payment FOREIGN KEY (payment_id) REFERENCES payments(payment_id) ON DELETE RESTRICT,
    CONSTRAINT chk_refund_amount CHECK (refund_amount > 0),
    INDEX idx_payment_id (payment_id),
    INDEX idx_status (refund_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================================================
-- CORRIDORS (fragmented: each node lists only its own stations on a corridor)
-- =============================================================================

CREATE TABLE corridor_stations (
    corridor_id INT NOT NULL,
    station_id INT NOT NULL,
    km_marker DECIMAL(6, 1) NOT NULL COMMENT 'Distance from the corridor origin, along the route',
    PRIMARY KEY (corridor_id, station_id),
    CONSTRAINT fk_cs_corridor FOREIGN KEY (corridor_id) REFERENCES corridors(corridor_id) ON DELETE CASCADE,
    CONSTRAINT fk_cs_station FOREIGN KEY (station_id) REFERENCES stations(station_id) ON DELETE CASCADE,
    CONSTRAINT chk_cs_km CHECK (km_marker >= 0),
    -- Corridor query: WHERE corridor_id = ? ORDER BY km_marker.
    INDEX idx_cs_km (corridor_id, km_marker),
    INDEX idx_cs_station (station_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
