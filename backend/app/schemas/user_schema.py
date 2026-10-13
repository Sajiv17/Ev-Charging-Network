import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

CityName = Literal["bangalore", "chennai", "delhi"]


def _check_email(v: str) -> str:
    v = v.strip().lower()
    if not _EMAIL_RE.match(v):
        raise ValueError("invalid email address")
    return v


class UserCreate(BaseModel):
    email: str
    password: str = Field(min_length=6, max_length=72)
    full_name: str = Field(min_length=1, max_length=255)
    phone: str | None = Field(default=None, max_length=20)
    home_city: CityName = Field(description="City whose node holds this user's wallet")
    role: Literal["driver", "operator"] = "driver"

    _email = field_validator("email")(_check_email)

    @field_validator("home_city", mode="before")
    @classmethod
    def _lower_city(cls, v):
        return v.strip().lower() if isinstance(v, str) else v


class UserLogin(BaseModel):
    email: str
    password: str

    _email = field_validator("email")(_check_email)


class UserResponse(BaseModel):
    user_id: int
    email: str
    full_name: str
    phone: str | None = None
    role: str
    home_city: str
    wallet_balance: float


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class WalletTopUp(BaseModel):
    amount: float = Field(gt=0, le=50000, description="INR to add to wallet")


class WalletResponse(BaseModel):
    user_id: int
    home_city: str
    wallet_balance: float
