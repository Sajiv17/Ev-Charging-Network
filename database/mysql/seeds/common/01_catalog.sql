-- =============================================================================
-- Replicated catalog: identical rows and IDs on every node.
-- =============================================================================

-- Explicit IDs: backend/app/core/cities.py hard-codes Bangalore=1, Chennai=2, Delhi=3.
INSERT INTO cities (city_id, city_name, state, country) VALUES
(1, 'Bangalore', 'Karnataka', 'India'),
(2, 'Chennai', 'Tamil Nadu', 'India'),
(3, 'Delhi', 'Delhi', 'India');

INSERT INTO connector_types (connector_type, current_type, description) VALUES
('CCS2', 'DC', 'Combined Charging System (Combo 2): DC fast charging, the Indian standard for new cars'),
('CHAdeMO', 'DC', 'CHAdeMO: Japanese DC fast-charging standard (e.g. Nissan Leaf)'),
('Type2', 'AC', 'IEC 62196 Type 2 (Mennekes): AC charging, single or three phase');
