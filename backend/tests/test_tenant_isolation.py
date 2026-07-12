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


@pytest.mark.asyncio
async def test_order_and_items_isolation(client: AsyncClient, conn):
    tenant_b_id = "b4444444-4444-4444-4444-444444444444"
    async with conn.cursor() as cur:
        # Create Tenant B
        await cur.execute(
            "INSERT INTO tenants (id, name, subdomain, plan, status) VALUES (%s, %s, %s, %s, %s)",
            (tenant_b_id, "Tenant B Restaurant", "tenantb", "starter", "active")
        )
        # Create Tenant B Admin
        await cur.execute(
            "INSERT INTO admins (id, tenant_id, username, password_hash, role) VALUES (%s, %s, %s, %s, %s)",
            (201, tenant_b_id, "tenant_b_admin", "hash", "admin")
        )
        # Create a product for Tenant B
        await cur.execute(
            "INSERT INTO departments (id, tenant_id, name_en, name_ar, display_order, active) VALUES (%s, %s, %s, %s, %s, %s)",
            (999, tenant_b_id, "B Burgers", "برجر ب", 1, True)
        )
        await cur.execute(
            "INSERT INTO products (id, tenant_id, department_id, name_en, name_ar, price, available) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (999, tenant_b_id, 999, "B Secret Burger", "برجر سري ب", 150.00, True)
        )
        # Create an order for Tenant B
        tenant_b_order_uid = "b2222222-2222-2222-2222-222222222222"
        await cur.execute(
            "INSERT INTO orders (id, tenant_id, order_uid, status, total_price) VALUES (%s, %s, %s, %s, %s)",
            (999, tenant_b_id, tenant_b_order_uid, "pending", 0.00)
        )
        # Add an item to Tenant B's order
        await cur.execute(
            "INSERT INTO order_items (tenant_id, order_id, product_id, quantity, unit_price) VALUES (%s, %s, %s, %s, %s)",
            (tenant_b_id, 999, 999, 2, 150.00)
        )

    # Insert Tenant A admin to satisfy audit log constraint for status change tests
    async with conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO admins (id, tenant_id, username, password_hash, role) VALUES (%s, %s, %s, %s, %s)",
            (103, "d4444444-4444-4444-4444-444444444444", "tenant_a_admin", "hash", "admin")
        )

    from backend.infrastructure.security.auth import create_access_token
    tenant_a_token = create_access_token("d4444444-4444-4444-4444-444444444444", 103, "admin")
    headers_a = {
        "Authorization": f"Bearer {tenant_a_token}",
        "X-Tenant": "demo"
    }

    # 1. Tenant A attempts to add items to Tenant B's order -> must return 404 (Not Found)
    resp_add = await client.post(
        f"/api/orders/{tenant_b_order_uid}/items",
        json={"product_id": 1, "quantity": 1},
        headers=headers_a
    )
    assert resp_add.status_code == 404

    # 2. Tenant A attempts to update status of Tenant B's order -> must return 404 (Not Found)
    resp_status = await client.post(
        "/api/orders/999/status",
        json={"status": "confirmed"},
        headers=headers_a
    )
    assert resp_status.status_code == 404

    # 3. Repository level verification:
    from backend.infrastructure.database.mysql_order_repo import MysqlOrderRepo
    repo = MysqlOrderRepo(conn)
    
    # Query order by UID under Tenant A context -> must return None
    order_by_uid = await repo.get_order_by_uid("d4444444-4444-4444-4444-444444444444", tenant_b_order_uid)
    assert order_by_uid is None

    # Query order by ID under Tenant A context -> must return None
    order_by_id = await repo.get_order_by_id("d4444444-4444-4444-4444-444444444444", 999)
    assert order_by_id is None

    # Query order items under Tenant A context -> must return empty list
    items = await repo.get_order_items("d4444444-4444-4444-4444-444444444444", 999)
    assert len(items) == 0

    # Query specific order item under Tenant A context -> must return None
    item = await repo.get_item("d4444444-4444-4444-4444-444444444444", 999, 999)
    assert item is None
