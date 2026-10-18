#!/usr/bin/env bash
# =============================================================================
# Deadlock demo on the Bangalore node: why every transaction locks slot -> wallet
#
#   scripts/db/deadlock_demo.sh
#
# Part 1, WRONG order: T1 locks a slot then the wallet; T2 locks the wallet then
#         the same slot. Each waits for the other: a cycle in the wait-for graph.
#         InnoDB detects it at once and rolls one back with error 1213.
# Part 2, RIGHT order (the backend's rule): both lock slot -> wallet. T2 simply
#         waits for T1 to finish; no cycle, no error.
#
# Only locking reads and ROLLBACK: nothing is changed in the database.
# =============================================================================

set -u
export MSYS_NO_PATHCONV=1

NODE=ev-mysql-bangalore
DB=ev_bangalore
ROOT_PW="${MYSQL_ROOT_PASSWORD:-evcharge_root_2024}"
USER_ID=5
OUT_DIR=$(mktemp -d)

q() { docker exec -i "$NODE" mysql -uroot -p"$ROOT_PW" -N -B "$DB" "$@" 2>&1 | grep -v "Using a password"; }

SLOT=$(q -e "SELECT MIN(slot_id) FROM slots WHERE charger_id = 1 AND slot_date = CURDATE() + INTERVAL 4 DAY")
# SYSDATE(6), not NOW(6): NOW() is fixed at statement start, SYSDATE() is read after the lock is granted.
LOCK_SLOT="SELECT CONCAT(TIME(SYSDATE(6)), '  locked slots[$SLOT]') FROM slots WHERE slot_id = $SLOT FOR UPDATE;"
LOCK_WALLET="SELECT CONCAT(TIME(SYSDATE(6)), '  locked users[$USER_ID].wallet') FROM users WHERE user_id = $USER_ID FOR UPDATE;"

session() {  # session <name> <sql>
    docker exec -i "$NODE" mysql -uroot -p"$ROOT_PW" -N -B "$DB" > "$OUT_DIR/$1" 2>&1 <<< "$2"
}

run_pair() {  # run_pair <T1 sql> <T2 sql>
    session T1 "$1" & local p1=$!
    sleep 0.5
    session T2 "$2" & local p2=$!
    wait $p1 $p2
    for t in T1 T2; do
        echo "  $t:"; grep -v "Using a password" "$OUT_DIR/$t" | sed 's/^/      /'
    done
}

echo "== Part 1: WRONG lock order (T1: slot -> wallet, T2: wallet -> slot)"
run_pair \
    "START TRANSACTION; $LOCK_SLOT DO SLEEP(2); $LOCK_WALLET ROLLBACK;" \
    "START TRANSACTION; $LOCK_WALLET DO SLEEP(2); $LOCK_SLOT ROLLBACK;"
dead=$(cat "$OUT_DIR/T1" "$OUT_DIR/T2" | grep -c "ERROR 1213")
echo
echo "  InnoDB's record of it (SHOW ENGINE INNODB STATUS, LATEST DETECTED DEADLOCK):"
docker exec "$NODE" mysql -uroot -p"$ROOT_PW" -e "SHOW ENGINE INNODB STATUS\G" 2>/dev/null \
    | sed -n '/LATEST DETECTED DEADLOCK/,/^TRANSACTIONS$/p' \
    | grep -E "TRANSACTION|WAITING FOR|HOLDS THE LOCK|index PRIMARY of table|WE ROLL BACK|mysql tables in use" \
    | sed 's/^/      /' | head -16

echo
echo "== Part 2: RIGHT lock order (both: slot -> wallet), as booking_service does"
run_pair \
    "START TRANSACTION; $LOCK_SLOT DO SLEEP(2); $LOCK_WALLET ROLLBACK;" \
    "START TRANSACTION; $LOCK_SLOT $LOCK_WALLET ROLLBACK;"
errors=$(cat "$OUT_DIR/T1" "$OUT_DIR/T2" | grep -c "ERROR")
rm -rf "$OUT_DIR"

echo
if [ "$dead" -eq 1 ] && [ "$errors" -eq 0 ]; then
    echo "RESULT: wrong order -> one transaction chosen as deadlock victim (1213);"
    echo "        right order -> T2 waited for T1's slot lock until T1 finished, then went on. No deadlock."
else
    echo "RESULT: unexpected (deadlocks in part 1: $dead, errors in part 2: $errors)"; exit 1
fi
