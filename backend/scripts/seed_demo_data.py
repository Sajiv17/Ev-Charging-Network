"""
Seed demo data into all 3 city nodes.

TEMPORARY: lets the backend be tested before Person 1's seed files exist.
Once database/mysql/seeds/ is ready, prefer that.

Run from the backend/ folder:
    python -m scripts.seed_demo_data                # local
    docker exec ev-backend python -m scripts.seed_demo_data   # in Docker

Safe to run twice: skips anything that already exists.

Creates
  - pricing plans for every city x {AC, DC}            (replicated to all nodes)
  - 1 operator per city + 1 admin                      (replicated users)
  - 3 stations per city, 3-4 chargers each             (only on that city's node)
  - 1-hour slots 06:00-22:00 for the next 7 days
  - 1 demo driver per city with Rs 5000 and a vehicle
    login: driver.<city>@demo.ev / demo1234
"""

from datetime import date, datetime, time, timedelta

from sqlalchemy import text

from app.core.cities import CITIES, city_id_of
from app.db.mysql_connection import city_session
from app.services import user_service
from app.services.errors import Conflict

PASSWORD = "demo1234"

PRICING = {  # city: {charger_type: (rate_per_kwh, booking_fee)}
    "bangalore": {"AC": (14.00, 20.00), "DC": (21.00, 30.00)},
    "chennai": {"AC": (13.00, 20.00), "DC": (20.00, 30.00)},
    "delhi": {"AC": (12.50, 15.00), "DC": (19.50, 25.00)},
}

# (name, address, lat, lon, [(code, type, kW, connector), ...])
STATIONS = {
    "bangalore": [
        (
            "Koramangala EV Hub",
            "80 Feet Rd, Koramangala 4th Block",
            12.93520,
            77.62450,
            [
                ("CHG-01", "DC", 60, "CCS2"),
                ("CHG-02", "DC", 60, "CCS2"),
                ("CHG-03", "AC", 7.4, "Type2"),
                ("CHG-04", "DC", 50, "CHAdeMO"),
            ],
        ),
        (
            "Whitefield Tech Park Charging",
            "ITPL Main Rd, Whitefield",
            12.98710,
            77.73770,
            [("CHG-01", "DC", 120, "CCS2"), ("CHG-02", "AC", 22, "Type2"), ("CHG-03", "AC", 7.4, "Type2")],
        ),
        (
            "NH-275 Bidadi Highway Stop",
            "Mysore Rd, Bidadi",
            12.79720,
            77.38730,
            [("CHG-01", "DC", 60, "CCS2"), ("CHG-02", "DC", 30, "CCS2"), ("CHG-03", "AC", 7.4, "Type2")],
        ),
    ],
    "chennai": [
        (
            "T Nagar Power Point",
            "Usman Rd, T Nagar",
            13.04180,
            80.23410,
            [("CHG-01", "DC", 60, "CCS2"), ("CHG-02", "AC", 7.4, "Type2"), ("CHG-03", "DC", 50, "CHAdeMO")],
        ),
        (
            "OMR Sholinganallur Charge Bay",
            "Rajiv Gandhi Salai, Sholinganallur",
            12.90100,
            80.22790,
            [("CHG-01", "DC", 120, "CCS2"), ("CHG-02", "DC", 60, "CCS2"), ("CHG-03", "AC", 22, "Type2")],
        ),
        (
            "ECR Mahabalipuram Stop",
            "East Coast Rd, Kovalam",
            12.78860,
            80.25000,
            [("CHG-01", "DC", 60, "CCS2"), ("CHG-02", "AC", 7.4, "Type2"), ("CHG-03", "AC", 7.4, "Type2")],
        ),
    ],
    "delhi": [
        (
            "Connaught Place EV Station",
            "Outer Circle, Connaught Place",
            28.63150,
            77.21670,
            [
                ("CHG-01", "DC", 60, "CCS2"),
                ("CHG-02", "DC", 60, "CCS2"),
                ("CHG-03", "AC", 7.4, "Type2"),
                ("CHG-04", "DC", 50, "CHAdeMO"),
            ],
        ),
        (
            "Saket Mall Charging",
            "Press Enclave Marg, Saket",
            28.52870,
            77.21960,
            [("CHG-01", "DC", 120, "CCS2"), ("CHG-02", "AC", 22, "Type2"), ("CHG-03", "AC", 7.4, "Type2")],
        ),
        (
            "NH-48 Gurugram Toll Plaza Stop",
            "NH-48, Sirhaul",
            28.49650,
            77.08900,
            [("CHG-01", "DC", 60, "CCS2"), ("CHG-02", "DC", 30, "CCS2"), ("CHG-03", "AC", 7.4, "Type2")],
        ),
    ],
}

DEMO_VEHICLES = {
    "bangalore": dict(
        make="Tata",
        model="Nexon EV",
        battery_capacity_kwh=40.5,
        connector_type="CCS2",
        registration_number="KA01EV1001",
    ),
    "chennai": dict(
        make="MG",
        model="ZS EV",
        battery_capacity_kwh=50.3,
        connector_type="CCS2",
        registration_number="TN09EV2002",
    ),
    "delhi": dict(
        make="Hyundai",
        model="Kona Electric",
        battery_capacity_kwh=39.2,
        connector_type="CCS2",
        registration_number="DL3CEV3003",
    ),
}

SLOT_DAYS = 7
SLOT_FIRST_HOUR, SLOT_LAST_HOUR = 6, 22


def get_or_create_user(email, full_name, home_city, role="driver"):
    try:
        u = user_service.register_user(email, PASSWORD, full_name, None, home_city, role)
        print(f"  + user {email} (id {u['user_id']})")
        return u, True
    except Conflict:
        u = user_service.authenticate(email, PASSWORD)
        print(f"  = user {email} exists (id {u['user_id']})")
        return u, False


def seed_pricing():
    """Replicated catalog: identical rows (same plan_id) on every node."""
    for city in CITIES:
        with city_session(city) as db:
            if db.execute(text("SELECT COUNT(*) FROM pricing_plans")).scalar():
                print(f"  = pricing already on {city} node")
                continue
            plan_id = 0
            for plan_city, plans in PRICING.items():
                for ctype, (rate, fee) in plans.items():
                    plan_id += 1
                    db.execute(
                        text(
                            "INSERT INTO pricing_plans (plan_id, city_id, charger_type, rate_per_kwh, "
                            "booking_fee, effective_from) VALUES (:id, :c, :t, :r, :f, '2026-01-01')"
                        ),
                        {"id": plan_id, "c": city_id_of(plan_city), "t": ctype, "r": rate, "f": fee},
                    )
            db.commit()
            print(f"  + {plan_id} pricing plans on {city} node")


def seed_city(city, operator_id):
    """Fragmented data: only goes to this city's node."""
    with city_session(city) as db:
        if db.execute(text("SELECT COUNT(*) FROM stations")).scalar():
            print(f"  = stations already on {city} node")
            return
        today = date.today()
        n_slots = 0
        for name, addr, lat, lon, chargers in STATIONS[city]:
            sid = db.execute(
                text(
                    "INSERT INTO stations (station_name, city_id, address, latitude, longitude, operator_id) "
                    "VALUES (:n, :c, :a, :lat, :lon, :op)"
                ),
                {"n": name, "c": city_id_of(city), "a": addr, "lat": lat, "lon": lon, "op": operator_id},
            ).lastrowid
            for code, ctype, kw, conn in chargers:
                cid = db.execute(
                    text(
                        "INSERT INTO charger_units (station_id, charger_code, charger_type, max_power_kw, "
                        "connector_type) VALUES (:s, :code, :t, :kw, :conn)"
                    ),
                    {"s": sid, "code": code, "t": ctype, "kw": kw, "conn": conn},
                ).lastrowid
                rows = []
                for d in range(SLOT_DAYS):
                    day = today + timedelta(days=d)
                    for h in range(SLOT_FIRST_HOUR, SLOT_LAST_HOUR):
                        rows.append({"c": cid, "d": day, "s": time(h), "e": time(h + 1)})
                db.execute(
                    text(
                        "INSERT INTO slots (charger_id, slot_date, slot_start_time, slot_end_time) "
                        "VALUES (:c, :d, :s, :e)"
                    ),
                    rows,
                )
                n_slots += len(rows)
        db.commit()
        print(f"  + {len(STATIONS[city])} stations, {n_slots} slots on {city} node")


def main():
    started = datetime.now()
    print("Pricing plans")
    seed_pricing()

    print("Users")
    get_or_create_user("admin@demo.ev", "Network Admin", "bangalore", role="admin")
    operators = {}
    for city in CITIES:
        op, _ = get_or_create_user(f"operator.{city}@demo.ev", f"{city.title()} Operator", city, "operator")
        operators[city] = op["user_id"]

    print("Stations, chargers, slots")
    for city in CITIES:
        seed_city(city, operators[city])

    print("Demo drivers")
    for city in CITIES:
        drv, created = get_or_create_user(f"driver.{city}@demo.ev", f"Demo Driver {city.title()}", city)
        if created:
            user_service.top_up_wallet(drv["user_id"], city, 5000)
            user_service.add_vehicle(drv["user_id"], DEMO_VEHICLES[city])

    print(
        f"Done in {(datetime.now() - started).total_seconds():.1f}s. "
        f"Log in as driver.<city>@demo.ev / {PASSWORD}"
    )


if __name__ == "__main__":
    main()
