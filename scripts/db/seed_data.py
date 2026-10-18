"""
Static inputs for generate_seeds.py: cities, pricing, users, vehicles, the
backend's demo stations and the corridor routes.

Nothing here pretends to be real-world station data. Real stations come only
from Open Charge Map via fetch_stations.py (raw JSON in scripts/db/raw/).
"""

CITIES = {  # key -> (city_id, name); ids match backend/app/core/cities.py
    "bangalore": (1, "Bangalore"),
    "chennai": (2, "Chennai"),
    "delhi": (3, "Delhi"),
}

# Same values and the same plan_id order as PRICING in the backend's
# scripts/seed_demo_data.py (plan_id 1..6), so its prices stay valid.
PRICING = {  # city: {charger_type: (rate_per_kwh, booking_fee)}
    "bangalore": {"AC": ("14.00", "20.00"), "DC": ("21.00", "30.00")},
    "chennai": {"AC": ("13.00", "20.00"), "DC": ("20.00", "30.00")},
    "delhi": {"AC": ("12.50", "15.00"), "DC": ("19.50", "25.00")},
}
PRICING_EFFECTIVE_FROM = "2026-01-01"

PASSWORD = "demo1234"

# Demo accounts exactly as the backend's seed script creates them, in the same
# order, so the IDs also match a database seeded by that script.
DEMO_USERS = [
    # (email, full_name, home_city, role, wallet)
    ("admin@demo.ev", "Network Admin", "bangalore", "admin", "0.00"),
    ("operator.bangalore@demo.ev", "Bangalore Operator", "bangalore", "operator", "0.00"),
    ("operator.chennai@demo.ev", "Chennai Operator", "chennai", "operator", "0.00"),
    ("operator.delhi@demo.ev", "Delhi Operator", "delhi", "operator", "0.00"),
    ("driver.bangalore@demo.ev", "Demo Driver Bangalore", "bangalore", "driver", "5000.00"),
    ("driver.chennai@demo.ev", "Demo Driver Chennai", "chennai", "driver", "5000.00"),
    ("driver.delhi@demo.ev", "Demo Driver Delhi", "delhi", "driver", "5000.00"),
]

# DEMO_VEHICLES from the backend seed script (one per demo driver).
DEMO_VEHICLES = {
    "driver.bangalore@demo.ev": ("Tata", "Nexon EV", "40.50", "CCS2", "KA01EV1001"),
    "driver.chennai@demo.ev": ("MG", "ZS EV", "50.30", "CCS2", "TN09EV2002"),
    "driver.delhi@demo.ev": ("Hyundai", "Kona Electric", "39.20", "CCS2", "DL3CEV3003"),
}

# Synthetic drivers (clearly fictitious: example.com addresses, no phone numbers).
FIRST_NAMES = [
    "Aarav", "Ananya", "Vihaan", "Diya", "Arjun", "Ishita", "Kabir", "Meera", "Rohan", "Saanvi",
    "Aditya", "Priya", "Karthik", "Lakshmi", "Nikhil", "Divya", "Rahul", "Sneha", "Varun", "Pooja",
    "Siddharth", "Kavya", "Manish",
]
LAST_NAMES = [
    "Sharma", "Iyer", "Reddy", "Nair", "Gupta", "Rao", "Menon", "Singh", "Kumar", "Pillai",
    "Verma", "Krishnan", "Joshi", "Subramanian", "Mehta", "Chatterjee", "Bhat", "Malhotra",
]
EXTRA_DRIVERS_PER_CITY = {"bangalore": 8, "chennai": 8, "delhi": 7}  # 7 demo + 23 = 30 users

# Popular EVs sold in India: (make, model, battery kWh, connector). Weighted
# towards CCS2 like the market; a few Type2-only and CHAdeMO cars give variety.
EV_MODELS = [
    ("Tata", "Nexon EV", "40.50", "CCS2"),
    ("Tata", "Tigor EV", "26.00", "CCS2"),
    ("Tata", "Punch EV", "35.00", "CCS2"),
    ("MG", "ZS EV", "50.30", "CCS2"),
    ("Hyundai", "Kona Electric", "39.20", "CCS2"),
    ("Hyundai", "Ioniq 5", "72.60", "CCS2"),
    ("Mahindra", "XUV400", "39.40", "CCS2"),
    ("BYD", "Atto 3", "60.48", "CCS2"),
    ("Kia", "EV6", "77.40", "CCS2"),
    ("Citroen", "eC3", "29.20", "CCS2"),
    ("MG", "Comet EV", "17.30", "Type2"),
    ("Nissan", "Leaf", "40.00", "CHAdeMO"),
]
REG_PREFIX = {"bangalore": ["KA01", "KA03", "KA05", "KA51"], "chennai": ["TN01", "TN09", "TN10", "TN22"],
              "delhi": ["DL1C", "DL3C", "DL4C", "DL8C"]}

# The backend's demo stations, verbatim from STATIONS in scripts/seed_demo_data.py.
# They come first on each node so they keep station_id 1-3 and the same
# charger_ids (concurrency_demo picks "the first CCS2 charger in Bangalore").
# (name, address, lat, lon, [(code, type, kW, connector), ...])
DEMO_STATIONS = {
    "bangalore": [
        ("Koramangala EV Hub", "80 Feet Rd, Koramangala 4th Block", 12.93520, 77.62450,
         [("CHG-01", "DC", 60, "CCS2"), ("CHG-02", "DC", 60, "CCS2"), ("CHG-03", "AC", 7.4, "Type2"),
          ("CHG-04", "DC", 50, "CHAdeMO")]),
        ("Whitefield Tech Park Charging", "ITPL Main Rd, Whitefield", 12.98710, 77.73770,
         [("CHG-01", "DC", 120, "CCS2"), ("CHG-02", "AC", 22, "Type2"), ("CHG-03", "AC", 7.4, "Type2")]),
        ("NH-275 Bidadi Highway Stop", "Mysore Rd, Bidadi", 12.79720, 77.38730,
         [("CHG-01", "DC", 60, "CCS2"), ("CHG-02", "DC", 30, "CCS2"), ("CHG-03", "AC", 7.4, "Type2")]),
    ],
    "chennai": [
        ("T Nagar Power Point", "Usman Rd, T Nagar", 13.04180, 80.23410,
         [("CHG-01", "DC", 60, "CCS2"), ("CHG-02", "AC", 7.4, "Type2"), ("CHG-03", "DC", 50, "CHAdeMO")]),
        ("OMR Sholinganallur Charge Bay", "Rajiv Gandhi Salai, Sholinganallur", 12.90100, 80.22790,
         [("CHG-01", "DC", 120, "CCS2"), ("CHG-02", "DC", 60, "CCS2"), ("CHG-03", "AC", 22, "Type2")]),
        ("ECR Mahabalipuram Stop", "East Coast Rd, Kovalam", 12.78860, 80.25000,
         [("CHG-01", "DC", 60, "CCS2"), ("CHG-02", "AC", 7.4, "Type2"), ("CHG-03", "AC", 7.4, "Type2")]),
    ],
    "delhi": [
        ("Connaught Place EV Station", "Outer Circle, Connaught Place", 28.63150, 77.21670,
         [("CHG-01", "DC", 60, "CCS2"), ("CHG-02", "DC", 60, "CCS2"), ("CHG-03", "AC", 7.4, "Type2"),
          ("CHG-04", "DC", 50, "CHAdeMO")]),
        ("Saket Mall Charging", "Press Enclave Marg, Saket", 28.52870, 77.21960,
         [("CHG-01", "DC", 120, "CCS2"), ("CHG-02", "AC", 22, "Type2"), ("CHG-03", "AC", 7.4, "Type2")]),
        ("NH-48 Gurugram Toll Plaza Stop", "NH-48, Sirhaul", 28.49650, 77.08900,
         [("CHG-01", "DC", 60, "CCS2"), ("CHG-02", "DC", 30, "CCS2"), ("CHG-03", "AC", 7.4, "Type2")]),
    ],
}

# City-centre search areas for Open Charge Map: (lat, lon, radius_km)
CITY_AREAS = {
    "bangalore": (12.9716, 77.5946, 25),
    "chennai": (13.0827, 80.2707, 25),
    "delhi": (28.6139, 77.2090, 25),
}

# Corridors as town-to-town waypoints along the highway. Each waypoint carries
# the node that owns stations near it (by state: Karnataka -> Bangalore node,
# Tamil Nadu -> Chennai node). km markers are measured along these straight
# segments, so they approximate road distance from the origin.
CORRIDORS = [
    {
        "corridor_id": 1,
        "name": "Bangalore - Mysuru (NH-275)",
        "highway": "NH-275",
        "origin": "bangalore",
        "destination": "Mysuru",
        "waypoints": [
            ("Bengaluru, Mysore Rd", 12.9531, 77.5434, "bangalore"),
            ("Kengeri", 12.9081, 77.4826, "bangalore"),
            ("Bidadi", 12.7967, 77.3829, "bangalore"),
            ("Ramanagara", 12.7157, 77.2812, "bangalore"),
            ("Channapatna", 12.6514, 77.2067, "bangalore"),
            ("Maddur", 12.5847, 77.0451, "bangalore"),
            ("Mandya", 12.5223, 76.8970, "bangalore"),
            ("Srirangapatna", 12.4216, 76.6932, "bangalore"),
            ("Mysuru", 12.3051, 76.6551, "bangalore"),
        ],
    },
    {
        "corridor_id": 2,
        "name": "Bangalore - Chennai (NH-48)",
        "highway": "NH-48",
        "origin": "bangalore",
        "destination": "Chennai",
        "waypoints": [
            ("Bengaluru, Silk Board", 12.9172, 77.6229, "bangalore"),
            ("Electronic City", 12.8456, 77.6603, "bangalore"),
            ("Hosur", 12.7409, 77.8253, "chennai"),
            ("Shoolagiri", 12.6676, 78.0127, "chennai"),
            ("Krishnagiri", 12.5266, 78.2141, "chennai"),
            ("Vaniyambadi", 12.6819, 78.6201, "chennai"),
            ("Ambur", 12.7916, 78.7166, "chennai"),
            ("Vellore", 12.9165, 79.1325, "chennai"),
            ("Walajapet", 12.9250, 79.3667, "chennai"),
            ("Sriperumbudur", 12.9673, 79.9461, "chennai"),
            ("Poonamallee", 13.0475, 80.0945, "chennai"),
            ("Chennai, Koyambedu", 13.0694, 80.1948, "chennai"),
        ],
    },
]
# A station is on a corridor if it is within this distance of the route line...
CORRIDOR_MAX_OFFSET_KM = 4.0
# ...and not inside either end city (those are ordinary city stations).
CORRIDOR_END_MARGIN_KM = 8.0
