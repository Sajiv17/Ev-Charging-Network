# Database — Person 1 (Database Architect)

## Your Responsibility

Design and implement the complete MySQL schema and manage all database-level logic.

---

## What You Build

### 📁 `mysql/schema/`
- ✅ **`01_init_schema.sql`** — already created (Users, Stations, Chargers, Bookings, Payments, etc.)
- You can add more schema files if needed (e.g., `02_add_indexes.sql`)

**Tasks:**
- Review and refine the existing schema
- Apply normalization (1NF → BCNF) and document it
- Add composite indexes for query optimization (Module 3)

### 📁 `mysql/triggers/`
- ✅ **`charger_fault_trigger.sql`** — already created (auto-refund on charger fault)
- Add more triggers as needed

**Tasks:**
- Test the existing trigger
- Add trigger for slot auto-release if booking is cancelled
- Add trigger for wallet balance validation before booking

### 📁 `mysql/procedures/`
**Empty — you create these**

**Tasks:**
- `sp_create_booking.sql` — stored procedure for atomic booking (lock slot + debit payment)
- `sp_process_refund.sql` — stored procedure to process queued refunds
- `sp_get_station_load.sql` — get booking load per station for dashboard

### 📁 `mysql/seeds/`
**Empty — you create these**

**Tasks:**
- `01_seed_users.sql` — insert 20-30 sample users (drivers, operators, admin)
- `02_seed_stations.sql` — insert stations in Bangalore, Chennai, Delhi
- `03_seed_chargers.sql` — insert charger units at each station
- `04_seed_vehicles.sql` — insert vehicles linked to users
- `05_seed_pricing.sql` — insert pricing plans per city

---

## Normalization Documentation

Create `docs/NORMALIZATION.md`:
- Show original unnormalized structure
- Apply 1NF, 2NF, 3NF, BCNF step by step
- Explain functional dependencies
- Show the final normalized schema

---

## ER Diagram

Create `docs/ER_DIAGRAM.md`:
- Draw ER diagram (use draw.io, Lucidchart, or dbdiagram.io)
- Export as PNG and embed in the markdown
- Show entities, relationships, cardinalities
- Include weak entities (if any)

---

## Testing Your Work

```bash
# Connect to Bangalore MySQL node
docker exec -it ev-mysql-bangalore mysql -u ev_user -pevcharge_pass_2024 ev_bangalore

# Run your scripts
SOURCE /docker-entrypoint-initdb.d/01_init_schema.sql;
SOURCE /path/to/your/procedure.sql;

# Test a trigger
UPDATE charger_units SET status = 'faulted' WHERE charger_id = 5;
SELECT * FROM refunds ORDER BY created_at DESC LIMIT 5;
```

---

## MongoDB (Not your responsibility — Person 3 handles this)

Skip `mongodb/` folder — Person 3 will build that.

---

## Your Branch

```bash
git checkout -b database-schema
# Make changes
git add database/
git commit -m "feat(database): add stored procedures for booking"
git push origin database-schema
# Open PR to main
```
