-- =============================================================================
-- Backend additions to the schema (proposed by Person 2 - Backend)
-- =============================================================================
-- PERSON 1: please review. Merge these into 01_init_schema.sql if you prefer,
-- then delete this file. Docker runs files in this folder in alphabetical
-- order, so this runs right after 01_init_schema.sql on every city node.
--
-- Why these are needed:
--
-- 1. users.home_city_id
--    Users are replicated on all 3 nodes, so every user has 3 copies of
--    wallet_balance. Only ONE copy may be the real wallet, otherwise the
--    copies drift apart. The user's home city node holds the real wallet.
--    A Bangalore user booking in Chennai = debit on the Bangalore node +
--    booking on the Chennai node = a distributed transaction (2PC / XA).
--
-- 2. CHECK (wallet_balance >= 0)
--    Last line of defence: even if application code has a bug, MySQL
--    refuses to let a wallet go negative.
-- =============================================================================

ALTER TABLE users
    ADD COLUMN home_city_id INT NOT NULL DEFAULT 1
        COMMENT 'City node that holds the authoritative wallet_balance'
        AFTER wallet_balance,
    ADD CONSTRAINT fk_users_home_city FOREIGN KEY (home_city_id) REFERENCES cities(city_id),
    ADD CONSTRAINT chk_wallet_non_negative CHECK (wallet_balance >= 0),
    ADD INDEX idx_home_city (home_city_id);
