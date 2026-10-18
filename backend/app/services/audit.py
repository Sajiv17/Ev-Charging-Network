"""
Transaction audit trail for the live demo.

Every booking transaction reports its steps here (BEGIN, LOCK_WAIT,
LOCK_ACQUIRED, DEBIT, COMMIT, ROLLBACK ...). Each event goes to:

1. An in-memory ring buffer -> served by GET /api/demo/audit-log, so the
   frontend's "live transaction log" works even if MongoDB is down.
2. MongoDB `audit_log` collection (Person 3's collection) -> written on a
   background thread so a slow/missing MongoDB never slows a booking.
"""

import logging
import threading
import time
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

log = logging.getLogger("audit")

_BUFFER: deque = deque(maxlen=2000)
_SEQ = 0
_LOCK = threading.Lock()

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="audit-mongo")
_mongo_disabled_until = 0.0


def new_txn_id() -> str:
    return "tx-" + uuid.uuid4().hex[:8]


def record(event: str, *, txn: str | None = None, city: str | None = None, **details) -> dict:
    """Record one audit event. Never raises."""
    global _SEQ
    with _LOCK:
        _SEQ += 1
        entry = {
            "seq": _SEQ,
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "event": event,
            "txn": txn,
            "city": city,
            "thread": threading.current_thread().name,
            **details,
        }
        _BUFFER.append(entry)
    log.info("%s %s %s %s", txn or "-", event, city or "-", details or "")
    _executor.submit(_write_to_mongo, dict(entry))
    return entry


def recent(limit: int = 200, after_seq: int = 0, txn: str | None = None) -> list[dict]:
    with _LOCK:
        items = [e for e in _BUFFER if e["seq"] > after_seq and (txn is None or e["txn"] == txn)]
    return items[-limit:]


def clear() -> None:
    with _LOCK:
        _BUFFER.clear()


def _write_to_mongo(entry: dict) -> None:
    global _mongo_disabled_until
    if time.monotonic() < _mongo_disabled_until:
        return
    try:
        from app.db.mongodb_connection import audit_log_collection

        audit_log_collection.with_options().insert_one(entry)
    except Exception as exc:  # MongoDB down or not configured: keep working
        _mongo_disabled_until = time.monotonic() + 60
        log.warning("audit: MongoDB write failed, retrying in 60s (%s)", exc.__class__.__name__)
