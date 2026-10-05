from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# Create engines for each city node
engine_bangalore = create_engine(
    settings.mysql_bangalore_url,
    pool_pre_ping=True,
    echo=settings.DEBUG,
)

engine_chennai = create_engine(
    settings.mysql_chennai_url,
    pool_pre_ping=True,
    echo=settings.DEBUG,
)

engine_delhi = create_engine(
    settings.mysql_delhi_url,
    pool_pre_ping=True,
    echo=settings.DEBUG,
)

# Session factories for each city
SessionBangalore = sessionmaker(autocommit=False, autoflush=False, bind=engine_bangalore)
SessionChennai = sessionmaker(autocommit=False, autoflush=False, bind=engine_chennai)
SessionDelhi = sessionmaker(autocommit=False, autoflush=False, bind=engine_delhi)

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


def get_city_session(city: str):
    """Return the appropriate session for a city"""
    city = city.lower()
    if city == "bangalore":
        return SessionBangalore()
    elif city == "chennai":
        return SessionChennai()
    elif city == "delhi":
        return SessionDelhi()
    else:
        raise ValueError(f"Unknown city: {city}")
