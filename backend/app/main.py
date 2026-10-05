from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="EV Charging Network API",
    description="Backend API for multi-city EV charging slot booking system",
    version="1.0.0",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # React frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    return {
        "message": "EV Charging Network API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health")
def health_check():
    return {"status": "healthy"}


# TODO: Import and include routers
# from app.api import users, stations, bookings, payments
# app.include_router(users.router, prefix="/api/users", tags=["users"])
# app.include_router(stations.router, prefix="/api/stations", tags=["stations"])
# app.include_router(bookings.router, prefix="/api/bookings", tags=["bookings"])
# app.include_router(payments.router, prefix="/api/payments", tags=["payments"])
