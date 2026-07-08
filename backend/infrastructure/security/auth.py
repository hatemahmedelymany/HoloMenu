"""
Password hashing and JWT token utilities.

This module contains ZERO FastAPI dependencies — it's pure infrastructure
that can be used by any layer above it.
"""
import os
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
import jwt

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "holomenu_super_secret_key_123456")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False


def create_access_token(tenant_id: str, admin_id: int, role: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {
        "sub": str(admin_id),
        "tenant_id": tenant_id,
        "role": role,
        "exp": expire,
        "type": "access"
    }
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def create_refresh_token(tenant_id: str, admin_id: int, role: str) -> str:
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode = {
        "sub": str(admin_id),
        "tenant_id": tenant_id,
        "role": role,
        "exp": expire,
        "type": "refresh"
    }
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Decode and validate an access token. Raises jwt exceptions on failure."""
    payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("Invalid token type")
    return payload


def decode_refresh_token(token: str) -> dict:
    """Decode and validate a refresh token. Raises jwt exceptions on failure."""
    payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    if payload.get("type") != "refresh":
        raise jwt.InvalidTokenError("Invalid token type")
    return payload
