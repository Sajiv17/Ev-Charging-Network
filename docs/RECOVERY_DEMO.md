# Distributed Transactions and Recovery: the Backend Side

Owner: Person 2 (Backend + Transactions)
Code: `backend/app/services/xa.py` (coordinator), `cross_city.py`, `recovery_service.py`
Demo: `backend/demo/recovery_demo.py`
Database side (InnoDB crash recovery, `XA RECOVER` from the mysql CLI): `docs/DB_RECOVERY_AND_DEADLOCK.md`

---

## 1. Why a cross-city booking needs Two-Phase Commit

Each city has its own MySQL node. A user's wallet lives on their **home** node
(`users.home_city_id`), and a station's slots and bookings live on **its city's** node.
When a Bangalore driver books a Chennai charger:

| Node | Work |
|------|------|
| Chennai (station node) | lock slot, insert booking + payment, close slot |
| Bangalore (home node) | lock wallet, debit |

These are two independent databases. If each just ran `COMMIT`, a crash in between could leave
**money taken and no booking**, or **a booking that was never paid for**. Two-Phase Commit makes
the pair atomic.

## 2. How the backend does it (MySQL XA)

The FastAPI backend is the **coordinator**; each MySQL node is a **participant**.

```
            Chennai node                          Bangalore node
XA START 'ev-6283cf4a5460','chennai'
SELECT ... FROM slots ... FOR UPDATE      XA START 'ev-6283cf4a5460','bangalore'
                                          SELECT wallet_balance ... FOR UPDATE
                                          UPDATE users SET wallet_balance = wallet_balance - 840
INSERT bookings, payments; UPDATE slots
---------------------------- PHASE 1: voting ----------------------------
XA END; XA PREPARE        -> "yes"        XA END; XA PREPARE        -> "yes"
     (changes + locks kept, durable in the redo log, can still commit OR roll back)
------------------- decision: COMMIT written + fsync'ed to the coordinator log ----
---------------------------- PHASE 2: completion ------------------------
XA COMMIT                                 XA COMMIT
```

Real audit log from one booking (`GET /api/demo/audit-log`):

```
XA_BEGIN
XA_START       chennai
LOCK_ACQUIRED  chennai    slots[532]
XA_START       bangalore
LOCK_ACQUIRED  bangalore  users[5].wallet
WALLET_DEBIT   bangalore
BOOKING_WRITTEN chennai
XA_PREPARED    chennai    vote=yes
XA_PREPARED    bangalore  vote=yes
XA_DECISION    COMMIT  (logged)
XA_COMMIT      chennai
XA_COMMIT      bangalore
```

**Rules the coordinator follows**

- Any error before the decision (slot taken, wallet too low, a node not answering a PREPARE):
  `XA ROLLBACK` on every branch. Nothing happened anywhere.
- The COMMIT decision is written to the **coordinator's own write-ahead log**
  (`backend/var/xa_coordinator.log`, appended and `fsync`'ed) **before** any node is told to
  commit. From that moment the transaction *will* commit, even if the backend dies.
- A node that is down during phase 2 is not a failure: the booking is confirmed to the user,
  and recovery sends that node its `XA COMMIT` when it is back.

Same-city bookings don't need any of this: one node, one ordinary transaction
(`docs/CONCURRENCY.md`).

**2PL inside 2PC.** Each node still uses strict 2PL (`FOR UPDATE`, locks held until the end).
The global lock order is the same as on one node: slot (station node) first, wallet (home node)
second. InnoDB cannot detect a deadlock that spans two nodes, so this ordering is what prevents
one. A 10 s lock-wait timeout with retry is the safety net.

## 3. Recovery

A participant that voted *yes* has given up the right to decide alone. After `XA PREPARE` it
keeps its changes **and its locks** until it hears COMMIT or ROLLBACK, even across its own crash
and restart. Such a branch is **in doubt**.

`recover_in_doubt()` (in `xa.py`) runs at startup, every 30 s on a background thread, and on
`POST /api/admin/recover`:

1. Ask every node `XA RECOVER` (needs the `XA_RECOVER_ADMIN` privilege, granted to `ev_user`
   by `database/mysql/init.sh`).
2. For each prepared branch whose id starts with `ev-` (created by this backend):
   - decision log says **COMMIT** → `XA COMMIT`
   - no COMMIT in the log → `XA ROLLBACK`. This is **presumed abort**: the coordinator only
     ever logs commits, so "no record" safely means "never decided to commit".
3. Branches the backend is still working on are skipped.

The same recovery pass also pays **queued refunds**. When a charger faults, Vyaan's
`after_charger_fault` trigger refunds bookings, but it can only credit a wallet on its own node.
For a user from another city it inserts the refund as `queued`. The backend settles it with 2PC:
refund row `queued → completed` on the station node, wallet `+= amount` on the home node.
`POST /api/operator/chargers/{city}/{id}/status` runs this immediately after a fault, so the
driver is refunded within the same request.

## 4. The demo

```bash
cd backend
python demo/recovery_demo.py                 # scenarios 1 and 2
python demo/recovery_demo.py --node-crash    # also scenario 3 (kills ev-mysql-chennai with docker)
```

The demo endpoint can stop the coordinator at two points (`fail_point`), to simulate the backend
crashing mid-2PC. A simulated crash is hidden from the background recovery worker for 2 minutes,
so the in-doubt state can be shown before recovery runs.

### Real output

```
1. Coordinator crashes after PREPARE, before deciding
>>> State right after the crash (both branches in doubt, locks still held):
    prepared branch of ev-72047e49d60d on each node : {'bangalore': 'YES', 'chennai': 'YES', 'delhi': 'no'}
    booking visible on Chennai node      : no
    wallet on Bangalore node             : Rs 5000.0
>>> Recovery: decision log has NO commit for this transaction -> presumed abort
    bangalore  XA ROLLBACK ev-72047e49d60d
    chennai    XA ROLLBACK ev-72047e49d60d
    RESULT: both nodes rolled back, nothing half-done

2. Coordinator crashes after logging COMMIT, before telling the nodes
>>> State right after the crash (decided, but no node has committed yet):
    prepared branch of ev-ab9032e0d98d on each node : {'bangalore': 'YES', 'chennai': 'YES', 'delhi': 'no'}
    booking visible on Chennai node      : no
    wallet on Bangalore node             : Rs 5000.0
>>> Recovery: decision log says COMMIT -> the coordinator's promise is kept
    bangalore  XA COMMIT ev-ab9032e0d98d
    chennai    XA COMMIT ev-ab9032e0d98d
    booking visible on Chennai node      : YES
    wallet on Bangalore node             : Rs 4160.0
    RESULT: both nodes committed: booking exists AND wallet debited

3. The Chennai MySQL node itself crashes while prepared
>>> Kill the Chennai node
    in doubt now: {'bangalore': ['ev-aee151066979'], 'chennai': 'UNREACHABLE', 'delhi': []}
>>> After restart: InnoDB crash recovery KEPT the prepared branch (it is in the redo log)
    prepared branch of ev-aee151066979 on each node : {'bangalore': 'YES', 'chennai': 'YES', 'delhi': 'no'}
>>> Recovery: decision log says COMMIT
    bangalore  XA COMMIT ev-aee151066979
    chennai    XA COMMIT ev-aee151066979
    RESULT: prepared branch survived the node crash and was committed
```

The Chennai node's MySQL error log for scenario 3 confirms it from the database side:

```
[Server] Starting XA crash recovery...
[Server] Found 1 prepared XA transactions
[Server] XA crash recovery finished.
```

## 5. Viva quick answers

- **2PL vs 2PC?** 2PL is concurrency control on one node: grow locks, release them all at commit.
  2PC is atomic commitment across nodes: everyone PREPAREs (votes), then everyone COMMITs.
  Cross-city bookings use both.
- **Why can't a prepared node just roll back on its own after a timeout?** It promised the
  coordinator it can commit. The coordinator may already have told the other node to commit;
  rolling back alone would break atomicity. That waiting is the known **blocking** weakness of 2PC.
- **What is the coordinator's log for?** It makes the decision durable. Without it, a coordinator
  that crashes after telling one node COMMIT could not finish the other one after restart.
- **Presumed abort?** Only COMMIT decisions are logged. On recovery, any prepared branch with no
  logged COMMIT is rolled back. Fewer log writes, and the safe default.
- **InnoDB recovery vs 2PC recovery?** InnoDB (redo + undo, ARIES style) makes each *node*
  consistent on its own: committed work is redone, uncommitted work undone, prepared work kept.
  2PC recovery then makes the *nodes agree with each other*.
- **What about the README's "deferred update"?** InnoDB uses immediate update with undo/redo
  logging, not deferred update. See `docs/DB_RECOVERY_AND_DEADLOCK.md`.
