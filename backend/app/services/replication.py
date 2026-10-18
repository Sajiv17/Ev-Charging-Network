"""
Writes to replicated tables (users, vehicles, pricing_plans).

These rows must exist on every city node with the SAME primary key, because
bookings on any node have foreign keys to users and vehicles.

How it works:
  1. Open one session per node.
  2. Insert on the ID-authority node first -> MySQL generates the id.
  3. Insert the same row, with that explicit id, on the other nodes.
  4. Commit everywhere. If anything fails before the commits, roll back
     everywhere, so no node keeps a half-registered user.

Phase-1 limitation (fixed in phase 2): the commits in step 4 are one after
another, not a true atomic commit. If a node dies exactly between two
commits, the nodes disagree. Phase 2 swaps step 4 for XA two-phase commit
(the same mechanism used for cross-city bookings).
"""

from typing import Callable

from sqlalchemy.orm import Session

from app.core.cities import CITIES, ID_AUTHORITY_CITY
from app.db.mysql_connection import get_city_session


def node_order() -> list[str]:
    """Authority node first, then the rest."""
    return [ID_AUTHORITY_CITY] + [c for c in CITIES if c != ID_AUTHORITY_CITY]


def write_everywhere(write_fn: Callable[[str, Session, int | None], int]) -> int:
    """
    write_fn(city, db, new_id) runs once per node.
    On the authority node new_id is None and write_fn must return the
    generated id; on other nodes it receives that id and must reuse it.
    Returns the id.
    """
    sessions = {city: get_city_session(city) for city in node_order()}
    try:
        new_id = None
        for city, db in sessions.items():
            got = write_fn(city, db, new_id)
            if new_id is None:
                new_id = got
        for db in sessions.values():
            db.commit()
        return new_id
    except Exception:
        for db in sessions.values():
            try:
                db.rollback()
            except Exception:
                pass
        raise
    finally:
        for db in sessions.values():
            db.close()
