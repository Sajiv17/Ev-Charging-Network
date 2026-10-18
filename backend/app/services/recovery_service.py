"""
Background recovery: finishes what a crash left half-done.

1. In-doubt 2PC transactions (xa.recover_in_doubt)
   A branch that voted PREPARED keeps its locks until someone tells it
   COMMIT or ROLLBACK. If the coordinator (this backend) or a node crashed in
   between, recovery asks every node `XA RECOVER` and resolves each branch
   from the coordinator's decision log.

2. Queued refunds
   The charger-fault trigger (database/mysql/triggers/charger_fault_trigger.sql)
   can only credit a wallet that lives on its own node. For a user from
   another city it inserts the refund as 'queued'. Paying it means:
     station node : refund row  queued -> completed
     home node    : wallet      += amount
   two nodes again, so 2PC.

Runs once at startup and then every RECOVERY_INTERVAL_S seconds on a daemon
thread; also on demand via POST /api/admin/recover.
"""

import logging
import threading
import time

from app.core.cities import CITIES, city_key_of
from app.core.config import settings
from app.services import audit, xa

log = logging.getLogger("recovery")

_run_lock = threading.Lock()
_last_report: dict = {}


def settle_queued_refunds() -> dict:
    report = {"settled": [], "errors": [], "unreachable": []}
    for station_city in CITIES:
        try:
            raw = xa._checkout(station_city)
        except Exception:
            report["unreachable"].append(station_city)
            continue
        try:
            queued = xa.Q(raw.dbapi_connection).all(
                """
                SELECT r.refund_id, r.refund_amount, b.user_id, u.home_city_id
                FROM refunds r
                JOIN payments p ON p.payment_id = r.payment_id
                JOIN bookings b ON b.booking_id = p.booking_id
                JOIN users u    ON u.user_id = b.user_id
                WHERE r.refund_status = 'queued'
                ORDER BY r.refund_id
                """
            )
        finally:
            xa._release(raw)
        for r in queued:
            try:
                report["settled"].append(_settle_one(station_city, r))
            except Exception as exc:
                report["errors"].append(
                    {"city": station_city, "refund_id": r["refund_id"], "error": str(exc)[:200]}
                )
    return report


def _settle_one(station_city: str, r: dict) -> dict:
    home_city = city_key_of(r["home_city_id"])
    txn = audit.new_txn_id()
    with xa.transaction(station_city, home_city, "settle_refund", txn) as t:
        s = t.branch(station_city)
        row = s.q.one(
            "SELECT refund_status, refund_amount FROM refunds WHERE refund_id = :r FOR UPDATE",
            r=r["refund_id"],
        )
        if not row or row["refund_status"] != "queued":  # someone else settled it meanwhile
            return {"city": station_city, "refund_id": r["refund_id"], "skipped": True}
        s.q.exec(
            "UPDATE refunds SET refund_status = 'completed', processed_at = NOW() WHERE refund_id = :r",
            r=r["refund_id"],
        )
        h = t.branch(home_city)
        h.q.one("SELECT wallet_balance FROM users WHERE user_id = :u FOR UPDATE", u=r["user_id"])
        h.q.exec(
            "UPDATE users SET wallet_balance = wallet_balance + :a WHERE user_id = :u",
            a=row["refund_amount"],
            u=r["user_id"],
        )
        t.commit()
    audit.record(
        "REFUND_SETTLED",
        txn=txn,
        city=station_city,
        refund_id=r["refund_id"],
        wallet_node=home_city,
        user_id=r["user_id"],
        amount=float(row["refund_amount"]),
    )
    return {
        "city": station_city,
        "refund_id": r["refund_id"],
        "wallet_node": home_city,
        "user_id": r["user_id"],
        "amount": float(row["refund_amount"]),
    }


def run_recovery(background: bool = False) -> dict:
    """One full pass. Serialised: two passes never run at the same time."""
    global _last_report
    with _run_lock:
        started = time.time()
        xa_report = xa.recover_in_doubt(background=background)
        refunds = settle_queued_refunds()
        _last_report = {
            "ran_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "trigger": "background" if background else "manual",
            "took_ms": int((time.time() - started) * 1000),
            "in_doubt": xa_report,
            "refunds": refunds,
        }
        if xa_report["committed"] or xa_report["rolled_back"] or refunds["settled"]:
            log.info(
                "recovery: %s committed, %s rolled back, %s refunds settled",
                len(xa_report["committed"]),
                len(xa_report["rolled_back"]),
                len(refunds["settled"]),
            )
        return _last_report


def last_report() -> dict:
    return _last_report


def start_background_worker() -> None:
    interval = settings.RECOVERY_INTERVAL_S
    if interval <= 0:
        log.info("background recovery disabled (RECOVERY_INTERVAL_S=0)")
        return

    def loop():
        time.sleep(3)  # let the nodes finish starting
        while True:
            try:
                run_recovery(background=True)
            except Exception as exc:  # a node being down must never kill the worker
                log.warning("recovery pass failed: %s", exc.__class__.__name__)
            time.sleep(interval)

    threading.Thread(target=loop, name="recovery-worker", daemon=True).start()
    log.info("background recovery every %ss", interval)
