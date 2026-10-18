"""
Recovery demo: two-phase commit across city nodes, and what happens when
something crashes in the middle of it.

A Bangalore driver books a CHENNAI charger. That is a distributed transaction:
    Chennai node   : slot locked, booking + payment written
    Bangalore node : wallet locked and debited
The backend coordinates it with 2PC (MySQL XA). We crash it on purpose:

  1. coordinator crashes AFTER PREPARE, BEFORE deciding
       both nodes are "in doubt": they voted yes and must wait
       recovery finds no COMMIT in the decision log -> ROLLBACK both (presumed abort)
  2. coordinator crashes AFTER logging COMMIT, before telling the nodes
       recovery finds COMMIT in the decision log -> COMMIT both
  3. (--node-crash) same as 2, and the Chennai MySQL node is killed (-9) and
       restarted while its branch is prepared. The prepared branch SURVIVES the
       crash (it is in the redo log), and recovery commits it afterwards.

Needs the API with DEMO_MODE=true and the seed data (admin@demo.ev, driver.bangalore@demo.ev).

    cd backend
    python demo/recovery_demo.py                    # scenarios 1 and 2
    python demo/recovery_demo.py --node-crash       # also scenario 3 (uses docker)
"""

import argparse
import subprocess
import sys
import time

import httpx

PASSWORD = "demo1234"
STATION_CITY = "chennai"


def login(c, email):
    r = c.post("/api/users/login", json={"email": email, "password": PASSWORD})
    if r.status_code != 200:
        sys.exit(f"Cannot log in as {email}: {r.text}. Is the seed data loaded?")
    d = r.json()
    return {"Authorization": f"Bearer {d['access_token']}"}, d["user"]


def wallet(c, h):
    return c.get("/api/users/me/wallet", headers=h).json()["wallet_balance"]


def in_doubt(c, admin):
    nodes = c.get("/api/admin/nodes", headers=admin).json()["in_doubt"]
    return {
        city: [x["gtrid"] for x in info.get("prepared", [])] if info["reachable"] else "UNREACHABLE"
        for city, info in nodes.items()
    }


def slot_report(c, slot_id):
    return c.get(f"/api/demo/slot-report/{STATION_CITY}/{slot_id}").json()


def step(msg):
    print(f"\n>>> {msg}")


def show_state(c, drv, admin, slot_id, gtrid):
    doubt = in_doubt(c, admin)
    rep = slot_report(c, slot_id)
    mine = {k: ("YES" if gtrid in v else "no") if isinstance(v, list) else v for k, v in doubt.items()}
    print(f"    prepared branch of {gtrid} on each node : {mine}")
    print(f"    booking visible on Chennai node      : {'YES' if rep['confirmed_bookings'] else 'no'}")
    print(f"    wallet on Bangalore node             : Rs {wallet(c, drv)}")


def crash_booking(c, drv, vehicle_id, slot_id, point):
    r = c.post(
        "/api/demo/book",
        headers=drv,
        json={"city": STATION_CITY, "slot_id": slot_id, "vehicle_id": vehicle_id, "fail_point": point},
    )
    body = r.json()
    if body.get("code") != "coordinator_crash_simulated":
        sys.exit(f"Expected a simulated crash, got {r.status_code}: {body}")
    gtrid = body["detail"].split("Transaction ")[1].split(" ")[0]
    print(f"    API answered {r.status_code}: {body['detail']}")
    return gtrid


def recover(c, admin, gtrid):
    rep = c.post("/api/admin/recover", headers=admin).json()["in_doubt"]
    for kind in ("committed", "rolled_back"):
        for x in rep[kind]:
            if x["gtrid"] == gtrid:
                print(f"    {x['city']:<10} XA {'COMMIT' if kind == 'committed' else 'ROLLBACK'} {gtrid}")
    if rep["unreachable"]:
        print(f"    unreachable nodes (will be retried): {rep['unreachable']}")


def wait_healthy(c, city, timeout=90):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if c.get("/health").json()["mysql_nodes"][city] == "up":
                return True
        except Exception:
            pass
        time.sleep(2)
    return False


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--api", default="http://localhost:8000")
    p.add_argument("--node-crash", action="store_true", help="also kill and restart the Chennai MySQL node")
    p.add_argument("--kill-cmd", default="docker kill -s KILL ev-mysql-chennai")
    p.add_argument("--start-cmd", default="docker start ev-mysql-chennai")
    a = p.parse_args()

    with httpx.Client(base_url=a.api, timeout=60) as c:
        try:
            c.get("/health").raise_for_status()
        except Exception:
            sys.exit(f"API not reachable at {a.api}")
        drv, user = login(c, "driver.bangalore@demo.ev")
        admin, _ = login(c, "admin@demo.ev")
        car = next(
            v for v in c.get("/api/users/me/vehicles", headers=drv).json() if v["connector_type"] == "CCS2"
        )
        print(
            f"Driver: {user['full_name']} (wallet on the {user['home_city'].upper()} node), "
            f"booking a charger in {STATION_CITY.upper()}"
        )

        # ------------------------------------------------------------------ 1
        print("\n" + "=" * 78 + "\n1. Coordinator crashes after PREPARE, before deciding\n" + "=" * 78)
        slot = c.post("/api/demo/fresh-slot", params={"city": STATION_CITY}).json()["slot_id"]
        before = wallet(c, drv)
        step(f"Book Chennai slot #{slot}; both nodes PREPARE, then the coordinator 'dies'")
        g1 = crash_booking(c, drv, car["vehicle_id"], slot, "after_prepare")
        step("State right after the crash (both branches in doubt, locks still held):")
        show_state(c, drv, admin, slot, g1)
        step("Recovery: decision log has NO commit for this transaction -> presumed abort")
        recover(c, admin, g1)
        step("After recovery:")
        show_state(c, drv, admin, slot, g1)
        ok = wallet(c, drv) == before and slot_report(c, slot)["confirmed_bookings"] == 0
        print(f"\n    RESULT: {'both nodes rolled back, nothing half-done' if ok else 'UNEXPECTED STATE'}")

        # ------------------------------------------------------------------ 2
        print(
            "\n"
            + "=" * 78
            + "\n2. Coordinator crashes after logging COMMIT, before telling the nodes\n"
            + "=" * 78
        )
        slot = c.post("/api/demo/fresh-slot", params={"city": STATION_CITY}).json()["slot_id"]
        before = wallet(c, drv)
        step(f"Book Chennai slot #{slot}; both PREPARE, COMMIT is written to the decision log, then crash")
        g2 = crash_booking(c, drv, car["vehicle_id"], slot, "after_decision")
        step("State right after the crash (decided, but no node has committed yet):")
        show_state(c, drv, admin, slot, g2)
        step("Recovery: decision log says COMMIT -> the coordinator's promise is kept")
        recover(c, admin, g2)
        step("After recovery:")
        show_state(c, drv, admin, slot, g2)
        ok = wallet(c, drv) < before and slot_report(c, slot)["confirmed_bookings"] == 1
        print(
            f"\n    RESULT: {'both nodes committed: booking exists AND wallet debited' if ok else 'UNEXPECTED'}"
        )

        # ------------------------------------------------------------------ 3
        if a.node_crash:
            print("\n" + "=" * 78 + "\n3. The Chennai MySQL node itself crashes while prepared\n" + "=" * 78)
            slot = c.post("/api/demo/fresh-slot", params={"city": STATION_CITY}).json()["slot_id"]
            before = wallet(c, drv)
            step(f"Book Chennai slot #{slot}; PREPARE + COMMIT decision logged, then crash")
            g3 = crash_booking(c, drv, car["vehicle_id"], slot, "after_decision")
            show_state(c, drv, admin, slot, g3)
            step(f"Kill the Chennai node: {a.kill_cmd}")
            subprocess.run(a.kill_cmd, shell=True, check=False)
            time.sleep(2)
            print(f"    in doubt now: {in_doubt(c, admin)}")
            step(f"Restart it: {a.start_cmd}")
            subprocess.run(a.start_cmd, shell=True, check=False)
            if not wait_healthy(c, STATION_CITY):
                sys.exit("Chennai node did not come back")
            step("After restart: InnoDB crash recovery KEPT the prepared branch (it is in the redo log)")
            show_state(c, drv, admin, slot, g3)
            step("Recovery: decision log says COMMIT")
            recover(c, admin, g3)
            show_state(c, drv, admin, slot, g3)
            ok = wallet(c, drv) < before and slot_report(c, slot)["confirmed_bookings"] == 1
            print(
                f"\n    RESULT: {'prepared branch survived the node crash and was committed' if ok else 'UNEXPECTED'}"
            )

        print("\nDecision log entries for this run:")
        log = c.get("/api/admin/xa-log", headers=admin).json()
        for g in [g1, g2] + ([g3] if a.node_crash else []):
            print(f"    {g}: {log.get(g, {'decision': '(none) -> presumed abort'})}")


if __name__ == "__main__":
    main()
