import pytest
from httpx import AsyncClient
from backend.infrastructure.security.auth import create_access_token

DEMO_TENANT_ID = "d4444444-4444-4444-4444-444444444444"

@pytest.mark.asyncio
async def test_endpoint_role_restrictions(client: AsyncClient, conn):
    chef_token = create_access_token(DEMO_TENANT_ID, 101, "chef")
    cashier_token = create_access_token(DEMO_TENANT_ID, 102, "cashier")
    admin_token = create_access_token(DEMO_TENANT_ID, 103, "admin")
    
    # Insert mock admins into the database to satisfy the audit_logs foreign key constraint
    async with conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO admins (id, tenant_id, username, password_hash, role) VALUES (%s, %s, %s, %s, %s)",
            (101, DEMO_TENANT_ID, "chef_user", "hash", "chef")
        )
        await cur.execute(
            "INSERT INTO admins (id, tenant_id, username, password_hash, role) VALUES (%s, %s, %s, %s, %s)",
            (102, DEMO_TENANT_ID, "cashier_user", "hash", "cashier")
        )
        await cur.execute(
            "INSERT INTO admins (id, tenant_id, username, password_hash, role) VALUES (%s, %s, %s, %s, %s)",
            (103, DEMO_TENANT_ID, "admin_user", "hash", "admin")
        )
    
    # 1. POST /api/departments (restricted to admin/owner)
    # Case A: Unauthenticated
    resp_unauth = await client.post("/api/departments", json={"name_en": "Test", "name_ar": "تجربة"})
    assert resp_unauth.status_code == 401
    
    # Case B: Insufficient Role (Chef)
    resp_chef = await client.post(
        "/api/departments",
        json={"name_en": "Test", "name_ar": "تجربة"},
        headers={"Authorization": f"Bearer {chef_token}"}
    )
    assert resp_chef.status_code == 403
    assert resp_chef.json()["detail"] == "Insufficient permissions"
    
    # Case C: Insufficient Role (Cashier)
    resp_cashier = await client.post(
        "/api/departments",
        json={"name_en": "Test", "name_ar": "تجربة"},
        headers={"Authorization": f"Bearer {cashier_token}"}
    )
    assert resp_cashier.status_code == 403
    
    # Case D: Authorized Role (Admin)
    resp_admin = await client.post(
        "/api/departments",
        json={"name_en": "Test", "name_ar": "تجربة", "display_order": 5, "active": True},
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert resp_admin.status_code == 201
    assert resp_admin.json()["status"] == "created"
    assert "id" in resp_admin.json()


@pytest.mark.asyncio
async def test_tenant_context_mismatch(client: AsyncClient, conn):
    tenant_b_id = "b4444444-4444-4444-4444-444444444444"
    async with conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO tenants (id, name, subdomain, plan, status) VALUES (%s, %s, %s, %s, %s)",
            (tenant_b_id, "Tenant B", "tenantb", "starter", "active")
        )
        # Insert admin for Tenant B
        await cur.execute(
            "INSERT INTO admins (id, tenant_id, username, password_hash, role) VALUES (%s, %s, %s, %s, %s)",
            (201, tenant_b_id, "tenant_b_admin", "hash", "admin")
        )
    
    tenant_b_admin_token = create_access_token(tenant_b_id, 201, "admin")
    
    resp = await client.post(
        "/api/departments",
        json={"name_en": "Test", "name_ar": "تجربة"},
        headers={
            "Authorization": f"Bearer {tenant_b_admin_token}",
            "X-Tenant": "demo"
        }
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Tenant context mismatch"
