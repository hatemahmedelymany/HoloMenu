import pytest
from httpx import AsyncClient
from backend.infrastructure.security.auth import create_access_token

DEMO_TENANT_ID = "d4444444-4444-4444-4444-444444444444"

@pytest.mark.asyncio
async def test_order_status_transitions(client: AsyncClient, conn):
    chef_token = create_access_token(DEMO_TENANT_ID, 101, "chef")
    headers = {
        "Authorization": f"Bearer {chef_token}",
        "X-Tenant": "demo"
    }

    # Insert chef admin to satisfy audit log constraint
    async with conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO admins (id, tenant_id, username, password_hash, role) VALUES (%s, %s, %s, %s, %s)",
            (101, DEMO_TENANT_ID, "chef_user_lifecycle", "hash", "chef")
        )

    # 1. Create order
    resp_create = await client.post("/api/orders", headers=headers)
    assert resp_create.status_code == 201
    order = resp_create.json()
    order_uid = order["order_uid"]
    assert order["status"] == "pending"

    # Query DB to get the auto-increment integer ID of the order
    async with conn.cursor() as cur:
        await cur.execute("SELECT id FROM orders WHERE order_uid = %s", (order_uid,))
        row = await cur.fetchone()
        order_id = row[0]

    # 2. Transition pending -> confirmed
    resp_confirmed = await client.post(f"/api/orders/{order_id}/status", json={"status": "confirmed"}, headers=headers)
    assert resp_confirmed.status_code == 200
    assert resp_confirmed.json()["status"] == "updated"
    assert resp_confirmed.json()["new_status"] == "confirmed"

    # 3. Transition confirmed -> cooking
    resp_cooking = await client.post(f"/api/orders/{order_id}/status", json={"status": "cooking"}, headers=headers)
    assert resp_cooking.status_code == 200
    assert resp_cooking.json()["status"] == "updated"
    assert resp_cooking.json()["new_status"] == "cooking"

    # 4. Try Transition cooking -> pending (invalid)
    resp_invalid = await client.post(f"/api/orders/{order_id}/status", json={"status": "pending"}, headers=headers)
    assert resp_invalid.status_code == 409
    assert "Cannot move order from" in resp_invalid.json()["detail"]

    # 5. Transition cooking -> ready
    resp_ready = await client.post(f"/api/orders/{order_id}/status", json={"status": "ready"}, headers=headers)
    assert resp_ready.status_code == 200
    assert resp_ready.json()["status"] == "updated"
    assert resp_ready.json()["new_status"] == "ready"

    # 6. Transition ready -> completed
    resp_completed = await client.post(f"/api/orders/{order_id}/status", json={"status": "completed"}, headers=headers)
    assert resp_completed.status_code == 200
    assert resp_completed.json()["status"] == "updated"
    assert resp_completed.json()["new_status"] == "completed"

    # 7. Try Transition completed -> cancelled (invalid)
    resp_invalid_cancelled = await client.post(f"/api/orders/{order_id}/status", json={"status": "cancelled"}, headers=headers)
    assert resp_invalid_cancelled.status_code == 409
