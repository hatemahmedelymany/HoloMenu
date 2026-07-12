import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_department_isolation(client: AsyncClient, conn):
    # 1. Insert Tenant B into the database
    tenant_b_id = "b4444444-4444-4444-4444-444444444444"
    async with conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO tenants (id, name, subdomain, plan, status) VALUES (%s, %s, %s, %s, %s)",
            (tenant_b_id, "Tenant B Restaurant", "tenantb", "starter", "active")
        )
        # Create a department for Tenant B
        await cur.execute(
            "INSERT INTO departments (tenant_id, name_en, name_ar, display_order, active) VALUES (%s, %s, %s, %s, %s)",
            (tenant_b_id, "B Sides", "جانبي ب", 1, True)
        )
    
    # 2. Query departments for Tenant A
    response_a = await client.get("/api/departments", headers={"X-Tenant": "demo"})
    assert response_a.status_code == 200
    depts_a = response_a.json()
    for dept in depts_a:
        assert dept["name_en"] != "B Sides"

    # 3. Query departments for Tenant B
    response_b = await client.get("/api/departments", headers={"X-Tenant": "tenantb"})
    assert response_b.status_code == 200
    depts_b = response_b.json()
    assert len(depts_b) == 1
    assert depts_b[0]["name_en"] == "B Sides"


@pytest.mark.asyncio
async def test_cross_tenant_product_referencing(client: AsyncClient, conn):
    tenant_b_id = "b4444444-4444-4444-4444-444444444444"
    async with conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO tenants (id, name, subdomain, plan, status) VALUES (%s, %s, %s, %s, %s)",
            (tenant_b_id, "Tenant B Restaurant", "tenantb", "starter", "active")
        )
        # Create a department for Tenant B
        await cur.execute(
            "INSERT INTO departments (id, tenant_id, name_en, name_ar, display_order, active) VALUES (%s, %s, %s, %s, %s, %s)",
            (999, tenant_b_id, "B Burgers", "برجر ب", 1, True)
        )
        # Create a product for Tenant B
        await cur.execute(
            "INSERT INTO products (id, tenant_id, department_id, name_en, name_ar, price, available) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (999, tenant_b_id, 999, "B Secret Burger", "برجر سري ب", 150.00, True)
        )

    # 1. Create an order under Tenant A
    order_response = await client.post("/api/orders", headers={"X-Tenant": "demo"})
    assert order_response.status_code == 201
    order = order_response.json()
    order_uid = order["order_uid"]

    # 2. Attempt to add Tenant B's product to Tenant A's order.
    add_item_response = await client.post(
        f"/api/orders/{order_uid}/items",
        json={"product_id": 999, "quantity": 1},
        headers={"X-Tenant": "demo"}
    )
    assert add_item_response.status_code in (404, 400)
