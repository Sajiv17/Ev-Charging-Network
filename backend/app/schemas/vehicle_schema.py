from typing import Literal

from pydantic import BaseModel, Field

ConnectorType = Literal["CCS2", "CHAdeMO", "Type2"]


class VehicleCreate(BaseModel):
    make: str = Field(min_length=1, max_length=100, examples=["Tata"])
    model: str = Field(min_length=1, max_length=100, examples=["Nexon EV"])
    battery_capacity_kwh: float = Field(gt=0, lt=1000, examples=[30.2])
    connector_type: ConnectorType
    registration_number: str | None = Field(default=None, max_length=20, examples=["KA01AB1234"])


class VehicleResponse(BaseModel):
    vehicle_id: int
    user_id: int
    make: str
    model: str
    battery_capacity_kwh: float
    connector_type: str
    registration_number: str | None = None
