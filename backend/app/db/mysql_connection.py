from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker

from app.core.cities import normalize_city
from app.core.config import settings


def _make_engine(url: str):
    engine = create_engine(
        url,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        echo=settings.SQL_ECHO,  # set SQL_ECHO=true to print every SQL statement
    )

    @event.listens_for(engine, "connect")
    def _set_session_timezone(dbapi_conn, _record):
        # Slot dates/times are local (IST). Making NOW() IST too means
        # "is this slot in the past?" checks are correct inside Docker (UTC).
        cur = dbapi_conn.cursor()
        cur.execute(f"SET time_zone = '{settings.DB_TIME_ZONE}'")
        cur.close()

    return engine


# Create engines for each city node
engine_bangalore = _make_engine(settings.mysql_bangalore_url)
engine_chennai = _make_engine(settings.mysql_chennai_url)
engine_delhi = _make_engine(settings.mysql_delhi_url)

# Session factories for each city
SessionBangalore = sessionmaker(autocommit=False, autoflush=False, bind=engine_bangalore)
SessionChennai = sessionmaker(autocommit=False, autoflush=False, bind=engine_chennai)
SessionDelhi = sessionmaker(autocommit=False, autoflush=False, bind=engine_delhi)

ENGINES = {
    "bangalore": engine_bangalore,
    "chennai": engine_chennai,
    "delhi": engine_delhi,
}

SESSION_FACTORIES = {
    "bangalore": SessionBangalore,
    "chennai": SessionChennai,
    "delhi": SessionDelhi,
}

# Base class for SQLAlchemy models
Base = declarative_base()


def get_db_bangalore():
    """Dependency for Bangalore DB session"""
    db = SessionBangalore()
    try:
        yield db
    finally:
        db.close()


def get_db_chennai():
    """Dependency for Chennai DB session"""
    db = SessionChennai()
    try:
        yield db
    finally:
        db.close()


def get_db_delhi():
    """Dependency for Delhi DB session"""
    db = SessionDelhi()
    try:
        yield db
    finally:
        db.close()


def get_city_session(city: str) -> Session:
    """Return a new session for a city node. Caller must close it."""
    return SESSION_FACTORIES[normalize_city(city)]()


@contextmanager
def city_session(city: str):
    """`with city_session("chennai") as db:` - always closes the session."""
    db = get_city_session(city)
    try:
        yield db
    finally:
        db.close()
