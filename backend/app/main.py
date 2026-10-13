import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.api import bookings, stations, users
from app.core.config import settings
from app.db.mysql_connection import ENGINES
from app.services.errors import AppError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")

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


# ----------------------------------------------------------------- error handling
# Every error the frontend sees has the shape {"detail": "...", "code": "..."}


@app.exception_handler(AppError)
def _app_error(_req: Request, exc: AppError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message, "code": exc.code})


@app.exception_handler(ValueError)
def _value_error(_req: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(exc), "code": "bad_request"})


@app.exception_handler(OperationalError)
def _db_down(_req: Request, exc: OperationalError):
    log.error("database error: %s", exc.orig if hasattr(exc, "orig") else exc)
    return JSONResponse(
        status_code=503, content={"detail": "A city database node is unavailable", "code": "node_unavailable"}
    )


# ----------------------------------------------------------------- routes


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
    """Overall status + per-node status (used by the admin panel's node health view)."""
    nodes = {}
    for city, engine in ENGINES.items():
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            nodes[city] = "up"
        except Exception:
            nodes[city] = "down"
    return {
        "status": "healthy" if all(v == "up" for v in nodes.values()) else "degraded",
        "mysql_nodes": nodes,
    }


app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(stations.router, prefix="/api/stations", tags=["stations"])
app.include_router(bookings.router, prefix="/api/bookings", tags=["bookings"])

if settings.DEMO_MODE:
    from app.api import demo

    app.include_router(demo.router, prefix="/api/demo", tags=["demo"])


@app.on_event("startup")
def _check_schema():
    """Warn loudly if the database is missing the columns this backend needs."""
    for city, engine in ENGINES.items():
        try:
            with engine.connect() as conn:
                has_col = conn.execute(
                    text(
                        "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = DATABASE() "
                        "AND table_name = 'users' AND column_name = 'home_city_id'"
                    )
                ).scalar()
            if not has_col:
                log.error(
                    "[%s] users.home_city_id is missing - run "
                    "database/mysql/schema/02_backend_additions.sql",
                    city,
                )
        except Exception as exc:
            log.warning("[%s] node not reachable at startup: %s", city, exc.__class__.__name__)
