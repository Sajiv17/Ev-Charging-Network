#!/usr/bin/env bash
# =============================================================================
# Crash-recovery demo on the Bangalore node (database side of the recovery demo)
#
#   scripts/db/crash_recovery_demo.sh
#
# 1. Shows the durability settings (redo log = InnoDB's write-ahead log, binlog).
# 2. Commits one booking (must survive the crash).
# 3. Leaves a second booking UNCOMMITTED (wallet debited, booking + payment
#    inserted, slot closed), then kills mysqld with SIGKILL, like a power cut.
# 4. Restarts the node: InnoDB replays the redo log and rolls the uncommitted
#    transaction back from the undo log. Prints the recovery lines from the
#    error log and checks the data.
# 5. Repeats with an XA transaction left PREPARED (phase 1 of two-phase commit
#    done, phase 2 not): it survives the crash as "in doubt", XA RECOVER lists
#    it, and the coordinator's decision (here: ROLLBACK) finishes it.
#
# Needs the compose MySQL nodes running and seeded. Restarts ev-mysql-bangalore
# twice; the backend sees that node as down for a few seconds each time.
# =============================================================================

set -u
export MSYS_NO_PATHCONV=1

NODE=ev-mysql-bangalore
DB=ev_bangalore
ROOT_PW="${MYSQL_ROOT_PASSWORD:-evcharge_root_2024}"
APP_USER="${MYSQL_USER:-ev_user}"
APP_PW="${MYSQL_PASSWORD:-evcharge_pass_2024}"
USER_ID=5      # driver.bangalore@demo.ev (home node Bangalore)
VEHICLE_ID=1   # Tata Nexon EV, CCS2
CHARGER_ID=1   # Koramangala EV Hub CHG-01, 60 kW CCS2

q() { docker exec -i "$NODE" mysql -uroot -p"$ROOT_PW" -N -B "$DB" "$@" 2>&1 | grep -v "Using a password"; }
qt() { docker exec -i "$NODE" mysql -uroot -p"$ROOT_PW" -t "$DB" "$@" 2>&1 | grep -v "Using a password"; }

wait_ready() {
    for _ in $(seq 1 90); do
        docker exec "$NODE" mysqladmin ping -h127.0.0.1 --protocol=TCP -uroot -p"$ROOT_PW" > /dev/null 2>&1 && return
        sleep 1
    done
    echo "node did not come back"; exit 1
}

crash_and_restart() {
    local since
    since=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    # InnoDB's background thread flushes the redo log about once a second; give it time so the
    # uncommitted changes are on disk and recovery has something to undo.
    sleep 3
    echo ">>> docker kill -s KILL $NODE   (no clean shutdown, like a power cut)"
    docker kill -s KILL "$NODE" > /dev/null
    sleep 2
    echo ">>> docker start $NODE"
    docker start "$NODE" > /dev/null
    wait_ready
    echo ">>> recovery lines from the MySQL error log:"
    docker logs --since "$since" "$NODE" 2>&1 \
        | grep -iE "crash recovery|shut ?down normally|rolling back trx|rollback of trx|prepared state|prepared XA" \
        | sed 's/^/    /' | head -20
}

echo "== 1. Durability settings"
qt -e "SELECT @@innodb_flush_log_at_trx_commit AS flush_log_at_commit, @@sync_binlog AS sync_binlog,
              @@log_bin AS binlog_on, @@binlog_format AS binlog_format,
              @@innodb_doublewrite AS doublewrite, @@innodb_redo_log_capacity DIV 1048576 AS redo_log_mb;"
echo "flush_log_at_commit=1 + sync_binlog=1: a COMMIT returns only after its redo (and binlog) is on disk."

# InnoDB logs its recovery steps at Note level (hidden by default); show them for the demo
# and put the default back on exit. PERSIST so the setting survives the crash restart.
q -e "SET PERSIST log_error_verbosity = 3" > /dev/null
trap 'q -e "RESET PERSIST log_error_verbosity; SET GLOBAL log_error_verbosity = 2" > /dev/null' EXIT

read -r S1 S2 S3 <<< "$(q -e "SELECT slot_id FROM slots WHERE charger_id = $CHARGER_ID AND is_available
                                 AND slot_date = CURDATE() + INTERVAL 3 DAY ORDER BY slot_start_time LIMIT 3" | tr '\n' ' ')"
if [ -z "${S3:-}" ]; then echo "no free slots left on charger $CHARGER_ID in 3 days; reseed the node"; exit 1; fi
W0=$(q -e "SELECT wallet_balance FROM users WHERE user_id = $USER_ID")
echo
echo "== 2. Committed booking on slot $S1 (wallet before: Rs $W0)"
q -e "CALL sp_create_booking($USER_ID, $S1, $VEHICLE_ID, @b, @a); SELECT CONCAT('committed booking ', @b, ', Rs ', @a);"
W1=$(q -e "SELECT wallet_balance FROM users WHERE user_id = $USER_ID")

echo
echo "== 3. Uncommitted booking on slot $S2, then crash"
docker exec -i "$NODE" mysql -uroot -p"$ROOT_PW" "$DB" > /dev/null 2>&1 <<SQL &
START TRANSACTION;
UPDATE users SET wallet_balance = wallet_balance - 880.50 WHERE user_id = $USER_ID;
INSERT INTO bookings (user_id, slot_id, vehicle_id, booking_status, booking_amount) VALUES ($USER_ID, $S2, $VEHICLE_ID, 'confirmed', 880.50);
INSERT INTO payments (booking_id, amount, payment_method, payment_status, transaction_id)
VALUES (LAST_INSERT_ID(), 880.50, 'wallet', 'completed', 'CRASH-DEMO-$S2');
UPDATE slots SET is_available = FALSE WHERE slot_id = $S2;
DO SLEEP(600);
SQL
sleep 2
echo "open transaction just before the crash (information_schema.innodb_trx):"
qt -e "SELECT trx_id, trx_state, trx_rows_modified, trx_started FROM information_schema.innodb_trx;"
crash_and_restart

echo ">>> after recovery:"
report=$(q -e "
  SELECT CONCAT('committed booking on slot $S1 survived:   ', IF(COUNT(*) = 1, 'YES', 'NO'))
    FROM bookings WHERE slot_id = $S1 AND booking_status = 'confirmed';
  SELECT CONCAT('uncommitted booking on slot $S2 is gone:  ', IF(COUNT(*) = 0, 'YES', 'NO'))
    FROM bookings WHERE slot_id = $S2;
  SELECT CONCAT('its payment is gone:                     ', IF(COUNT(*) = 0, 'YES', 'NO'))
    FROM payments WHERE transaction_id = 'CRASH-DEMO-$S2';
  SELECT CONCAT('slot $S2 is open again:                   ', IF(is_available, 'YES', 'NO'))
    FROM slots WHERE slot_id = $S2;
  SELECT CONCAT('wallet = after the committed booking:    ', IF(wallet_balance = $W1, 'YES', 'NO'),
                ' (Rs ', wallet_balance, ')') FROM users WHERE user_id = $USER_ID;")
echo "$report" | sed 's/^/    /'
part1_ok=1; echo "$report" | grep -q "NO" && part1_ok=0

echo
echo "== 4. XA transaction left PREPARED (two-phase commit, phase 1 only), then crash"
docker exec -i "$NODE" mysql -uroot -p"$ROOT_PW" "$DB" 2>&1 <<SQL | grep -v "Using a password"
XA START 'crash-demo-$S3';
INSERT INTO bookings (user_id, slot_id, vehicle_id, booking_status, booking_amount) VALUES ($USER_ID, $S3, $VEHICLE_ID, 'confirmed', 880.50);
XA END 'crash-demo-$S3';
XA PREPARE 'crash-demo-$S3';
SQL
echo "prepared; the coordinator has not said COMMIT or ROLLBACK yet."
crash_and_restart
echo ">>> XA RECOVER as $APP_USER (the backend's user; needs XA_RECOVER_ADMIN):"
docker exec "$NODE" mysql -u"$APP_USER" -p"$APP_PW" -t -e "XA RECOVER" 2>&1 | grep -v "Using a password" | sed 's/^/    /'
echo ">>> coordinator decides ROLLBACK:"
docker exec "$NODE" mysql -u"$APP_USER" -p"$APP_PW" "$DB" -e "XA ROLLBACK 'crash-demo-$S3'" 2>&1 | grep -v "Using a password"
xa=$(q -e "SELECT COUNT(*) FROM bookings WHERE slot_id = $S3")
left=$(docker exec "$NODE" mysql -uroot -p"$ROOT_PW" -N -e "XA RECOVER" 2>/dev/null | wc -l)
echo "    in-doubt booking on slot $S3 gone: $([ "$xa" = 0 ] && echo YES || echo NO); prepared transactions left: $left"

echo
if [ "$part1_ok" = 1 ] && [ "$xa" = 0 ] && [ "$left" = 0 ]; then
    echo "RESULT: committed work survived, uncommitted work was undone, the in-doubt XA transaction was resolved."
else
    echo "RESULT: unexpected state, see above"; exit 1
fi
