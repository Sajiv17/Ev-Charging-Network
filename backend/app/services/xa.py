"""
Two-Phase Commit (2PC) across city nodes, using MySQL XA transactions.

WHY
---
A Bangalore user booking a Chennai charger touches TWO databases:
  * Chennai node   : lock the slot, write booking + payment
  * Bangalore node : lock the wallet, debit it
Each node can commit or roll back on its own, so without coordination one
could commit while the other rolls back (money gone, no booking). 2PC makes
the pair atomic: both commit or both roll back.

HOW (the backend is the COORDINATOR, each MySQL node is a PARTICIPANT)
---
    XA START 'gtrid','city'      begin a branch of the global transaction
    ... normal SQL, with SELECT ... FOR UPDATE locks (2PL on each node) ...
    XA END   'gtrid','city'
    XA PREPARE 'gtrid','city'    PHASE 1 "vote": node writes everything to its
                                 redo log and promises it can still commit.
                                 Locks stay held.
  coordinator writes COMMIT to its own log (fsync)   <- the decision point
    XA COMMIT 'gtrid','city'     PHASE 2 on every node

If anything fails before the decision is logged, every branch is rolled back.
After the decision is logged, the transaction WILL commit: a node that is down
gets its XA COMMIT later from recover_in_doubt() ("presumed abort": a gtrid
with no COMMIT in the log is rolled back by recovery).

Branches are plain pymysql connections from the same pools as the rest of the
app (engine.raw_connection()), so the session time zone hook still applies.
"""

import json
import logging
import os
import re
import threading
import time
import uuid

import pymysql
from pymysql.cursors import DictCursor

from app.core.cities import CITIES, normalize_city
from app.core.config import settings
from app.db.mysql_connection import ENGINES
from app.services import audit

log = logging.getLogger("xa")

GTRID_PREFIX = "ev-"
LOCK_WAIT_TIMEOUT_S = 10

# Demo-only fault injection points (see demo/recovery_demo.py)
FAIL_AFTER_PREPARE = "after_prepare"  # coordinator "crashes" before deciding  -> recovery rolls back
FAIL_AFTER_DECISION = "after_decision"  # coordinator "crashes" after deciding -> recovery commits
FAIL_POINTS = (FAIL_AFTER_PREPARE, FAIL_AFTER_DECISION)


class CoordinatorCrash(Exception):
    """Raised by the fault-injection points to simulate the coordinator dying."""

    def __init__(self, gtrid: str, point: str):
        super().__init__(f"simulated coordinator crash {point} for {gtrid}")
        self.gtrid = gtrid
        self.point = point


# =============================================================================
# SQL helper: lets services write ":name" parameters like the rest of the code
# =============================================================================

_PARAM = re.compile(r"(?<![:\w]):(\w+)")


class Q:
    """Small wrapper over a pymysql DictCursor. Accepts SQL with :name params."""

    def __init__(self, conn):
        self.conn = conn

    def _run(self, sql: str, params: dict | None):
        cur = self.conn.cursor(DictCursor)
        cur.execute(_PARAM.sub(r"%(\1)s", sql), params or {})
        return cur

    def one(self, sql: str, **params) -> dict | None:
        cur = self._run(sql, params)
        row = cur.fetchone()
        cur.close()
        return row

    def all(self, sql: str, **params) -> list[dict]:
        cur = self._run(sql, params)
        rows = cur.fetchall()
        cur.close()
        return list(rows)

    def exec(self, sql: str, **params):
        cur = self._run(sql, params)
        n, last = cur.rowcount, cur.lastrowid
        cur.close()
        return n, last

    def scalar(self, sql: str, **params):
        row = self.one(sql, **params)
        return next(iter(row.values())) if row else None


def mysql_errno(exc: BaseException) -> int | None:
    """MySQL error number from a pymysql or SQLAlchemy exception."""
    orig = getattr(exc, "orig", exc)
    args = getattr(orig, "args", None)
    return args[0] if args and isinstance(args[0], int) else None


def _checkout(city: str):
    raw = ENGINES[normalize_city(city)].raw_connection()
    raw.dbapi_connection.autocommit(True)  # XA statements manage the transaction themselves
    return raw


def _release(raw, *, broken: bool = False):
    try:
        if broken:
            raw.invalidate()  # close the socket; anything prepared stays prepared on the server
        else:
            raw.dbapi_connection.autocommit(False)
            raw.close()  # back to the pool
    except Exception:
        pass


# =============================================================================
# The coordinator's decision log (its own write-ahead log)
# =============================================================================


class DecisionLog:
    """
    Append-only JSON lines file. A COMMIT decision is fsync'ed to disk BEFORE
    any participant is told to commit; that is what makes it safe for recovery
    to finish the transaction after a crash.
    """

    def __init__(self, path: str):
        self.path = os.path.abspath(path)
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(self.path), exist_ok=True)

    def append(self, record: dict) -> None:
        line = json.dumps({**record, "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}) + "\n"
        with self._lock, open(self.path, "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())

    def state(self) -> dict[str, dict]:
        """gtrid -> latest record (decision / done)."""
        out: dict[str, dict] = {}
        if not os.path.exists(self.path):
            return out
        with self._lock, open(self.path, encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue  # a torn last line after a crash = that record never happened
                g = rec.get("gtrid")
                if g:
                    out[g] = {**out.get(g, {}), **rec}
        return out

    def decision(self, gtrid: str) -> str | None:
        return self.state().get(gtrid, {}).get("decision")


decision_log = DecisionLog(settings.XA_LOG_PATH)

# gtrids this process is still driving; recovery must not touch them.
_inflight: set[str] = set()
_inflight_lock = threading.Lock()

# Demo only: a simulated crash is hidden from the BACKGROUND worker for a while,
# so the evaluator can see the in-doubt state before recovery runs.
DEMO_HOLD_S = 120
_demo_hold: dict[str, float] = {}


# =============================================================================
# Branches
# =============================================================================


class XABranch:
    """One participant (one city node) of a global transaction."""

    def __init__(self, gtrid: str, city: str, txn: str | None):
        self.gtrid, self.city, self.txn = gtrid, normalize_city(city), txn
        self.raw = _checkout(self.city)
        self.q = Q(self.raw.dbapi_connection)
        self.state = "idle"  # idle -> active -> idle_ended -> prepared -> committed / rolled_back

    @property
    def xid(self) -> str:
        return f"'{self.gtrid}','{self.city}'"

    def _xa(self, stmt: str) -> None:
        self.raw.dbapi_connection.cursor().execute(f"XA {stmt} {self.xid}")

    def start(self) -> None:
        self.q.exec(f"SET SESSION innodb_lock_wait_timeout = {LOCK_WAIT_TIMEOUT_S}")
        self._xa("START")
        self.state = "active"

    def prepare(self) -> None:
        self._xa("END")
        self.state = "ended"
        self._xa("PREPARE")
        self.state = "prepared"
        audit.record("XA_PREPARED", txn=self.txn, city=self.city, gtrid=self.gtrid, vote="yes")

    def commit(self) -> None:
        self._xa("COMMIT")
        self.state = "committed"

    def rollback(self) -> None:
        if self.state == "active":
            try:
                self._xa("END")
            except Exception:
                pass
        if self.state in ("active", "ended", "prepared"):
            self._xa("ROLLBACK")
        self.state = "rolled_back"

    def release(self, broken: bool = False) -> None:
        _release(self.raw, broken=broken)


class TwoPhaseCommit:
    """
    Usage:
        with TwoPhaseCommit("booking", txn=txn) as tpc:
            s = tpc.branch("chennai")      # XA START on Chennai
            ... s.q.one("SELECT ... FOR UPDATE", ...) ...
            h = tpc.branch("bangalore")    # XA START on Bangalore
            ...
            tpc.commit()                   # PREPARE all, log decision, COMMIT all
    Leaving the block without commit() (or with an exception) rolls back every branch.
    """

    def __init__(self, label: str, txn: str | None = None, fail_point: str | None = None):
        self.gtrid = GTRID_PREFIX + uuid.uuid4().hex[:12]
        self.label, self.txn, self.fail_point = label, txn, fail_point
        self.branches: list[XABranch] = []
        self.done = False
        self.pending_commit: list[str] = []  # nodes that still owe us an XA COMMIT

    def __enter__(self):
        with _inflight_lock:
            _inflight.add(self.gtrid)
        audit.record("XA_BEGIN", txn=self.txn, gtrid=self.gtrid, op=self.label)
        return self

    def branch(self, city: str) -> XABranch:
        city = normalize_city(city)
        for b in self.branches:
            if b.city == city:
                return b
        b = XABranch(self.gtrid, city, self.txn)
        self.branches.append(b)
        try:
            b.start()
        except Exception:
            b.release(broken=True)
            self.branches.remove(b)
            raise
        audit.record("XA_START", txn=self.txn, city=city, gtrid=self.gtrid)
        return b

    def commit(self) -> None:
        # ---- Phase 1: every participant votes by preparing ------------------------
        for b in self.branches:
            b.prepare()

        if self.fail_point == FAIL_AFTER_PREPARE:
            self._crash(FAIL_AFTER_PREPARE)

        # ---- Decision point: durable BEFORE anyone is told to commit -------------
        decision_log.append(
            {
                "gtrid": self.gtrid,
                "decision": "commit",
                "op": self.label,
                "branches": [b.city for b in self.branches],
            }
        )
        audit.record("XA_DECISION", txn=self.txn, gtrid=self.gtrid, decision="COMMIT", logged=True)

        if self.fail_point == FAIL_AFTER_DECISION:
            self._crash(FAIL_AFTER_DECISION)

        # ---- Phase 2: tell every participant ------------------------------------
        for b in self.branches:
            try:
                b.commit()
                audit.record("XA_COMMIT", txn=self.txn, city=b.city, gtrid=self.gtrid)
            except Exception as exc:  # node died between phases: recovery finishes it
                self.pending_commit.append(b.city)
                audit.record(
                    "XA_COMMIT_PENDING",
                    txn=self.txn,
                    city=b.city,
                    gtrid=self.gtrid,
                    reason=exc.__class__.__name__,
                )
                b.release(broken=True)
        if not self.pending_commit:
            decision_log.append({"gtrid": self.gtrid, "state": "done"})
        self.done = True

    def _crash(self, point: str) -> None:
        audit.record(
            "COORDINATOR_CRASH",
            txn=self.txn,
            gtrid=self.gtrid,
            point=point,
            note="simulated: connections dropped, branches left prepared",
        )
        for b in self.branches:
            b.release(broken=True)
        self.branches = []
        self.done = True  # nothing left for __exit__ to roll back
        _demo_hold[self.gtrid] = time.monotonic() + DEMO_HOLD_S
        raise CoordinatorCrash(self.gtrid, point)

    def __exit__(self, exc_type, exc, tb):
        try:
            if not self.done:
                for b in self.branches:
                    try:
                        b.rollback()
                        audit.record("XA_ROLLBACK", txn=self.txn, city=b.city, gtrid=self.gtrid)
                    except Exception:
                        # unreachable node: it has no COMMIT decision, so recovery rolls it back
                        b.release(broken=True)
                        b.raw = None
            for b in self.branches:
                if b.raw is not None and b.state in ("committed", "rolled_back"):
                    b.release()
        finally:
            with _inflight_lock:
                _inflight.discard(self.gtrid)
        return False


class LocalTxn:
    """
    Same interface as TwoPhaseCommit for the single-node case (station node ==
    wallet node): one ordinary transaction, branch(city) always returns it.
    """

    class _Branch:
        def __init__(self, city):
            self.city = normalize_city(city)
            self.raw = _checkout(self.city)
            self.raw.dbapi_connection.autocommit(False)
            self.q = Q(self.raw.dbapi_connection)
            self.q.exec(f"SET SESSION innodb_lock_wait_timeout = {LOCK_WAIT_TIMEOUT_S}")

    def __init__(self, city: str, label: str, txn: str | None = None):
        self.city, self.label, self.txn = normalize_city(city), label, txn
        self.b = None
        self.done = False
        self.pending_commit: list[str] = []
        self.gtrid = None

    def __enter__(self):
        self.b = self._Branch(self.city)
        audit.record("BEGIN", txn=self.txn, city=self.city, op=self.label)
        return self

    def branch(self, city: str):
        if normalize_city(city) != self.city:
            raise ValueError("LocalTxn used for two different nodes")
        return self.b

    def commit(self) -> None:
        self.b.raw.dbapi_connection.commit()
        self.done = True
        audit.record("COMMIT", txn=self.txn, city=self.city, op=self.label)

    def __exit__(self, exc_type, exc, tb):
        try:
            if not self.done:
                try:
                    self.b.raw.dbapi_connection.rollback()
                except Exception:
                    pass
                audit.record(
                    "ROLLBACK",
                    txn=self.txn,
                    city=self.city,
                    op=self.label,
                    reason=getattr(exc, "message", None) or (repr(exc)[:200] if exc else None),
                )
        finally:
            # A dead connection is dropped instead of going back to the pool.
            _release(
                self.b.raw,
                broken=isinstance(exc, pymysql.err.OperationalError)
                and mysql_errno(exc) in (2006, 2013, None),
            )
        return False


def transaction(
    station_city: str, wallet_city: str, label: str, txn: str | None = None, fail_point: str | None = None
):
    """One local transaction if both rows live on the same node, otherwise 2PC."""
    if normalize_city(station_city) == normalize_city(wallet_city) and not fail_point:
        return LocalTxn(station_city, label, txn)
    return TwoPhaseCommit(label, txn, fail_point)


# =============================================================================
# Recovery: finish transactions left in doubt by a crash
# =============================================================================


def list_in_doubt() -> dict:
    """XA RECOVER on every node: prepared branches nobody has committed or rolled back."""
    out = {}
    for city in CITIES:
        try:
            raw = _checkout(city)
        except Exception as exc:
            out[city] = {"reachable": False, "error": exc.__class__.__name__}
            continue
        try:
            rows = Q(raw.dbapi_connection).all("XA RECOVER")
            xids = []
            for r in rows:
                data = r["data"].decode() if isinstance(r["data"], (bytes, bytearray)) else r["data"]
                g = int(r["gtrid_length"])
                xids.append({"gtrid": data[:g], "bqual": data[g:]})
            out[city] = {"reachable": True, "prepared": xids}
        finally:
            _release(raw)
    return out


def recover_in_doubt(background: bool = False) -> dict:
    """
    For every prepared branch created by this backend (gtrid 'ev-...'):
      decision log says COMMIT -> XA COMMIT   (the coordinator promised it)
      otherwise               -> XA ROLLBACK  (presumed abort: no decision = no commit)
    Branches the running process is still driving are skipped.
    """
    report = {"committed": [], "rolled_back": [], "skipped": [], "unreachable": [], "errors": []}
    state = decision_log.state()
    listing = list_in_doubt()
    with _inflight_lock:
        busy = set(_inflight)
    now = time.monotonic()
    if background:
        busy |= {g for g, until in _demo_hold.items() if until > now}
    for city, info in listing.items():
        if not info["reachable"]:
            report["unreachable"].append(city)
            continue
        for x in info["prepared"]:
            g, bq = x["gtrid"], x["bqual"]
            if not g.startswith(GTRID_PREFIX):
                report["skipped"].append({"city": city, "gtrid": g, "why": "not created by the backend"})
                continue
            if g in busy:
                report["skipped"].append(
                    {"city": city, "gtrid": g, "why": "in progress or held for the demo"}
                )
                continue
            action = "COMMIT" if state.get(g, {}).get("decision") == "commit" else "ROLLBACK"
            raw = _checkout(city)
            try:
                raw.dbapi_connection.cursor().execute(f"XA {action} '{g}','{bq}'")
                (report["committed"] if action == "COMMIT" else report["rolled_back"]).append(
                    {"city": city, "gtrid": g}
                )
                audit.record(
                    "XA_RECOVERED",
                    city=city,
                    gtrid=g,
                    action=action,
                    reason="decision log says commit"
                    if action == "COMMIT"
                    else "no commit decision logged (presumed abort)",
                )
            except Exception as exc:
                report["errors"].append({"city": city, "gtrid": g, "error": str(exc)[:200]})
            finally:
                _release(raw)

    # A commit decision is fully done once no reachable node still holds a branch of it.
    if not report["unreachable"]:
        still = {x["gtrid"] for i in list_in_doubt().values() if i["reachable"] for x in i["prepared"]}
        for g, rec in state.items():
            if (
                rec.get("decision") == "commit"
                and rec.get("state") != "done"
                and g not in still
                and g not in busy
            ):
                decision_log.append({"gtrid": g, "state": "done"})
    return report
