import pytest
import jwt
from datetime import datetime, timedelta
from httpx import AsyncClient
from backend.infrastructure.security.auth import (
    JWT_SECRET_KEY,
    JWT_ALGORITHM,
    create_access_token,
    create_refresh_token,
)

DEMO_TENANT_ID = "d4444444-4444-4444-4444-444444444444"

def create_expired_access_token(tenant_id: str, admin_id: int, role: str) -> str:
    expire = datetime.utcnow() - timedelta(minutes=15)
    to_encode = {
        "sub": str(admin_id),
        "tenant_id": tenant_id,
        "role": role,
        "exp": expire,
        "type": "access"
    }
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

def create_expired_refresh_token(tenant_id: str, admin_id: int, role: str) -> str:
    expire = datetime.utcnow() - timedelta(days=7)
    to_encode = {
        "sub": str(admin_id),
        "tenant_id": tenant_id,
        "role": role,
        "exp": expire,
        "type": "refresh"
    }
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


@pytest.mark.asyncio
async def test_expired_access_token(client: AsyncClient):
    # Create an expired token for an admin
    expired_token = create_expired_access_token(DEMO_TENANT_ID, 103, "admin")
    
    # Request a protected endpoint
    response = await client.post(
        "/api/departments",
        json={"name_en": "Expired Test", "name_ar": "تجربة منتهية"},
        headers={"Authorization": f"Bearer {expired_token}"}
    )
    
    # Must fail with 401 Token has expired
    assert response.status_code == 401
    assert response.json()["detail"] == "Token has expired"


@pytest.mark.asyncio
async def test_expired_refresh_token(client: AsyncClient):
    expired_ref = create_expired_refresh_token(DEMO_TENANT_ID, 103, "admin")
    
    # Call refresh endpoint with the expired cookie
    client.cookies.set("refresh_token", expired_ref)
    response = await client.post("/api/auth/refresh")
    
    assert response.status_code == 401
    assert response.json()["detail"] == "Refresh token has expired"


@pytest.mark.asyncio
async def test_revoked_or_unsaved_refresh_token(client: AsyncClient, conn):
    # Create a fresh refresh token, but DO NOT save it in the database
    unsaved_ref = create_refresh_token(DEMO_TENANT_ID, 103, "admin")
    
    client.cookies.set("refresh_token", unsaved_ref)
    response = await client.post("/api/auth/refresh")
    
    assert response.status_code == 401
    assert response.json()["detail"] == "Revoked or invalid refresh token"


@pytest.mark.asyncio
async def test_refresh_token_revocation_on_logout(client: AsyncClient, conn):
    # Insert admin into DB to satisfy audit log constraint
    async with conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO admins (id, tenant_id, username, password_hash, role) VALUES (%s, %s, %s, %s, %s)",
            (103, DEMO_TENANT_ID, "test_admin_logout", "hash", "admin")
        )

    # 1. Simulate login by creating a refresh token and saving it in the DB
    ref_token = create_refresh_token(DEMO_TENANT_ID, 103, "admin")
    expires_at = datetime.utcnow() + timedelta(days=7)
    
    async with conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO refresh_tokens (tenant_id, admin_id, token, expires_at) VALUES (%s, %s, %s, %s)",
            (DEMO_TENANT_ID, 103, ref_token, expires_at)
        )
    
    # Verify the token is active/valid in DB
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT id FROM refresh_tokens WHERE token = %s AND tenant_id = %s",
            (ref_token, DEMO_TENANT_ID)
        )
        row = await cur.fetchone()
        assert row is not None

    # 2. Call logout using this refresh token cookie
    client.cookies.set("refresh_token", ref_token)
    logout_response = await client.post("/api/auth/logout")
    assert logout_response.status_code == 200
    
    # 3. Verify it was deleted from DB (revoked)
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT id FROM refresh_tokens WHERE token = %s AND tenant_id = %s",
            (ref_token, DEMO_TENANT_ID)
        )
        row = await cur.fetchone()
        assert row is None

    # 4. Attempting to refresh using the revoked token must return 401
    refresh_response = await client.post("/api/auth/refresh")
    assert refresh_response.status_code == 401
    assert refresh_response.json()["detail"] == "Revoked or invalid refresh token"
