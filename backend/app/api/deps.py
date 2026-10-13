"""Shared FastAPI dependencies: who is calling?"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import decode_access_token

_bearer = HTTPBearer(auto_error=False)


def get_current_user(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> dict:
    """
    Reads 'Authorization: Bearer <token>' and returns
    {"user_id": int, "role": str, "home_city": str}.
    """
    if creds is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Not logged in", headers={"WWW-Authenticate": "Bearer"}
        )
    payload = decode_access_token(creds.credentials)
    if not payload:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Invalid or expired token", headers={"WWW-Authenticate": "Bearer"}
        )
    return {"user_id": int(payload["sub"]), "role": payload["role"], "home_city": payload["home_city"]}


def require_role(*roles: str):
    def checker(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requires role: {', '.join(roles)}")
        return user

    return checker
