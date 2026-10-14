# ER Diagram

Owner: Person 1 (Database). Source of truth: `database/mysql/schema/01_catalog.sql` and `02_core.sql`.
A dbdiagram.io version is in [`er_diagram.dbml`](er_diagram.dbml): paste it into
<https://dbdiagram.io/d> and use *Export → PNG* for the report.

## Data placement

Every table exists on all three MySQL nodes (identical schema). What differs is which **rows** a
node holds:

| Placement | Tables | Rows on each node | IDs |
|---|---|---|---|
| **Replicated** | `cities`, `connector_types`, `pricing_plans`, `corridors`, `users`, `vehicles` | all rows | identical everywhere (users/vehicles: Bangalore issues them) |
| **Fragmented** (horizontal, by city) | `stations`, `charger_units`, `slots`, `bookings`, `payments`, `refunds`, `corridor_stations` | only that city's rows | repeat across nodes; the API addresses rows as `(city, id)` |

In the diagram, the first attribute comment of each entity says **REPLICATED** or **FRAGMENTED**.

```mermaid
erDiagram
    cities {
        int city_id PK "REPLICATED"
        varchar city_name UK
        varchar state
        varchar country
    }
    connector_types {
        varchar connector_type PK "REPLICATED: CCS2, CHAdeMO, Type2"
        enum current_type "AC or DC"
        varchar description
    }
    pricing_plans {
        int plan_id PK "REPLICATED"
        int city_id FK
        enum charger_type "AC or DC"
        decimal rate_per_kwh
        decimal booking_fee
        date effective_from "UK with city_id, charger_type"
        date effective_to
    }
    corridors {
        int corridor_id PK "REPLICATED"
        varchar corridor_name UK
        varchar highway
        int origin_city_id FK
        varchar destination
        decimal length_km
    }
    users {
        int user_id PK "REPLICATED: same id on every node"
        varchar email UK
        varchar password_hash
        varchar full_name
        enum role "driver, operator, admin"
        decimal wallet_balance "authoritative only on home node; CHECK >= 0"
        int home_city_id FK
        boolean is_active
    }
    vehicles {
        int vehicle_id PK "REPLICATED: same id on every node"
        int user_id FK
        varchar make
        varchar model
        decimal battery_capacity_kwh
        varchar connector_type FK
        varchar registration_number UK
    }
    stations {
        int station_id PK "FRAGMENTED by city_id"
        varchar station_name
        int city_id FK
        text address
        decimal latitude
        decimal longitude
        int operator_id FK
        boolean is_operational
    }
    charger_units {
        int charger_id PK "FRAGMENTED"
        int station_id FK "UK with charger_code"
        varchar charger_code
        enum charger_type "denormalized; trigger-checked against connector"
        decimal max_power_kw
        varchar connector_type FK
        enum status "available, occupied, faulted, maintenance"
    }
    slots {
        int slot_id PK "FRAGMENTED"
        int charger_id FK "UK with slot_date, slot_start_time"
        date slot_date
        time slot_start_time
        time slot_end_time "CHECK > start; no overlap (trigger)"
        boolean is_available "controlled redundancy"
    }
    bookings {
        int booking_id PK "FRAGMENTED"
        int user_id FK
        int slot_id FK
        int vehicle_id FK
        enum booking_status "confirmed, active, completed, cancelled"
        decimal booking_amount "prepaid estimate"
        decimal energy_consumed_kwh
        datetime session_start_time
        datetime session_end_time
    }
    payments {
        int payment_id PK "FRAGMENTED"
        int booking_id FK
        decimal amount
        enum payment_method
        enum payment_status "pending, completed, failed, refunded"
        varchar transaction_id UK
    }
    refunds {
        int refund_id PK "FRAGMENTED"
        int payment_id FK
        decimal refund_amount
        text refund_reason
        enum refund_status "queued, processing, completed, failed"
        timestamp processed_at
    }
    corridor_stations {
        int corridor_id PK, FK "FRAGMENTED"
        int station_id PK, FK
        decimal km_marker
    }

    cities ||--o{ pricing_plans : "prices"
    cities ||--o{ users : "is home node of"
    cities ||--o{ stations : "contains"
    cities ||--o{ corridors : "is origin of"
    connector_types ||--o{ charger_units : "plug of"
    connector_types ||--o{ vehicles : "inlet of"
    users ||--o{ vehicles : "owns"
    users ||--o{ stations : "operates"
    users ||--o{ bookings : "makes"
    stations ||--o{ charger_units : "has"
    charger_units ||--o{ slots : "offers"
    slots ||--o{ bookings : "is booked by"
    vehicles ||--o{ bookings : "is charged in"
    bookings ||--o{ payments : "is paid by"
    payments ||--o{ refunds : "is refunded by"
    corridors ||--o{ corridor_stations : "lists"
    stations ||--o{ corridor_stations : "lies on"
```

## Notes for the viva

- **Cardinalities.** One station has many chargers, one charger many slots. A slot has **at most
  one live booking** (enforced by 2PL in the backend, optionally by
  `optional/double_booking_guard.sql`), but any number of cancelled ones, hence `||--o{`.
  One booking has one payment today. The model allows several payments and several refunds per
  payment, for phase-2 settlement.
- **Weak-entity flavour.** A slot has no meaning without its charger, and its natural key
  `(charger_id, slot_date, slot_start_time)` includes the owner's key. We give it a surrogate
  `slot_id` because bookings reference it and the 2PL transaction locks it by primary key.
  `corridor_stations` is an associative entity (M:N between corridors and stations, with the
  attribute `km_marker`).
- **Cross-node references.** Every foreign key stays inside one node. Fragmented tables only
  reference replicated tables (users, vehicles, catalog) or other fragmented rows of the same
  city, so no foreign key ever crosses nodes.
- **Delete rules.** `bookings`, `payments` and `refunds` are never removed by a cascade: every FK
  into or out of them is `RESTRICT`. Cascades exist only for structural data with no money
  attached (station → chargers → slots, user → vehicles, corridor membership), and they stop at
  the first booking.
