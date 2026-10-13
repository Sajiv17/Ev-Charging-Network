from datetime import date, time
from typing import Literal

from fastapi import APIRouter, Query

from app.schemas.station_schema import CityResponse, SlotResponse, StationDetail, StationSummary
from app.services import station_service

router = APIRouter()

Connector = Literal["CCS2", "CHAdeMO", "Type2"]
ChargerType = Literal["AC", "DC"]


@router.get("/cities", response_model=list[CityResponse])
def cities():
    return station_service.list_cities()


@router.get("", response_model=list[StationSummary])
def search(
    city: str = Query(..., examples=["bangalore"]),
    on_date: date | None = Query(None, alias="date", description="YYYY-MM-DD, defaults to today"),
    connector_type: Connector | None = None,
    charger_type: ChargerType | None = None,
    from_time: time | None = Query(None, description="Earliest slot start, e.g. 09:00"),
    to_time: time | None = Query(None, description="Latest slot end, e.g. 18:00"),
):
    """Stations in one city with how many free chargers/slots they have on a date (default: today)."""
    return station_service.search_stations(
        city, on_date or station_service.today_ist(), connector_type, charger_type, from_time, to_time
    )


@router.get("/{city}/{station_id}", response_model=StationDetail)
def detail(city: str, station_id: int):
    return station_service.get_station(city, station_id)


@router.get("/{city}/{station_id}/slots", response_model=list[SlotResponse])
def slots(
    city: str,
    station_id: int,
    on_date: date | None = Query(None, alias="date", description="YYYY-MM-DD, defaults to today"),
    connector_type: Connector | None = None,
    only_available: bool = True,
):
    return station_service.list_slots(
        city, station_id, on_date or station_service.today_ist(), connector_type, only_available
    )
