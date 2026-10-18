#!/usr/bin/env bash
# =============================================================================
# Database tests for the three MySQL city nodes.
#
#   scripts/db/run_db_tests.sh           # run against the running nodes
#   scripts/db/run_db_tests.sh --fresh   # first recreate the 3 MySQL nodes from
#                                        # empty volumes (DELETES their data)
#
# The checks assume freshly seeded nodes (run with --fresh, or right after
# `docker compose down -v && docker compose up -d`). They leave test rows behind
# (a "TEST" station on the Bangalore node, a few bookings), so re-run with --fresh.
# Prints PASS/FAIL per check; exit code 1 if anything failed.
# Works from Linux, macOS and Git Bash on Windows (needs docker on PATH).
# =============================================================================

set -u
export MSYS_NO_PATHCONV=1  # Git Bash: do not rewrite /ev-sql/... into C:/... paths

ROOT_PW="${MYSQL_ROOT_PASSWORD:-evcharge_root_2024}"
CITIES=(bangalore chennai delhi)
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PASSES=0
FAILS=0

pass() { echo "PASS  $1"; PASSES=$((PASSES + 1)); }
fail() { echo "FAIL  $1${2:+   -> $2}"; FAILS=$((FAILS + 1)); }

# sql <city> [mysql args...]: run as root on that node's database, tab-separated, no headers.
sql() {
    local city=$1; shift
    docker exec -i "ev-mysql-$city" mysql -uroot -p"$ROOT_PW" -N -B "ev_$city" "$@" 2>&1 | grep -v "Using a password"
}

# Reads "name<TAB>PASS|FAIL<TAB>detail" rows produced by the SQL checks.
report_rows() {
    local name res detail
    while IFS=$'\t' read -r name res detail; do
        [ -z "$name" ] && continue
        if [ "$res" = "PASS" ]; then pass "$name"; else fail "$name" "$res $detail"; fi
    done
}

# Keep only check rows (and errors) from output that also contains procedure result sets.
checks_only() { awk -F'\t' '$2 == "PASS" || $2 == "FAIL" || /ERROR/'; }

# expect_error <name> <city> <sql> <grep pattern>: the SQL must fail with a matching message.
expect_error() {
    local name=$1 city=$2 stmt=$3 pattern=$4 out
    out=$(sql "$city" -e "$stmt")
    if echo "$out" | grep -q "$pattern"; then pass "$name"; else fail "$name" "${out:-no error raised}"; fi
}

wait_ready() {
    local c i
    for c in "${CITIES[@]}"; do
        for i in $(seq 1 120); do
            # TCP ping only answers once the entrypoint's init (socket-only server) has finished.
            docker exec "ev-mysql-$c" mysqladmin ping -h127.0.0.1 --protocol=TCP -uroot -p"$ROOT_PW" \
                > /dev/null 2>&1 && break
            if [ "$(docker inspect -f '{{.State.Running}}' "ev-mysql-$c" 2>/dev/null)" != "true" ]; then
                echo "ev-mysql-$c stopped during init:"; docker logs --tail 30 "ev-mysql-$c"; exit 1
            fi
            sleep 2
        done
    done
}

if [ "${1:-}" = "--fresh" ]; then
    echo "Recreating the MySQL nodes from empty volumes..."
    for c in "${CITIES[@]}"; do
        vol=$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/var/lib/mysql"}}{{.Name}}{{end}}{{end}}' \
              "ev-mysql-$c" 2>/dev/null)
        docker rm -f "ev-mysql-$c" > /dev/null 2>&1
        [ -n "$vol" ] && docker volume rm "$vol" > /dev/null
    done
    (cd "$REPO_ROOT" && docker compose up -d mysql-bangalore mysql-chennai mysql-delhi > /dev/null 2>&1)
fi
wait_ready

echo "== Nodes and schema"

for c in "${CITIES[@]}"; do
    tz=$(sql "$c" -e "SELECT @@global.time_zone")
    [ "$tz" = "+05:30" ] && pass "$c: server time zone is +05:30" || fail "$c: server time zone is +05:30" "$tz"
done

dump_schema() {
    docker exec "ev-mysql-$1" mysqldump -uroot -p"$ROOT_PW" --no-data --skip-comments --routines --triggers \
        --events --skip-dump-date "ev_$1" 2>/dev/null | sed -E 's/ AUTO_INCREMENT=[0-9]+//; s/`ev_[a-z]+`//g'
}
ref=$(dump_schema bangalore | md5sum)
for c in chennai delhi; do
    [ "$(dump_schema $c | md5sum)" = "$ref" ] && pass "schema on $c identical to bangalore" \
        || fail "schema on $c identical to bangalore"
done

echo "== Fragmentation and replication"

for i in 0 1 2; do
    c=${CITIES[$i]}; id=$((i + 1))
    report_rows <<< "$(sql "$c" -e "
        SELECT '$c: only its own city''s stations',
               IF(COUNT(*) > 0 AND SUM(city_id <> $id) = 0, 'PASS', 'FAIL'),
               CONCAT(COUNT(*), ' stations, ', SUM(city_id <> $id), ' foreign') FROM stations;
        SELECT '$c: every booking is on a local station',
               IF(SUM(s.city_id <> $id) = 0, 'PASS', 'FAIL'), CONCAT(COUNT(*), ' bookings')
          FROM bookings b JOIN slots sl ON sl.slot_id = b.slot_id
          JOIN charger_units c ON c.charger_id = sl.charger_id JOIN stations s ON s.station_id = c.station_id;
        SELECT '$c: no slot is available while it has a live booking',
               IF(COUNT(*) = 0, 'PASS', 'FAIL'), CONCAT(COUNT(*), ' inconsistent slots')
          FROM slots sl
         WHERE sl.is_available = TRUE
           AND EXISTS (SELECT 1 FROM bookings b WHERE b.slot_id = sl.slot_id
                        AND b.booking_status IN ('confirmed', 'active'));")"
done

fingerprint() {
    sql "$1" -e "
        SELECT MD5(CONCAT_WS('|',
          (SELECT GROUP_CONCAT(user_id, email, home_city_id, role ORDER BY user_id) FROM users),
          (SELECT GROUP_CONCAT(vehicle_id, user_id, registration_number, connector_type ORDER BY vehicle_id) FROM vehicles),
          (SELECT GROUP_CONCAT(city_id, city_name ORDER BY city_id) FROM cities),
          (SELECT GROUP_CONCAT(connector_type, current_type ORDER BY connector_type) FROM connector_types),
          (SELECT GROUP_CONCAT(plan_id, city_id, charger_type, rate_per_kwh, booking_fee ORDER BY plan_id) FROM pricing_plans),
          (SELECT GROUP_CONCAT(corridor_id, corridor_name ORDER BY corridor_id) FROM corridors)))"
}
ref=$(fingerprint bangalore)
for c in chennai delhi; do
    [ "$(fingerprint $c)" = "$ref" ] \
        && pass "replicated tables (users, vehicles, catalog) identical with same IDs on $c" \
        || fail "replicated tables (users, vehicles, catalog) identical with same IDs on $c"
done

echo "== Constraints and triggers"

expect_error "charger_type/connector mismatch rejected (AC + CCS2)" bangalore \
    "START TRANSACTION;
     INSERT INTO charger_units (station_id, charger_code, charger_type, max_power_kw, connector_type)
     VALUES (1, 'TST-BAD', 'AC', 50, 'CCS2'); ROLLBACK;" \
    "does not match connector_type"

expect_error "charger_type/connector mismatch rejected on UPDATE (Type2 -> DC)" bangalore \
    "START TRANSACTION; UPDATE charger_units SET charger_type = 'DC' WHERE connector_type = 'Type2' LIMIT 1; ROLLBACK;" \
    "does not match connector_type"

expect_error "overlapping slot rejected (10:30-11:30 over 10:00-11:00)" bangalore \
    "START TRANSACTION;
     INSERT INTO slots (charger_id, slot_date, slot_start_time, slot_end_time)
     VALUES (1, CURDATE() + INTERVAL 1 DAY, '10:30:00', '11:30:00'); ROLLBACK;" \
    "overlaps an existing slot"

report_rows <<< "$(sql bangalore -e "
    START TRANSACTION;
    INSERT INTO slots (charger_id, slot_date, slot_start_time, slot_end_time)
    VALUES (1, '2031-06-01', '06:00:00', '07:00:00'), (1, '2031-06-01', '07:00:00', '08:00:00');
    SELECT 'back-to-back slots accepted (demo_service.create_fresh_slot pattern)',
           IF(COUNT(*) = 2, 'PASS', 'FAIL'), COUNT(*) FROM slots WHERE charger_id = 1 AND slot_date = '2031-06-01';
    ROLLBACK;")"

expect_error "negative wallet rejected with readable message (trigger)" bangalore \
    "START TRANSACTION; UPDATE users SET wallet_balance = -1 WHERE user_id = 5; ROLLBACK;" \
    "Insufficient wallet balance: user 5"

expect_error "negative wallet rejected by CHECK on insert (no trigger involved)" bangalore \
    "START TRANSACTION;
     INSERT INTO users (email, password_hash, full_name, wallet_balance, home_city_id)
     VALUES ('neg@test.ev', 'x', 'Neg', -10, 1); ROLLBACK;" \
    "chk_wallet_non_negative"

expect_error "deleting a booking with payments is blocked" bangalore \
    "START TRANSACTION; DELETE FROM bookings WHERE booking_id = 1; ROLLBACK;" \
    "foreign key constraint fails"

expect_error "deleting a vehicle with bookings is blocked (backend's 409 vehicle_in_use)" bangalore \
    "START TRANSACTION;
     DELETE FROM vehicles WHERE vehicle_id = (SELECT vehicle_id FROM bookings ORDER BY booking_id LIMIT 1);
     ROLLBACK;" \
    "foreign key constraint fails"

expect_error "deleting a station with bookings is blocked (cascade stops at bookings)" bangalore \
    "START TRANSACTION; DELETE FROM stations WHERE station_id = 1; ROLLBACK;" \
    "foreign key constraint fails"

expect_error "EER: a driver cannot operate a station (insert)" bangalore \
    "START TRANSACTION;
     INSERT INTO stations (station_name, city_id, address, operator_id) VALUES ('TEST bad op', 1, 'x', 5);
     ROLLBACK;" \
    "must be a user with role operator or admin"

expect_error "EER: a station cannot be handed to a driver (update)" bangalore \
    "START TRANSACTION; UPDATE stations SET operator_id = 5 WHERE station_id = 1; ROLLBACK;" \
    "must be a user with role operator or admin"

out=$(docker exec ev-mysql-bangalore mysql -uev_user -p"${MYSQL_PASSWORD:-evcharge_pass_2024}" -e "XA RECOVER" 2>&1 \
      | grep -v "Using a password")
echo "$out" | grep -q "ERROR" && fail "ev_user may run XA RECOVER (XA_RECOVER_ADMIN granted)" "$out" \
    || pass "ev_user may run XA RECOVER (XA_RECOVER_ADMIN granted)"

echo "== Stored procedures"

# A fresh future slot on Koramangala CHG-01 (60 kW CCS2), booked by driver.bangalore (user 5,
# vehicle 1: Nexon EV 40.5 kWh). Expected price: 30 + 21 x min(60 x 1 h, 40.5) = 880.50.
report_rows <<< "$(sql bangalore -e "
    SET @slot = (SELECT slot_id FROM slots WHERE charger_id = 1
                  AND slot_date = CURDATE() + INTERVAL 2 DAY AND slot_start_time = '09:00:00');
    SET @bal = (SELECT wallet_balance FROM users WHERE user_id = 5);
    CALL sp_create_booking(5, @slot, 1, @booking, @amount);
    SELECT 'sp_create_booking succeeds on a free slot',
           IF(@booking IS NOT NULL AND @amount = 880.50
              AND (SELECT wallet_balance FROM users WHERE user_id = 5) = @bal - 880.50
              AND (SELECT is_available FROM slots WHERE slot_id = @slot) = FALSE
              AND (SELECT payment_status FROM payments WHERE booking_id = @booking) = 'completed',
              'PASS', 'FAIL'),
           CONCAT('booking ', IFNULL(@booking, 'NULL'), ', amount ', IFNULL(@amount, 'NULL'));")"

expect_error "sp_create_booking fails on the same slot" bangalore \
    "SET @slot = (SELECT slot_id FROM slots WHERE charger_id = 1
                   AND slot_date = CURDATE() + INTERVAL 2 DAY AND slot_start_time = '09:00:00');
     CALL sp_create_booking(5, @slot, 1, @b, @a);" \
    "Slot already booked"

report_rows <<< "$(sql bangalore -e "
    SET @slot = (SELECT slot_id FROM slots WHERE charger_id = 1
                  AND slot_date = CURDATE() + INTERVAL 2 DAY AND slot_start_time = '09:00:00');
    SELECT 'failed sp_create_booking rolled back (one booking, one debit)',
           IF((SELECT COUNT(*) FROM bookings WHERE slot_id = @slot) = 1, 'PASS', 'FAIL'),
           (SELECT COUNT(*) FROM bookings WHERE slot_id = @slot);")"

expect_error "sp_create_booking refuses a remote-home user (wallet on another node)" bangalore \
    "SET @slot = (SELECT slot_id FROM slots WHERE charger_id = 1
                   AND slot_date = CURDATE() + INTERVAL 2 DAY AND slot_start_time = '10:00:00');
     CALL sp_create_booking(6, @slot, 2, @b, @a);" \
    "wallet is on another node"

report_rows <<< "$(sql bangalore -e "
    SELECT COUNT(*) INTO @before FROM slots;
    CALL sp_generate_slots(7);
    SELECT COUNT(*) INTO @mid FROM slots;
    CALL sp_generate_slots(7);
    SELECT 'sp_generate_slots is idempotent (second call adds nothing)',
           IF((SELECT COUNT(*) FROM slots) = @mid, 'PASS', 'FAIL'),
           CONCAT(@before, ' -> ', @mid, ' -> ', (SELECT COUNT(*) FROM slots));" | checks_only)"

load_rows=$(sql bangalore -e "CALL sp_get_station_load(1, CURDATE() + INTERVAL 1 DAY)" | wc -l)
[ "$load_rows" -eq 16 ] && pass "sp_get_station_load returns one row per hour (16)" \
    || fail "sp_get_station_load returns one row per hour (16)" "$load_rows rows"

echo "== Fault trigger (Bangalore node: user 5 home = Bangalore, user 6 home = Chennai)"

report_rows <<< "$(sql bangalore <<'SQL' | checks_only
SET @w5 = (SELECT wallet_balance FROM users WHERE user_id = 5);
SET @w6 = (SELECT wallet_balance FROM users WHERE user_id = 6);
INSERT INTO stations (station_name, city_id, address, latitude, longitude, operator_id)
VALUES ('TEST fault station', 1, 'test fixture', 12.90, 77.60, 2);
SET @st = LAST_INSERT_ID();
INSERT INTO charger_units (station_id, charger_code, charger_type, max_power_kw, connector_type)
VALUES (@st, 'TST-01', 'DC', 60, 'CCS2');
SET @ch = LAST_INSERT_ID();

-- A slot in progress (started 30 min ago) and future/past slots.
SET @a_start = NOW() - INTERVAL 30 MINUTE;
SET @a_date = DATE(@a_start), @a_t0 = TIME(@a_start), @a_t1 = ADDTIME(TIME(@a_start), '01:00:00');
INSERT INTO slots (charger_id, slot_date, slot_start_time, slot_end_time) VALUES (@ch, @a_date, @a_t0, @a_t1);
SET @s_active = LAST_INSERT_ID();
INSERT INTO slots (charger_id, slot_date, slot_start_time, slot_end_time) VALUES (@ch, CURDATE() + INTERVAL 1 DAY, '10:00', '11:00');
SET @s_remote = LAST_INSERT_ID();
INSERT INTO slots (charger_id, slot_date, slot_start_time, slot_end_time) VALUES (@ch, CURDATE() + INTERVAL 1 DAY, '11:00', '12:00');
SET @s_local = LAST_INSERT_ID();
INSERT INTO slots (charger_id, slot_date, slot_start_time, slot_end_time) VALUES (@ch, CURDATE() + INTERVAL 1 DAY, '12:00', '13:00');
SET @s_old = LAST_INSERT_ID();
INSERT INTO slots (charger_id, slot_date, slot_start_time, slot_end_time) VALUES (@ch, CURDATE() + INTERVAL 1 DAY, '13:00', '14:00');
SET @s_free = LAST_INSERT_ID();
INSERT INTO slots (charger_id, slot_date, slot_start_time, slot_end_time) VALUES (@ch, CURDATE() - INTERVAL 1 DAY, '10:00', '11:00');
SET @s_past = LAST_INSERT_ID();

-- active, local user: proportional refund, credited here
INSERT INTO bookings (user_id, slot_id, vehicle_id, booking_status, booking_amount, session_start_time)
VALUES (5, @s_active, 1, 'active', 600.00, @a_start);
SET @b_active = LAST_INSERT_ID();
INSERT INTO payments (booking_id, amount, payment_method, payment_status, transaction_id)
VALUES (@b_active, 600.00, 'wallet', 'completed', 'TEST-ACTIVE');
-- confirmed, remote user: full refund, queued
INSERT INTO bookings (user_id, slot_id, vehicle_id, booking_status, booking_amount) VALUES (6, @s_remote, 2, 'confirmed', 500.00);
SET @b_remote = LAST_INSERT_ID();
INSERT INTO payments (booking_id, amount, payment_method, payment_status, transaction_id)
VALUES (@b_remote, 500.00, 'wallet', 'completed', 'TEST-REMOTE');
-- confirmed, local user: full refund, credited here
INSERT INTO bookings (user_id, slot_id, vehicle_id, booking_status, booking_amount) VALUES (5, @s_local, 1, 'confirmed', 400.00);
SET @b_local = LAST_INSERT_ID();
INSERT INTO payments (booking_id, amount, payment_method, payment_status, transaction_id)
VALUES (@b_local, 400.00, 'wallet', 'completed', 'TEST-LOCAL');
-- cancelled earlier by the user (already refunded): must stay untouched
INSERT INTO bookings (user_id, slot_id, vehicle_id, booking_status, booking_amount) VALUES (5, @s_old, 1, 'cancelled', 300.00);
SET @b_old = LAST_INSERT_ID();
INSERT INTO payments (booking_id, amount, payment_method, payment_status, transaction_id)
VALUES (@b_old, 300.00, 'wallet', 'refunded', 'TEST-OLD');
SET @p_old = LAST_INSERT_ID();
INSERT INTO refunds (payment_id, refund_amount, refund_reason, refund_status, processed_at)
VALUES (@p_old, 300.00, 'Cancelled by user', 'completed', NOW() - INTERVAL 1 HOUR);
-- confirmed but the slot already ended (no-show): not affected
INSERT INTO bookings (user_id, slot_id, vehicle_id, booking_status, booking_amount) VALUES (5, @s_past, 1, 'confirmed', 200.00);
SET @b_past = LAST_INSERT_ID();
INSERT INTO payments (booking_id, amount, payment_method, payment_status, transaction_id)
VALUES (@b_past, 200.00, 'wallet', 'completed', 'TEST-PAST');

SET @w5_mid = (SELECT wallet_balance FROM users WHERE user_id = 5);
SET @t_fault = NOW();
UPDATE charger_units SET status = 'faulted' WHERE charger_id = @ch;
SET @expected = ROUND(600 * TIMESTAMPDIFF(SECOND, @t_fault, TIMESTAMP(@a_date, @a_t1)) / 3600, 2);
SET @r_active = (SELECT r.refund_amount FROM refunds r JOIN payments p ON p.payment_id = r.payment_id WHERE p.booking_id = @b_active);

SELECT 'fault: active booking gets proportional refund of unused time',
       IF(ABS(@r_active - @expected) <= 0.50 AND @r_active BETWEEN 250 AND 350, 'PASS', 'FAIL'),
       CONCAT('refund ', IFNULL(@r_active, 'NULL'), ', expected ~', @expected, ' of 600.00');
SELECT 'fault: confirmed booking gets full refund',
       IF((SELECT refund_amount FROM refunds r JOIN payments p ON p.payment_id = r.payment_id WHERE p.booking_id = @b_local) = 400.00
          AND (SELECT refund_amount FROM refunds r JOIN payments p ON p.payment_id = r.payment_id WHERE p.booking_id = @b_remote) = 500.00,
          'PASS', 'FAIL'), '';
SELECT 'fault: same-node user credited directly, refunds completed',
       IF(@w5_mid + @r_active + 400.00 = (SELECT wallet_balance FROM users WHERE user_id = 5)
          AND (SELECT COUNT(*) FROM refunds r JOIN payments p ON p.payment_id = r.payment_id
                WHERE p.booking_id IN (@b_active, @b_local) AND r.refund_status = 'completed' AND r.processed_at IS NOT NULL) = 2,
          'PASS', 'FAIL'),
       CONCAT('wallet +', (SELECT wallet_balance FROM users WHERE user_id = 5) - @w5_mid);
SELECT 'fault: remote user refund queued, local copy of wallet untouched',
       IF((SELECT CONCAT(r.refund_status, IFNULL(r.processed_at, '-')) FROM refunds r JOIN payments p ON p.payment_id = r.payment_id
            WHERE p.booking_id = @b_remote) = 'queued-'
          AND (SELECT wallet_balance FROM users WHERE user_id = 6) = @w6, 'PASS', 'FAIL'), '';
SELECT 'fault: bookings cancelled, payments refunded, session end recorded',
       IF((SELECT COUNT(*) FROM bookings WHERE booking_id IN (@b_active, @b_remote, @b_local) AND booking_status = 'cancelled') = 3
          AND (SELECT COUNT(*) FROM payments WHERE booking_id IN (@b_active, @b_remote, @b_local) AND payment_status = 'refunded') = 3
          AND (SELECT session_end_time FROM bookings WHERE booking_id = @b_active) IS NOT NULL, 'PASS', 'FAIL'), '';
SELECT 'fault: earlier cancelled booking untouched (still one refund)',
       IF((SELECT COUNT(*) FROM refunds WHERE payment_id = @p_old) = 1
          AND (SELECT payment_status FROM payments WHERE payment_id = @p_old) = 'refunded', 'PASS', 'FAIL'), '';
SELECT 'fault: confirmed booking whose slot ended is not touched',
       IF((SELECT booking_status FROM bookings WHERE booking_id = @b_past) = 'confirmed'
          AND (SELECT payment_status FROM payments WHERE booking_id = @b_past) = 'completed', 'PASS', 'FAIL'), '';
SELECT 'fault: slots of cancelled bookings stay closed while faulted',
       IF((SELECT SUM(is_available) FROM slots WHERE slot_id IN (@s_active, @s_remote, @s_local)) = 0, 'PASS', 'FAIL'), '';

UPDATE charger_units SET status = 'available' WHERE charger_id = @ch;
SELECT 'repair: free future slots re-open, the started slot does not',
       IF((SELECT is_available FROM slots WHERE slot_id = @s_remote) = 1
          AND (SELECT is_available FROM slots WHERE slot_id = @s_local) = 1
          AND (SELECT is_available FROM slots WHERE slot_id = @s_free) = 1
          AND (SELECT is_available FROM slots WHERE slot_id = @s_active) = 0, 'PASS', 'FAIL'), '';

SELECT 'alert: fault notifies the station operator with counts and totals',
       IF((SELECT COUNT(*) FROM operator_alerts
            WHERE charger_id = @ch AND alert_type = 'charger_faulted' AND operator_id = 2
              AND bookings_cancelled = 3 AND refunded_amount = @r_active + 400.00
              AND queued_refund_amount = 500.00 AND acknowledged_at IS NULL) = 1, 'PASS', 'FAIL'),
       (SELECT message FROM operator_alerts WHERE charger_id = @ch AND alert_type = 'charger_faulted');
SELECT 'alert: repair notifies the operator with slots re-opened',
       IF((SELECT slots_reopened FROM operator_alerts WHERE charger_id = @ch AND alert_type = 'charger_repaired') = 2,
          'PASS', 'FAIL'),
       (SELECT message FROM operator_alerts WHERE charger_id = @ch AND alert_type = 'charger_repaired');

-- sp_process_refund: the queued remote refund is handed back to the coordinator.
SET @r_remote = (SELECT r.refund_id FROM refunds r JOIN payments p ON p.payment_id = r.payment_id WHERE p.booking_id = @b_remote);
CALL sp_process_refund(@r_remote);
SELECT 'sp_process_refund leaves a remote refund queued',
       IF((SELECT refund_status FROM refunds WHERE refund_id = @r_remote) = 'queued', 'PASS', 'FAIL'), '';
SQL
)"

report_rows <<< "$(sql bangalore -e "
    SET @r = (SELECT r.refund_id FROM refunds r JOIN payments p ON p.payment_id = r.payment_id
               WHERE p.transaction_id = 'TEST-REMOTE');
    CALL sp_process_refund(@r);" | awk -F'\t' '{
        ok = ($2 == "remote" && $3 == 6 && $4 == 2 && $5 == "500.00");
        print "sp_process_refund returns (user_id, home_city_id, amount) for a remote refund\t" (ok ? "PASS" : "FAIL") "\t" $0 }')"

report_rows <<< "$(sql bangalore -e "
    SET @p = (SELECT payment_id FROM payments WHERE transaction_id = 'TEST-PAST');
    INSERT INTO refunds (payment_id, refund_amount, refund_reason, refund_status) VALUES (@p, 50.00, 'test', 'queued');
    SET @r = LAST_INSERT_ID();
    SET @w = (SELECT wallet_balance FROM users WHERE user_id = 5);
    CALL sp_process_refund(@r);
    SELECT 'sp_process_refund completes a local refund and credits the wallet',
           IF((SELECT refund_status FROM refunds WHERE refund_id = @r) = 'completed'
              AND (SELECT wallet_balance FROM users WHERE user_id = 5) = @w + 50.00, 'PASS', 'FAIL'), '';" \
    | checks_only)"

echo "== Schema re-run and optional double-booking guard (scratch database on the Bangalore node)"

scratch() { docker exec -i ev-mysql-bangalore mysql -uroot -p"$ROOT_PW" -N -B "$@" 2>&1 | grep -v "Using a password"; }
apply() { docker exec ev-mysql-bangalore sh -c "mysql -uroot -p'$ROOT_PW' ev_guard_test < /ev-sql/$1" 2>&1 | grep -v "Using a password"; }

scratch -e "DROP DATABASE IF EXISTS ev_guard_test; CREATE DATABASE ev_guard_test;"
out=$( { apply schema/01_catalog.sql; apply schema/02_core.sql; apply schema/01_catalog.sql; apply schema/02_core.sql; } )
[ -z "$out" ] && pass "schema files re-run cleanly on a database that already has the tables" \
    || fail "schema files re-run cleanly on a database that already has the tables" "$out"

apply seeds/common/01_catalog.sql
apply optional/double_booking_guard.sql
scratch ev_guard_test -e "
    INSERT INTO users (user_id, email, password_hash, full_name, home_city_id) VALUES (1, 'a@t', 'x', 'A', 1), (2, 'b@t', 'x', 'B', 1);
    INSERT INTO vehicles (vehicle_id, user_id, make, model, battery_capacity_kwh, connector_type)
    VALUES (1, 1, 'Tata', 'Nexon EV', 40.5, 'CCS2'), (2, 2, 'MG', 'ZS EV', 50.3, 'CCS2');
    INSERT INTO stations (station_id, station_name, city_id, address, operator_id) VALUES (1, 'S', 1, 'addr', 1);
    INSERT INTO charger_units (charger_id, station_id, charger_code, charger_type, max_power_kw, connector_type)
    VALUES (1, 1, 'C1', 'DC', 60, 'CCS2');
    INSERT INTO slots (slot_id, charger_id, slot_date, slot_start_time, slot_end_time) VALUES (1, 1, '2031-01-01', '10:00', '11:00');
    INSERT INTO bookings (user_id, slot_id, vehicle_id, booking_status, booking_amount) VALUES (1, 1, 1, 'cancelled', 100);
    INSERT INTO bookings (user_id, slot_id, vehicle_id, booking_status, booking_amount) VALUES (1, 1, 1, 'confirmed', 100);" > /dev/null
out=$(scratch ev_guard_test -e "INSERT INTO bookings (user_id, slot_id, vehicle_id, booking_status, booking_amount) VALUES (2, 1, 2, 'confirmed', 100);")
echo "$out" | grep -q "Duplicate entry '1' for key 'bookings.uq_bookings_live_slot_id'" \
    && pass "optional guard rejects a second live booking on the same slot" \
    || fail "optional guard rejects a second live booking on the same slot" "${out:-inserted}"
out=$(scratch ev_guard_test -e "
    UPDATE bookings SET booking_status = 'cancelled' WHERE booking_status = 'confirmed';
    INSERT INTO bookings (user_id, slot_id, vehicle_id, booking_status, booking_amount) VALUES (2, 1, 2, 'confirmed', 100);
    SELECT COUNT(*) FROM bookings WHERE slot_id = 1;")
[ "$out" = "3" ] && pass "optional guard still allows re-booking after a cancellation" \
    || fail "optional guard still allows re-booking after a cancellation" "$out"
scratch -e "DROP DATABASE ev_guard_test;"

echo
echo "$PASSES passed, $FAILS failed"
[ "$FAILS" -eq 0 ]
