"""
Concurrency demo: fire simultaneous booking requests at the API and show
what happens with and without locking.

Needs the API running with DEMO_MODE=true and seed data loaded.

    cd backend
    python demo/concurrency_demo.py                     # both modes, 5 drivers, same slot
    python demo/concurrency_demo.py --mode unsafe       # just the broken version
    python demo/concurrency_demo.py --users 10 --delay 500
    python demo/concurrency_demo.py --scenario wallet   # lost-update demo on one wallet

Scenarios
  slot   : N different drivers book THE SAME slot at the same instant.
           unsafe -> several "confirmed" bookings for one slot (double booking)
           locked -> exactly 1 confirmed, the rest get "Slot already booked"
  wallet : ONE driver books N DIFFERENT slots at the same instant.
           unsafe -> N bookings but the wallet is only charged once (lost update)
           locked -> wallet is charged for every booking
"""

import argparse
import asyncio
import sys
import time

import httpx

PASSWORD = "demo1234"
CITY = "bangalore"


# ------------------------------------------------------------------ helpers


async def ensure_driver(client: httpx.AsyncClient, i: int, min_balance: float) -> dict:
    """Log in (or register) race driver #i and make sure it has money + a CCS2 car."""
    email = f"race{i}@demo.ev"
    r = await client.post("/api/users/login", json={"email": email, "password": PASSWORD})
    if r.status_code == 401:
        r = await client.post(
            "/api/users/register",
            json={"email": email, "password": PASSWORD, "full_name": f"Race Driver {i}", "home_city": CITY},
        )
    r.raise_for_status()
    data = r.json()
    headers = {"Authorization": f"Bearer {data['access_token']}"}
    user = data["user"]

    if user["wallet_balance"] < min_balance:
        await client.post(
            "/api/users/me/wallet/topup",
            headers=headers,
            json={"amount": round(min_balance - user["wallet_balance"] + 1000, 2)},
        )
    vehicles = (await client.get("/api/users/me/vehicles", headers=headers)).json()
    car = next((v for v in vehicles if v["connector_type"] == "CCS2"), None)
    if not car:
        car = (
            await client.post(
                "/api/users/me/vehicles",
                headers=headers,
                json={
                    "make": "Tata",
                    "model": "Nexon EV",
                    "battery_capacity_kwh": 40.5,
                    "connector_type": "CCS2",
                    "registration_number": f"KA99RC{i:04d}",
                },
            )
        ).json()
    return {"i": i, "user_id": user["user_id"], "headers": headers, "vehicle_id": car["vehicle_id"]}


async def wallet(client, drv) -> float:
    return (await client.get("/api/users/me/wallet", headers=drv["headers"])).json()["wallet_balance"]


async def last_seq(client) -> int:
    log = (await client.get("/api/demo/audit-log", params={"limit": 1})).json()
    return log[-1]["seq"] if log else 0


async def fire(client, start: asyncio.Event, drv, slot_id: int, mode: str, delay: int) -> dict:
    await start.wait()  # everyone leaves the starting line together
    t0 = time.perf_counter()
    r = await client.post(
        "/api/demo/book",
        headers=drv["headers"],
        json={
            "city": CITY,
            "slot_id": slot_id,
            "vehicle_id": drv["vehicle_id"],
            "mode": mode,
            "delay_ms": delay,
        },
    )
    body = r.json()
    return {
        "driver": drv["i"],
        "slot_id": slot_id,
        "status": r.status_code,
        "ms": int((time.perf_counter() - t0) * 1000),
        "body": body,
    }


def print_results(results):
    for r in sorted(results, key=lambda x: x["ms"]):
        if r["status"] == 201:
            b = r["body"]
            msg = f"CONFIRMED booking #{b['booking_id']}  Rs {b['booking_amount']}"
        else:
            msg = f"REJECTED  {r['body'].get('code')}: {r['body'].get('detail')}"
        print(f"   driver {r['driver']:>2}  slot {r['slot_id']:>5}  {r['status']}  {r['ms']:>5} ms  {msg}")


async def print_timeline(client, after_seq: int):
    events = (await client.get("/api/demo/audit-log", params={"after_seq": after_seq, "limit": 2000})).json()
    events = [e for e in events if e.get("txn")]
    if not events:
        return
    print("\n   Transaction log (what the database saw, in order):")
    from datetime import datetime

    t_first = datetime.fromisoformat(events[0]["ts"])
    for e in events:
        dt = int((datetime.fromisoformat(e["ts"]) - t_first).total_seconds() * 1000)
        extra = {k: v for k, v in e.items() if k not in ("seq", "ts", "event", "txn", "city", "thread")}
        detail = " ".join(f"{k}={v}" for k, v in extra.items())
        print(f"   +{dt:>5}ms  {e['txn']}  {e['event']:<15} {detail}")


# ------------------------------------------------------------------ scenarios


async def scenario_slot(client, drivers, mode, delay, show_log):
    slot = (await client.post("/api/demo/fresh-slot", params={"city": CITY})).json()
    print(
        f"\n=== {mode.upper()} : {len(drivers)} drivers -> the same slot #{slot['slot_id']} "
        f"({slot['station_name']} {slot['charger_code']}, {slot['slot_date']} {slot['start_time']}) ==="
    )
    seq = await last_seq(client)
    start = asyncio.Event()
    tasks = [asyncio.create_task(fire(client, start, d, slot["slot_id"], mode, delay)) for d in drivers]
    await asyncio.sleep(0.2)
    start.set()
    results = await asyncio.gather(*tasks)
    print_results(results)

    report = (await client.get(f"/api/demo/slot-report/{CITY}/{slot['slot_id']}")).json()
    n = report["confirmed_bookings"]
    if n > 1:
        print(f"\n   RESULT: slot #{slot['slot_id']} has {n} confirmed bookings -> DOUBLE BOOKED")
    else:
        print(f"\n   RESULT: slot #{slot['slot_id']} has {n} confirmed booking -> correct")
    if show_log:
        await print_timeline(client, seq)
    return n


async def scenario_wallet(client, driver, n, mode, delay, show_log):
    slots = [(await client.post("/api/demo/fresh-slot", params={"city": CITY})).json() for _ in range(n)]
    before = await wallet(client, driver)
    print(
        f"\n=== {mode.upper()} : driver {driver['i']} books {n} different slots at once "
        f"(wallet before: Rs {before}) ==="
    )
    seq = await last_seq(client)
    start = asyncio.Event()
    tasks = [asyncio.create_task(fire(client, start, driver, s["slot_id"], mode, delay)) for s in slots]
    await asyncio.sleep(0.2)
    start.set()
    results = await asyncio.gather(*tasks)
    print_results(results)

    after = await wallet(client, driver)
    charged = round(sum(r["body"]["booking_amount"] for r in results if r["status"] == 201), 2)
    actually_debited = round(before - after, 2)
    print(f"\n   Bookings confirmed : {sum(r['status'] == 201 for r in results)}")
    print(f"   Should be debited  : Rs {charged}")
    print(f"   Actually debited   : Rs {actually_debited}")
    if abs(charged - actually_debited) > 0.01:
        print(
            f"   RESULT: LOST UPDATE - Rs {round(charged - actually_debited, 2)} of bookings were never paid for"
        )
    else:
        print("   RESULT: wallet is correct")
    if show_log:
        await print_timeline(client, seq)
    return charged - actually_debited


async def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--api", default="http://localhost:8000")
    p.add_argument("--mode", choices=["unsafe", "locked", "both"], default="both")
    p.add_argument("--scenario", choices=["slot", "wallet"], default="slot")
    p.add_argument("--users", type=int, default=5, help="simultaneous requests (2-20)")
    p.add_argument("--delay", type=int, default=300, help="ms to pause inside each transaction")
    p.add_argument("--no-log", action="store_true", help="hide the transaction log")
    a = p.parse_args()
    a.users = max(2, min(a.users, 20))
    modes = ["unsafe", "locked"] if a.mode == "both" else [a.mode]

    async with httpx.AsyncClient(base_url=a.api, timeout=60) as client:
        try:
            (await client.get("/health")).raise_for_status()
        except Exception:
            sys.exit(f"API not reachable at {a.api}. Start it first.")
        if (await client.get("/api/demo/audit-log", params={"limit": 1})).status_code == 404:
            sys.exit("Demo endpoints are off. Start the API with DEMO_MODE=true.")

        n_drivers = a.users if a.scenario == "slot" else 1
        drivers = await asyncio.gather(
            *[ensure_driver(client, i, 3000 * a.users) for i in range(1, n_drivers + 1)]
        )

        for mode in modes:
            if a.scenario == "slot":
                await scenario_slot(client, drivers, mode, a.delay, not a.no_log)
            else:
                await scenario_wallet(client, drivers[0], a.users, mode, a.delay, not a.no_log)


if __name__ == "__main__":
    asyncio.run(main())
