#!/bin/bash
# =============================================================================
# MySQL node initialisation (mounted as /docker-entrypoint-initdb.d/00_init.sh)
# =============================================================================
# The official entrypoint only runs files directly inside docker-entrypoint-initdb.d
# and does not recurse, so this script walks /ev-sql (= ./database/mysql, read-only)
# and applies, each folder sorted by file name:
#
#   schema/  triggers/  procedures/  seeds/common/  seeds/$EV_CITY/
#
# optional/ is never applied automatically.
# Runs only when the data volume is empty; re-apply with `docker compose down -v`.
# =============================================================================

# The entrypoint SOURCES *.sh files that are not executable, which gives us its
# docker_process_sql helper. Bind mounts from Windows/macOS often show the file
# as executable, in which case it is EXECUTED instead; load the helpers ourselves.
if ! declare -F docker_process_sql > /dev/null; then
    # shellcheck source=/dev/null
    source /usr/local/bin/docker-entrypoint.sh
    docker_setup_env mysqld
fi

EV_SQL_ROOT=/ev-sql

case "${EV_CITY:-}" in
    bangalore|chennai|delhi) ;;
    *)
        echo "init.sh: EV_CITY must be bangalore, chennai or delhi (got '${EV_CITY:-}')" >&2
        exit 1
        ;;
esac

ev_apply_dir() {
    local dir="$EV_SQL_ROOT/$1" f
    if [ ! -d "$dir" ]; then
        echo "init.sh: $1/ not found, skipping"
        return 0
    fi
    # LC_ALL=C: byte order, so 01_ < 02_ < a < b regardless of the container locale.
    for f in $(find "$dir" -maxdepth 1 -type f -name '*.sql' | LC_ALL=C sort); do
        echo "init.sh: [$EV_CITY] applying ${f#"$EV_SQL_ROOT"/}"
        # The entrypoint's temporary init server runs with --default-time-zone=SYSTEM (UTC),
        # not our compose setting; force IST so CURDATE() in seeds and the event's stored
        # time zone match the running node.
        docker_process_sql --init-command="SET time_zone = '+05:30'" < "$f"
    done
}

ev_apply_dir schema
ev_apply_dir triggers
ev_apply_dir procedures
ev_apply_dir seeds/common
ev_apply_dir "seeds/$EV_CITY"

echo "init.sh: [$EV_CITY] database initialised"
