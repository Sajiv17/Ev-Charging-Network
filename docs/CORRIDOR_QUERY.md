# Highway Corridor Query

Owner: Person 1 (Database). Tables: `corridors` (catalog), `corridor_stations` (per node).

## What it answers

"I'm driving Bangalore → Chennai on NH-48 with a CCS2 car. Where can I charge, in order along
the road, and how far apart are the stops?"

## Design: relational, not a graph database

A highway corridor is an **ordered list of stations along one road**, keyed by distance from the
origin (`km_marker`). That is a one-dimensional ordering, not an arbitrary graph, so it needs
nothing more than a table and an index:

```
corridors          (corridor_id PK, corridor_name, highway, origin_city_id → cities, destination, length_km)   replicated
corridor_stations  (corridor_id → corridors, station_id → stations, km_marker)  PK (corridor_id, station_id)    fragmented
                   INDEX idx_cs_km (corridor_id, km_marker)
```

A graph database (Neo4j and similar) pays off when the question is **path finding over an
arbitrary network** ("cheapest route between any two towns with charging every 150 km"). For a fixed
named corridor, "stations ordered by km" is a range scan on a B+ tree, and `LAG()` gives the gap
between stops. Adding a fourth datastore for that would cost more than it gives.

## Data placement

- `corridors` is **replicated**: every node knows the corridors exist.
- `corridor_stations` is **fragmented** with the stations it points to. A corridor that crosses
  states has rows on **several nodes**: Bangalore → Chennai stations in Karnataka are on the
  Bangalore node, and those from Hosur onwards (Tamil Nadu) are on the Chennai node. Each row's
  foreign key to `stations` stays local to its node.
- `km_marker` is measured from the corridor's origin along town-to-town waypoints
  (`scripts/db/seed_data.py`). It is consistent across nodes, which is what makes the merge below work.

## The per-node query

Run on **every node** that may hold stations of the corridor:

```sql
SELECT cs.km_marker, s.station_id, s.station_name, s.latitude, s.longitude,
       COUNT(c.charger_id)          AS chargers,
       SUM(c.charger_type = 'DC')   AS dc_chargers,
       MAX(c.max_power_kw)          AS max_power_kw
  FROM corridor_stations cs
  JOIN stations s      ON s.station_id = cs.station_id AND s.is_operational = TRUE
  JOIN charger_units c ON c.station_id = s.station_id
                      AND c.status IN ('available', 'occupied')
                      AND (:conn IS NULL OR c.connector_type = :conn)
 WHERE cs.corridor_id = :corridor_id
 GROUP BY cs.km_marker, s.station_id, s.station_name, s.latitude, s.longitude
 ORDER BY cs.km_marker;
```

`EXPLAIN FORMAT=TREE` (Bangalore node):

```
-> Nested loop inner join
    -> Covering index lookup on cs using idx_cs_km (corridor_id=1)
    -> Single-row covering index lookup on s using PRIMARY (station_id=cs.station_id)
```

The rows come out of `idx_cs_km` already in `km_marker` order, so there is no sort.

## Merging across nodes (the API's job)

Station IDs repeat across nodes, so each result row is tagged with its city and the API keeps
`(city, station_id)` pairs, as it does everywhere else. Each node returns its rows sorted by
`km_marker`, so the coordinator does a **k-way merge by `km_marker`** (or simply concatenates and
sorts; the lists are short):

```python
rows = []
for city in CITIES:                       # or only the nodes whose waypoints the corridor uses
    with city_session(city) as db:
        rows += [{**r, "city": city} for r in db.execute(text(CORRIDOR_SQL), params).mappings()]
rows.sort(key=lambda r: r["km_marker"])
for prev, cur in zip(rows, rows[1:]):
    cur["km_from_previous"] = cur["km_marker"] - prev["km_marker"]   # gap between charging stops
```

Within a single node, the gap can also be computed in SQL with a window function:

```sql
cs.km_marker - LAG(cs.km_marker) OVER (ORDER BY cs.km_marker) AS km_from_previous
```

The gap across a node boundary (last Bangalore-node stop → first Chennai-node stop) only exists after the
merge, which is why the API computes it rather than SQL.

## Seeded corridors

| corridor_id | Corridor | Highway | Origin | length_km (along waypoints) |
|---|---|---|---|---|
| 1 | Bangalore - Mysuru | NH-275 | Bangalore | 124.7 |
| 2 | Bangalore - Chennai | NH-48 | Bangalore | 307.5 |

A station is put on a corridor by `scripts/db/generate_seeds.py` when it is within **4 km** of the
route line and not inside either end city (first and last 8 km). These are ordinary city stations.

**Current data:** the seeds were generated **without** Open Charge Map data (no API key at the time),
so the only corridor station is the backend's demo station *NH-275 Bidadi Highway Stop* (corridor 1,
km 24.4, Bangalore node). Corridor 2 has no stations yet. Running `scripts/db/fetch_stations.py` with
an `OCM_API_KEY` pulls real stations near every waypoint and regenerates the seeds, which fills both
corridors on the Bangalore and Chennai nodes.

Current output on the Bangalore node:

```
km_marker  station_id  station_name                 chargers  dc_chargers  max_power_kw  km_from_previous
24.4       3           NH-275 Bidadi Highway Stop   3         2            60.00         NULL
```
