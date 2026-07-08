"""
FastAPI dependency injectors for Authentication, Tenancy, and Authorization.
"""
from typing import Optional
from fastapi import Request, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
import jwt

# We import the JWT settings / decode utility from infrastructure/security/auth
from backend.infrastructure.security.auth import (
    JWT_SECRET_KEY,
    JWT_ALGORITHM,
    decode_access_token,
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


async def get_current_tenant_id(request: Request) -> str:
    """Dependency that resolves tenant_id from request.state."""
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context missing")
    return tenant_id


async def get_current_user(
    request: Request, token: Optional[str] = Depends(oauth2_scheme)
) -> dict:
    """Validate request bearer token and return user identity dict."""
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        payload = decode_access_token(token)
        admin_id = payload.get("sub")
        tenant_id = payload.get("tenant_id")
        role = payload.get("role")
        if not admin_id or not tenant_id or not role:
            raise HTTPException(
                status_code=401, detail="Invalid authentication credentials"
            )

        user_data = {
            "admin_id": int(admin_id),
            "tenant_id": tenant_id,
            "role": role,
        }
        # Set state for audit/trace logging
        request.state.user_id = user_data["admin_id"]
        return user_data
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")


def require_role(*allowed_roles):
    """Factory return decorator requiring the user object to have one of allowed_roles."""
    async def checker(
        user: dict = Depends(get_current_user),
        tenant_id: str = Depends(get_current_tenant_id),
    ):
        if user["role"] not in allowed_roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        if user["tenant_id"] != tenant_id:
            raise HTTPException(status_code=403, detail="Tenant context mismatch")
        return user

    return checker
