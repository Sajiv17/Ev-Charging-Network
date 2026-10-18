# Crash Recovery and Deadlocks: the Database Side

Owner: Person 1 (Database). Scripts: `scripts/db/crash_recovery_demo.sh`, `scripts/db/deadlock_demo.sh`.

This is the MySQL evidence behind two of the project's demos. The backend's versions of these
demos (`docs/RECOVERY_DEMO.md`, the deadlock demo in `docs/CONCURRENCY.md`) belong to Person 2.
These scripts show what the storage engine itself does, with no backend involved, and can be
run live in the viva.

---

## 1. Crash recovery

### How InnoDB recovers (and a correction for the README)

The README says "WAL-based **deferred update** recovery". InnoDB actually uses **immediate update
with UNDO/REDO logging**, the ARIES family. The viva answer should say so:

| | Deferred update (textbook NO-UNDO/REDO) | InnoDB (UNDO/REDO) |
|---|---|---|
| When do changes reach the data pages? | only after commit | any time, even before commit (the buffer pool flushes dirty pages when it likes) |
| Write-ahead log | redo only | **redo log** (`#innodb_redo/`) for every change, **undo log** for the old row versions |
| After a crash | redo committed transactions; nothing to undo | **redo** everything in the log (repeat history), then **undo** every transaction that had not committed |

The WAL rule still holds: a change's redo record reaches disk before the page it changes, and a
`COMMIT` returns only after its redo record is on disk.

### The settings that make it durable

Unchanged MySQL 8.0 defaults, verified by the script:

| Setting | Value | Meaning |
|---|---|---|
| `innodb_flush_log_at_trx_commit` | 1 | redo log flushed to disk at every COMMIT |
| `sync_binlog` | 1 | binary log flushed at every COMMIT |
| `log_bin`, `binlog_format` | ON, ROW | the binlog also records every committed change (used for replication and point-in-time recovery) |
| `innodb_doublewrite` | ON | protects against half-written (torn) pages |
| `innodb_redo_log_capacity` | 100 MB | size of the redo log |

### What the demo does

`scripts/db/crash_recovery_demo.sh` runs on the Bangalore node:

1. **Committed booking.** `sp_create_booking` books a slot and debits the wallet, then commits.
2. **Uncommitted booking.** A second session debits the wallet, inserts a booking and its payment,
   and closes the slot, so 4 rows are modified. It never commits.
3. **Crash.** `docker kill -s KILL ev-mysql-bangalore` gives mysqld no chance to shut down cleanly,
   like a power cut. The container is then restarted.
4. **XA in doubt.** Steps 2–3 are repeated with an XA transaction stopped after
   `XA PREPARE`, the state two-phase commit is in between "every node voted yes" and the
   coordinator's COMMIT.

Real output (MySQL error log at Note level; the script raises the verbosity for the demo and resets it afterwards):

```
open transaction just before the crash (information_schema.innodb_trx):
| trx_id | trx_state | trx_rows_modified |
|   4633 | RUNNING   |                 4 |
>>> docker kill -s KILL ev-mysql-bangalore
>>> recovery lines from the MySQL error log:
    [InnoDB] Database was not shutdown normally!
    [InnoDB] Starting crash recovery.
    [Server] Starting XA crash recovery...
    [Server] XA crash recovery finished.
    [InnoDB] Rolling back trx with id 4633, 4 rows to undo
    [InnoDB] Rollback of trx with id 4633 completed
>>> after recovery:
    committed booking on slot 156 survived:   YES
    uncommitted booking on slot 148 is gone:  YES
    its payment is gone:                     YES
    slot 148 is open again:                   YES
    wallet = after the committed booking:    YES (Rs 2227.83)
```

The open transaction modified 4 rows, and recovery undid exactly 4 rows. The committed booking
survived because its redo was on disk before `COMMIT` returned.

### Two-phase commit across a crash

```
>>> recovery lines from the MySQL error log:
    [InnoDB] Transaction 5139 was in the XA prepared state.
    [InnoDB] 1 transactions in prepared state after recovery
    [Server] Found 1 prepared XA transactions
>>> XA RECOVER as ev_user (the backend's user; needs XA_RECOVER_ADMIN):
    | formatID | gtrid_length | bqual_length | data           |
    |        1 |           14 |            0 | crash-demo-140 |
>>> coordinator decides ROLLBACK:
    in-doubt booking on slot 140 gone: YES; prepared transactions left: 0
```

A prepared transaction is **neither rolled back nor committed** by recovery. The node promised the
coordinator it can still commit, so it keeps the changes and their locks until told. The
coordinator must ask each node `XA RECOVER` and finish every in-doubt transaction with
`XA COMMIT` or `XA ROLLBACK`.

In MySQL 8, `XA RECOVER` requires the `XA_RECOVER_ADMIN` privilege. `database/mysql/init.sh`
grants it to `ev_user`, the account the backend uses, so Person 2's phase-2 recovery code can
run it.

---

## 2. Deadlock: why every transaction locks slot, then wallet

`scripts/db/deadlock_demo.sh` holds two locks in two sessions and changes nothing.

**Part 1, wrong order.** T1 locks `slots[53]` then `users[5]` (the wallet). T2 locks `users[5]` then
`slots[53]`. Each now waits for a lock the other holds, which is a cycle in the wait-for graph.
InnoDB's deadlock detector finds it immediately and rolls back the cheaper transaction.
Timestamps are `SYSDATE(6)`, the moment each lock was granted:

```
T1:  11:24:25.170  locked slots[53]
     11:24:27.758  locked users[5].wallet     (asked at 27.17, waited for T2; granted when T2 was rolled back)
T2:  11:24:25.755  locked users[5].wallet
     (asks for slots[53] at 27.755: cycle -> chosen as victim)
     ERROR 1213 (40001): Deadlock found when trying to get lock; try restarting transaction

SHOW ENGINE INNODB STATUS -> LATEST DETECTED DEADLOCK
  *** (1) TRANSACTION 2644
  *** (1) HOLDS THE LOCK(S):        index PRIMARY of table `ev_bangalore`.`slots` lock_mode X locks rec but not gap
  *** (1) WAITING FOR THIS LOCK:    index PRIMARY of table `ev_bangalore`.`users` lock_mode X locks rec but not gap waiting
  *** (2) TRANSACTION 2645
  *** (2) HOLDS THE LOCK(S):        index PRIMARY of table `ev_bangalore`.`users` lock_mode X ...
  *** (2) WAITING FOR THIS LOCK:    index PRIMARY of table `ev_bangalore`.`slots` lock_mode X ... waiting
  *** WE ROLL BACK TRANSACTION (2)
```

**Part 2, right order** (the backend's rule: slot, then wallet). T2 asks for the slot first, so
it simply waits until T1 finishes. There is no cycle and no error:

```
T1:  11:13:31.084  locked slots[53]
     11:13:33.085  locked users[5].wallet
T2:  11:13:33.086  locked slots[53]          (asked at ~31.6, waited ~1.5 s until T1 rolled back)
     11:13:33.087  locked users[5].wallet
```

The backend avoids deadlocks by **ordering resources**, which breaks the "circular wait"
condition. It still retries on error 1213, because InnoDB can deadlock on locks the code does
not take explicitly: gap locks, and the shared lock a foreign-key check takes, as
`docs/CONCURRENCY.md` describes. The locks here are `rec but not gap` because both reads are
primary-key equality lookups. Strict 2PL holds them until `ROLLBACK`/`COMMIT`.

---

## Running them

```bash
scripts/db/deadlock_demo.sh          # ~10 s, changes nothing
scripts/db/crash_recovery_demo.sh    # ~30 s, kills and restarts ev-mysql-bangalore twice;
                                     # leaves one committed demo booking for driver.bangalore@demo.ev
```

Both need the compose MySQL nodes running and seeded. Re-running the crash demo picks the next
free slots, so it can be repeated.
