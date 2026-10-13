from datetime import date

from pydantic import BaseModel


class StationSummary(BaseModel):
    city: str
    station_id: int
    station_name: str
    address: str
    latitude: float | None = None
    longitude: float | None = None
    on_date: date
    matching_chargers: int  # chargers that fit the filters
    available_chargers: int  # of those, how many still have a free slot on on_date
    available_slots: int
    max_power_kw: float | None = None


class ChargerResponse(BaseModel):
    charger_id: int
    charger_code: str
    charger_type: str
    max_power_kw: float
    connector_type: str
    status: str


class StationDetail(BaseModel):
    city: str
    station_id: int
    station_name: str
    address: str
    latitude: float | None = None
    longitude: float | None = None
    operator_id: int
    is_operational: bool
    chargers: list[ChargerResponse]


class SlotResponse(BaseModel):
    city: str
    slot_id: int
    charger_id: int
    charger_code: str
    charger_type: str
    connector_type: str
    max_power_kw: float
    slot_date: date
    start_time: str  # "HH:MM"
    end_time: str
    is_available: bool
    estimated_max_price: float | None = None  # booking fee + full slot at max power


class CityResponse(BaseModel):
    key: str
    city_id: int
    name: str
