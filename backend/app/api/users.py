from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user
from app.core.security import create_access_token
from app.schemas.user_schema import (
    TokenResponse,
    UserCreate,
    UserLogin,
    UserResponse,
    WalletResponse,
    WalletTopUp,
)
from app.schemas.vehicle_schema import VehicleCreate, VehicleResponse
from app.services import user_service

router = APIRouter()


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(body: UserCreate):
    """Create an account (replicated to all 3 nodes) and log in."""
    user = user_service.register_user(
        body.email, body.password, body.full_name, body.phone, body.home_city, body.role
    )
    token = create_access_token(user["user_id"], user["role"], user["home_city"])
    return {"access_token": token, "user": user}


@router.post("/login", response_model=TokenResponse)
def login(body: UserLogin):
    user = user_service.authenticate(body.email, body.password)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong email or password")
    token = create_access_token(user["user_id"], user["role"], user["home_city"])
    return {"access_token": token, "user": user}


@router.get("/me", response_model=UserResponse)
def me(current=Depends(get_current_user)):
    return user_service.get_user(current["user_id"])


@router.get("/me/wallet", response_model=WalletResponse)
def wallet(current=Depends(get_current_user)):
    bal = user_service.get_wallet_balance(current["user_id"], current["home_city"])
    return {"user_id": current["user_id"], "home_city": current["home_city"], "wallet_balance": float(bal)}


@router.post("/me/wallet/topup", response_model=WalletResponse)
def top_up(body: WalletTopUp, current=Depends(get_current_user)):
    """Add money to the wallet (simulated payment gateway)."""
    bal = user_service.top_up_wallet(current["user_id"], current["home_city"], body.amount)
    return {"user_id": current["user_id"], "home_city": current["home_city"], "wallet_balance": float(bal)}


@router.get("/me/vehicles", response_model=list[VehicleResponse])
def my_vehicles(current=Depends(get_current_user)):
    return user_service.list_vehicles(current["user_id"])


@router.post("/me/vehicles", response_model=VehicleResponse, status_code=201)
def add_vehicle(body: VehicleCreate, current=Depends(get_current_user)):
    return user_service.add_vehicle(current["user_id"], body.model_dump())


@router.delete("/me/vehicles/{vehicle_id}", status_code=204)
def delete_vehicle(vehicle_id: int, current=Depends(get_current_user)):
    user_service.delete_vehicle(current["user_id"], vehicle_id)
