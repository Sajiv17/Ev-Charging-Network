# Backend — Person 2 (Backend + Transactions)

## Your Responsibility

Build the FastAPI backend with all REST endpoints and implement concurrency control (2PL, deadlock handling).

---

## What You Build

### 📁 `app/api/`
**Empty — you create these**

Create one router file per resource:

**Tasks:**
- `users.py` — user registration, login, wallet management
- `stations.py` — search stations by city/location, get station details
- `bookings.py` — **MOST IMPORTANT** — create booking with 2PL, get user bookings, cancel booking
- `payments.py` — process payment, get payment history, refund status
- `chargers.py` — get charger status (read from MongoDB via Person 3's code)

**Example structure for `bookings.py`:**
```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.mysql_connection import get_city_session
from app.services.booking_service import create_booking_with_lock

router = APIRouter()

@router.post("/bookings")
def create_booking(user_id: int, slot_id: int, city: str):
    db = get_city_session(city)
    try:
        booking = create_booking_with_lock(db, user_id, slot_id)
        return {"booking_id": booking.booking_id, "status": "confirmed"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
```

### 📁 `app/models/`
**Empty — you create these**

SQLAlchemy models for each table:

**Tasks:**
- `user.py` — User model
- `station.py` — Station, ChargerUnit models
- `booking.py` — Booking, Slot models
- `payment.py` — Payment, Refund models
- `vehicle.py` — Vehicle model

**Example `user.py`:**
```python
from sqlalchemy import Column, Integer, String, DECIMAL, Boolean, TIMESTAMP
from app.db.mysql_connection import Base

class User(Base):
    __tablename__ = "users"
    
    user_id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    wallet_balance = Column(DECIMAL(10, 2), default=0.00)
    # ... rest of fields
```

### 📁 `app/schemas/`
**Empty — you create these**

Pydantic schemas for request/response validation:

**Tasks:**
- `user_schema.py` — UserCreate, UserResponse
- `booking_schema.py` — BookingCreate, BookingResponse
- `payment_schema.py` — PaymentCreate, PaymentResponse

**Example:**
```python
from pydantic import BaseModel

class BookingCreate(BaseModel):
    user_id: int
    slot_id: int
    vehicle_id: int
    
class BookingResponse(BaseModel):
    booking_id: int
    booking_status: str
    booking_amount: float
```

### 📁 `app/services/`
**Empty — you create these**

**MOST IMPORTANT** — Business logic with concurrency control:

**Tasks:**
- `booking_service.py` — **create_booking_with_lock()** function that:
  1. Starts transaction
  2. Acquires **row-level lock** on slot (`SELECT ... FOR UPDATE`)
  3. Checks if slot is available
  4. Debits wallet
  5. Creates booking record
  6. Commits or rolls back
  
**Concurrency demo code** — this is your key deliverable:

```python
from sqlalchemy.orm import Session
from sqlalchemy import text

def create_booking_with_lock(db: Session, user_id: int, slot_id: int):
    try:
        db.begin()  # Start transaction
        
        # LOCK THE SLOT ROW (2-Phase Locking)
        slot = db.execute(
            text("SELECT * FROM slots WHERE slot_id = :slot_id FOR UPDATE"),
            {"slot_id": slot_id}
        ).fetchone()
        
        if not slot or not slot.is_available:
            raise Exception("Slot not available")
        
        # Debit payment (simplified)
        db.execute(
            text("UPDATE users SET wallet_balance = wallet_balance - 100 WHERE user_id = :user_id"),
            {"user_id": user_id}
        )
        
        # Create booking
        result = db.execute(
            text("INSERT INTO bookings (user_id, slot_id, booking_status, booking_amount) VALUES (:user_id, :slot_id, 'confirmed', 100)"),
            {"user_id": user_id, "slot_id": slot_id}
        )
        
        # Mark slot as booked
        db.execute(
            text("UPDATE slots SET is_available = 0 WHERE slot_id = :slot_id"),
            {"slot_id": slot_id}
        )
        
        db.commit()
        return {"booking_id": result.lastrowid}
    
    except Exception as e:
        db.rollback()
        raise e
```

---

## Concurrency Demo

Create `docs/CONCURRENCY.md`:
- Explain the lost-update problem
- Show your 2PL implementation
- Provide curl commands to fire two simultaneous requests
- Screenshot of transaction logs showing lock acquisition

---

## Recovery Demo

Create `docs/RECOVERY_DEMO.md`:
- Explain deferred update recovery
- Show how to simulate node crash mid-transaction
- Show WAL inspection after recovery

---

## Testing Your Work

```bash
# Start backend
docker-compose up backend

# Test booking endpoint
curl -X POST http://localhost:8000/api/bookings \
  -H "Content-Type: application/json" \
  -d '{"user_id": 1, "slot_id": 42, "vehicle_id": 1}'

# Fire two simultaneous bookings (concurrency test)
curl -X POST http://localhost:8000/api/bookings -d '{"user_id":1,"slot_id":42,"vehicle_id":1}' & \
curl -X POST http://localhost:8000/api/bookings -d '{"user_id":2,"slot_id":42,"vehicle_id":2}' &
```

---

## Your Branch

```bash
git checkout -b backend-api
# Make changes
git add backend/
git commit -m "feat(backend): add booking endpoint with 2PL"
git push origin backend-api
# Open PR to main
```

---

## What You DON'T Touch

- ❌ `database/` — Person 1's territory
- ❌ `frontend/` — Person 4's territory
- ❌ `app/db/mongodb_connection.py` — Person 3 may extend this, coordinate with them
