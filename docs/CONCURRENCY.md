# Concurrency Control: Booking with Strict Two-Phase Locking

Owner: Person 2 (Backend + Transactions)
Code: `backend/app/services/booking_service.py`
Demo: `backend/demo/concurrency_demo.py`

---

## 1. The problem

Two drivers see the same slot as "available" and press **Book** at the same instant.
Without concurrency control, both transactions do this:

```
T1: read slot -> available            T2: read slot -> available
T1: debit wallet, insert booking      T2: debit wallet, insert booking
T1: COMMIT                            T2: COMMIT
=> two confirmed bookings for one charger (double booking)
```

A second classic anomaly is the **lost update**. If one driver books two slots at once
and each transaction does "read balance -> compute new balance -> write it back":

```
T1: read balance = 5000               T2: read balance = 5000
T1: write 5000 - 880 = 4120           T2: write 5000 - 880 = 4120
=> two bookings, but only one was ever paid for
```

## 2. The fix: Strict 2PL with row locks

The booking runs as **one transaction** on the station's city node:

| Step | SQL | Lock |
|------|-----|------|
| 1 | `SELECT ... FROM slots ... WHERE slot_id = ? FOR UPDATE OF sl` | X lock on the slot row |
| 2 | check: available, in the future, charger not faulted | |
| 3 | check vehicle belongs to user and connector fits | |
| 4 | look up pricing plan and compute the prepaid amount | |
| 5 | `SELECT wallet_balance FROM users WHERE user_id = ? FOR UPDATE` | X lock on the wallet row |
| 6 | check balance >= amount | |
| 7 | `UPDATE users SET wallet_balance = wallet_balance - ?` | |
| 8 | `INSERT INTO bookings ...`, `INSERT INTO payments ...` | |
| 9 | `UPDATE slots SET is_available = FALSE` | |
| 10 | `COMMIT` (or `ROLLBACK` if any step failed) | **all locks released together** |

**Why this is two-phase locking.** Steps 1 to 9 are the *growing phase*: locks are only
acquired, never released. Step 10 is the *shrinking phase*: every lock is released at once.

**Why it is *strict* 2PL.** No lock is released before COMMIT, so no other transaction
can ever read our uncommitted writes. That rules out dirty reads and cascading rollbacks.
InnoDB holds row locks until the end of the transaction, so `FOR UPDATE` + one
`COMMIT` gives strict 2PL automatically.

**What happens to the second driver.** T2's `SELECT ... FOR UPDATE` on the same slot row
**blocks** until T1 commits. A locking read in InnoDB always reads the *latest committed*
row, not T2's old snapshot, so after the wait T2 sees `is_available = FALSE` and returns
`409 Slot already booked`. T2 rolls back and nothing was charged.

**Atomicity.** If anything fails at any step (insufficient balance, wrong connector, node
error), the whole transaction rolls back. There are no partial bookings and no
ghost charges.

## 3. Deadlock avoidance and handling

Every transaction that needs both locks takes them in the **same order: slot row, then
wallet row** (cancellation also follows this order: booking/slot, then wallet).
With a global lock order, two of our transactions can never wait for each other in a cycle.

InnoDB can still choose a deadlock victim in edge cases (gap locks, foreign-key checks).
When that happens MySQL returns **error 1213**. The service catches it, rolls back,
waits briefly (100 ms, then 200 ms) and **retries up to 3 times**.
Lock waits are capped at 10 s (`innodb_lock_wait_timeout`, error 1205), so a stuck
transaction can never hang a request forever.

A real deadlock appeared while building the *unsafe* demo: inserting a booking makes
InnoDB take a **shared** lock on the referenced slot row (foreign-key check). Two
transactions holding S locks on the same row that then both try to `UPDATE` it (X lock)
wait for each other, which is a deadlock. This is a good viva example of an
S-to-X lock upgrade deadlock, and it will be the basis of the deadlock demo in phase 2.

## 4. Live demo

```bash
cd backend
python demo/concurrency_demo.py                      # unsafe vs locked, 5 drivers, same slot
python demo/concurrency_demo.py --scenario wallet    # lost update on one wallet
python demo/concurrency_demo.py --users 20 --delay 0 # stress test
```

The script fires all requests at the same instant (an `asyncio.Event` is used as a
starting gun). `--delay` pauses inside each transaction to make the race window wide
enough that it fails every time, not just sometimes.

### Real output (3 drivers, 300 ms delay)

```
=== UNSAFE : 3 drivers -> the same slot #1136 ===
   driver  2  slot  1136  201    330 ms  CONFIRMED booking #25  Rs 880.5
   driver  3  slot  1136  201    335 ms  CONFIRMED booking #26  Rs 880.5
   driver  1  slot  1136  201    339 ms  CONFIRMED booking #27  Rs 880.5
   RESULT: slot #1136 has 3 confirmed bookings -> DOUBLE BOOKED

=== LOCKED : 3 drivers -> the same slot #1137 ===
   driver  1  slot  1137  201    328 ms  CONFIRMED booking #28  Rs 880.5
   driver  2  slot  1137  409    335 ms  REJECTED  slot_unavailable: Slot already booked
   driver  3  slot  1137  409    335 ms  REJECTED  slot_unavailable: Slot already booked
   RESULT: slot #1137 has 1 confirmed booking -> correct

   Transaction log:
   +    0ms  tx-20642daa  LOCK_REQUEST    resource=slots[1137] lock=X
   +    1ms  tx-6b7d3e7c  LOCK_REQUEST    resource=slots[1137] lock=X
   +    2ms  tx-20642daa  LOCK_ACQUIRED   resource=slots[1137] waited_ms=2
   +   14ms  tx-20642daa  HOLDING_LOCKS   delay_ms=300
   +  316ms  tx-20642daa  WALLET_DEBIT    amount=880.5
   +  321ms  tx-20642daa  COMMIT          locks_released=True
   +  323ms  tx-6b7d3e7c  LOCK_ACQUIRED   resource=slots[1137] waited_ms=321
   +  327ms  tx-6b7d3e7c  ROLLBACK        reason=Slot already booked
```

`waited_ms=321` is the proof: the second transaction sat blocked for exactly as long as
the first one held its locks.

### Lost update (`--scenario wallet`, 4 bookings by one driver)

```
UNSAFE:  Should be debited Rs 3522.0 | Actually debited Rs 880.5  -> LOST UPDATE
LOCKED:  Should be debited Rs 3522.0 | Actually debited Rs 3522.0 -> correct
```

Stress test: 20 simultaneous requests on one slot gave 5 double bookings in unsafe mode
and exactly 1 booking in locked mode, over repeated runs.

### Note on the log timestamps

Timestamps are taken in Python *after* each database call returns, so lines that happen
within a few milliseconds of each other can appear slightly out of order. The database's
guarantee is shown by the slot report (`GET /api/demo/slot-report/{city}/{slot_id}`),
which counts confirmed bookings straight from MySQL.

## 5. Viva quick answers

- **2PL vs 2PC?** 2PL (Two-Phase *Locking*) is about concurrency on one node: acquire
  locks, then release them. 2PC (Two-Phase *Commit*) is about atomicity across nodes:
  PREPARE everywhere, then COMMIT everywhere. Same-city bookings use 2PL. Cross-city
  bookings (phase 2) use 2PL on each node plus 2PC between nodes.
- **Why not just `UPDATE slots SET is_available=0 WHERE slot_id=? AND is_available=1` and check
  rows affected?** That also works (optimistic, single-statement). We lock first because
  the booking also has to check and debit the wallet atomically, and the explicit lock makes
  the 2PL phases visible.
- **Isolation level?** InnoDB default, REPEATABLE READ. Plain SELECTs read a snapshot (which is
  why the unsafe version breaks). `FOR UPDATE` is a locking read that reads the latest
  committed version (which is why the locked version works).
- **What stops a negative wallet if the code has a bug?** `CHECK (wallet_balance >= 0)` in the
  schema (`02_backend_additions.sql`).
