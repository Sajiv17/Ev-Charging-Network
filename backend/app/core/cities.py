"""
City registry: the single place that knows which cities (= MySQL nodes) exist.

city_id values match the order of the INSERT INTO cities in
database/mysql/schema/01_init_schema.sql (Bangalore=1, Chennai=2, Delhi=3).
"""

CITIES = {
    "bangalore": {"city_id": 1, "name": "Bangalore"},
    "chennai": {"city_id": 2, "name": "Chennai"},
    "delhi": {"city_id": 3, "name": "Delhi"},
}

CITY_BY_ID = {v["city_id"]: key for key, v in CITIES.items()}

# Users and vehicles are replicated to every node. To keep their IDs identical
# on all nodes, exactly one node hands out new IDs; the others copy them.
ID_AUTHORITY_CITY = "bangalore"


def normalize_city(city: str) -> str:
    """'Bangalore', ' BANGALORE ' -> 'bangalore'. Raises ValueError if unknown."""
    key = (city or "").strip().lower()
    if key == "bengaluru":
        key = "bangalore"
    if key not in CITIES:
        raise ValueError(f"Unknown city '{city}'. Use one of: {', '.join(CITIES)}")
    return key


def city_id_of(city: str) -> int:
    return CITIES[normalize_city(city)]["city_id"]


def city_key_of(city_id: int) -> str:
    return CITY_BY_ID[city_id]
