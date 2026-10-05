-- =============================================================================
-- EV Charging Network - MySQL Schema
-- Database Systems Project (BACSE202)
-- =============================================================================
-- This schema is applied to ALL three city nodes (Bangalore, Chennai, Delhi)
-- Each node stores only its own city's data (horizontal fragmentation)
-- Global catalog tables are replicated across all nodes
-- =============================================================================

-- Drop tables if they exist (for re-initialization)
DROP TABLE IF EXISTS payments;
DROP TABLE IF EXISTS bookings;
DROP TABLE IF EXISTS slots;
DROP TABLE IF EXISTS charger_units;
DROP TABLE IF EXISTS stations;
DROP TABLE IF EXISTS vehicles;
DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS pricing_plans;
DROP TABLE IF EXISTS cities;
DROP TABLE IF EXISTS refunds;

-- =============================================================================
-- GLOBAL CATALOG TABLES (Replicated across all nodes)
-- =============================================================================

CREATE TABLE cities (
    city_id INT AUTO_INCREMENT PRIMARY KEY,
    city_name VARCHAR(100) NOT NULL UNIQUE,
    state VARCHAR(100) NOT NULL,
    country VARCHAR(100) DEFAULT 'India',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_city_name (city_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE pricing_plans (
    plan_id INT AUTO_INCREMENT PRIMARY KEY,
    city_id INT NOT NULL,
    charger_type ENUM('AC', 'DC') NOT NULL,
    rate_per_kwh DECIMAL(6, 2) NOT NULL COMMENT 'Price per kWh in INR',
    booking_fee DECIMAL(6, 2) DEFAULT 0.00 COMMENT 'Fixed booking fee',
    effective_from DATE NOT NULL,
    effective_to DATE DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (city_id) REFERENCES cities(city_id) ON DELETE CASCADE,
    INDEX idx_city_charger_type (city_id, charger_type),
    INDEX idx_effective_dates (effective_from, effective_to)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================================================
-- USER TABLES (Replicated globally, but each node stores all users)
-- =============================================================================

CREATE TABLE users (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    phone VARCHAR(20),
    role ENUM('driver', 'operator', 'admin') DEFAULT 'driver',
    wallet_balance DECIMAL(10, 2) DEFAULT 0.00,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_email (email),
    INDEX idx_role (role)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE vehicles (
    vehicle_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    make VARCHAR(100) NOT NULL COMMENT 'e.g., Tata, MG, Hyundai',
    model VARCHAR(100) NOT NULL COMMENT 'e.g., Nexon EV, ZS EV',
    battery_capacity_kwh DECIMAL(5, 2) NOT NULL COMMENT 'Battery size in kWh',
    connector_type ENUM('CCS2', 'CHAdeMO', 'Type2') NOT NULL,
    registration_number VARCHAR(20) UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    INDEX idx_user_id (user_id),
    INDEX idx_connector_type (connector_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================================================
-- STATION TABLES (Fragmented by city - each node stores only its own stations)
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
    FOREIGN KEY (city_id) REFERENCES cities(city_id),
    FOREIGN KEY (operator_id) REFERENCES users(user_id),
    INDEX idx_city_id (city_id),
    INDEX idx_operator_id (operator_id),
    INDEX idx_coordinates (latitude, longitude)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE charger_units (
    charger_id INT AUTO_INCREMENT PRIMARY KEY,
    station_id INT NOT NULL,
    charger_code VARCHAR(50) NOT NULL COMMENT 'Physical identifier (e.g., CHG-001)',
    charger_type ENUM('AC', 'DC') NOT NULL,
    max_power_kw DECIMAL(5, 2) NOT NULL COMMENT 'Max charging power in kW',
    connector_type ENUM('CCS2', 'CHAdeMO', 'Type2') NOT NULL,
    status ENUM('available', 'occupied', 'faulted', 'maintenance') DEFAULT 'available',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (station_id) REFERENCES stations(station_id) ON DELETE CASCADE,
    UNIQUE KEY unique_charger (station_id, charger_code),
    INDEX idx_station_id (station_id),
    INDEX idx_status (status),
    INDEX idx_connector_type (connector_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================================================
-- BOOKING TABLES (Fragmented by city)
-- =============================================================================

CREATE TABLE slots (
    slot_id INT AUTO_INCREMENT PRIMARY KEY,
    charger_id INT NOT NULL,
    slot_date DATE NOT NULL,
    slot_start_time TIME NOT NULL,
    slot_end_time TIME NOT NULL,
    is_available BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (charger_id) REFERENCES charger_units(charger_id) ON DELETE CASCADE,
    UNIQUE KEY unique_slot (charger_id, slot_date, slot_start_time),
    INDEX idx_charger_date (charger_id, slot_date),
    INDEX idx_availability (is_available)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE bookings (
    booking_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    slot_id INT NOT NULL,
    vehicle_id INT NOT NULL,
    booking_status ENUM('confirmed', 'active', 'completed', 'cancelled') DEFAULT 'confirmed',
    booking_amount DECIMAL(10, 2) NOT NULL,
    energy_consumed_kwh DECIMAL(8, 2) DEFAULT NULL COMMENT 'Actual energy consumed',
    session_start_time DATETIME DEFAULT NULL,
    session_end_time DATETIME DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (slot_id) REFERENCES slots(slot_id),
    FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id),
    INDEX idx_user_id (user_id),
    INDEX idx_slot_id (slot_id),
    INDEX idx_status (booking_status),
    INDEX idx_session_times (session_start_time, session_end_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================================================
-- PAYMENT TABLES (Fragmented by city)
-- =============================================================================

CREATE TABLE payments (
    payment_id INT AUTO_INCREMENT PRIMARY KEY,
    booking_id INT NOT NULL,
    amount DECIMAL(10, 2) NOT NULL,
    payment_method ENUM('wallet', 'upi', 'card', 'netbanking') NOT NULL,
    payment_status ENUM('pending', 'completed', 'failed', 'refunded') DEFAULT 'pending',
    transaction_id VARCHAR(255) UNIQUE,
    payment_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (booking_id) REFERENCES bookings(booking_id) ON DELETE CASCADE,
    INDEX idx_booking_id (booking_id),
    INDEX idx_status (payment_status),
    INDEX idx_transaction_id (transaction_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE refunds (
    refund_id INT AUTO_INCREMENT PRIMARY KEY,
    payment_id INT NOT NULL,
    refund_amount DECIMAL(10, 2) NOT NULL,
    refund_reason TEXT,
    refund_status ENUM('queued', 'processing', 'completed', 'failed') DEFAULT 'queued',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP NULL,
    FOREIGN KEY (payment_id) REFERENCES payments(payment_id),
    INDEX idx_payment_id (payment_id),
    INDEX idx_status (refund_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================================================
-- INDEXES FOR QUERY OPTIMIZATION (Module 3)
-- =============================================================================

-- Composite index for fast slot availability lookup
CREATE INDEX idx_slot_availability ON slots(charger_id, slot_date, is_available);

-- Composite index for station search by city and status
CREATE INDEX idx_station_city_status ON stations(city_id, is_operational);

-- Composite index for booking queries
CREATE INDEX idx_booking_user_status ON bookings(user_id, booking_status);

-- =============================================================================
-- INITIAL DATA: Cities
-- =============================================================================

INSERT INTO cities (city_name, state, country) VALUES
('Bangalore', 'Karnataka', 'India'),
('Chennai', 'Tamil Nadu', 'India'),
('Delhi', 'Delhi', 'India');

-- =============================================================================
-- Note: Triggers and stored procedures are in separate files
-- See: database/mysql/triggers/ and database/mysql/procedures/
-- =============================================================================
