import pytest
import json
import time
from datetime import datetime, timedelta
from httpx import AsyncClient
import aiomysql

from backend.infrastructure.security.auth import create_access_token, create_websocket_session_token
from gesture_engine.transport.websocket_server import ws_handler
from backend.tests.test_websocket_pairing import MockWebSocket
from backend.application.use_cases.offboarding import OffboardingUseCase
from backend.tests.test_stripe_billing import generate_stripe_signature

OFFBOARD_TENANT_ID = "f4444444-4444-4444-4444-444444444444"
OFFBOARD_SUBDOMAIN = "offboardtenant"


@pytest.mark.anyio
async def test_tenant_soft_delete_flow(client: AsyncClient, conn):
    # 1. Seed tenant f4444444-4444-4444-4444-444444444444
    async with conn.cursor() as cur:
        await cur.execute("DELETE FROM tenants WHERE id = %s", (OFFBOARD_TENANT_ID,))
        await cur.execute(
            "INSERT INTO tenants (id, name, subdomain, plan, status) VALUES (%s, %s, %s, %s, %s)",
            (OFFBOARD_TENANT_ID, "Offboard Tenant Restaurant", OFFBOARD_SUBDOMAIN, "starter", "active")
        )
        # Create an admin user for this tenant to authenticate the admin API call
        await cur.execute(
            "INSERT INTO admins (id, username, password_hash, role, tenant_id) VALUES (%s, %s, %s, %s, %s)",
            (999, "offboard_admin", "hash", "admin", OFFBOARD_TENANT_ID)
        )
    await conn.commit()

    # 2. Trigger soft-delete manually via admin API
    admin_token = create_access_token(OFFBOARD_TENANT_ID, 999, "admin")
    headers = {"Authorization": f"Bearer {admin_token}", "X-Tenant": OFFBOARD_SUBDOMAIN}

    res = await client.post(
        f"/api/admin/tenants/{OFFBOARD_TENANT_ID}/offboard",
        headers=headers
    )
    assert res.status_code == 200
    assert res.json()["status"] == "success"

    # Commit changes so other connections (middleware/WS) see them
    await conn.commit()

    # 3. Verify middleware returns 404 for this subdomain
    res_gated = await client.get("/api/departments", headers={"X-Tenant": OFFBOARD_SUBDOMAIN})
    assert res_gated.status_code == 404

    # 4. Verify WebSocket handshake is rejected with code 4006
    ws_token = create_websocket_session_token(
        OFFBOARD_TENANT_ID,
        "mock-kiosk-id",
        "device-a",
        expires_in_hours=1
    )
    ws = MockWebSocket(f"/?token={ws_token}&device_id=device-a")
    await ws_handler(ws)
    assert ws.closed
    assert ws.close_code == 4006
    assert ws.close_reason == "Tenant subscription suspended or deactivated"

    # Cleanup
    async with conn.cursor() as cur:
        await cur.execute("DELETE FROM audit_logs WHERE tenant_id = %s", (OFFBOARD_TENANT_ID,))
        await cur.execute("DELETE FROM admins WHERE tenant_id = %s", (OFFBOARD_TENANT_ID,))
        await cur.execute("DELETE FROM tenants WHERE id = %s", (OFFBOARD_TENANT_ID,))
    await conn.commit()


@pytest.mark.anyio
async def test_tenant_webhook_soft_delete_trigger(client: AsyncClient, conn):
    webhook_tenant_id = "e4444444-4444-4444-4444-444444444444"
    webhook_subdomain = "webhookoffboard"

    # Seed tenant
    async with conn.cursor() as cur:
        await cur.execute("DELETE FROM stripe_processed_events WHERE event_id = %s", ("evt_webhook_offboard_deleted",))
        await cur.execute("DELETE FROM tenants WHERE id = %s", (webhook_tenant_id,))
        await cur.execute(
            "INSERT INTO tenants (id, name, subdomain, plan, status) VALUES (%s, %s, %s, %s, %s)",
            (webhook_tenant_id, "Webhook Offboard Restaurant", webhook_subdomain, "pro", "active")
        )
    await conn.commit()

    # Call customer.subscription.deleted Stripe Webhook
    event_deleted = json.dumps({
        "id": "evt_webhook_offboard_deleted",
        "type": "customer.subscription.deleted",
        "data": {
            "object": {
                "id": "sub_webhook_offboard",
                "customer": "cus_webhook_offboard",
                "status": "canceled",
                "metadata": {"tenant_id": webhook_tenant_id}
            }
        }
    }).encode("utf-8")

    sig = generate_stripe_signature(event_deleted, "mock_stripe_webhook_secret")
    res = await client.post(
        "/api/billing/webhook",
        content=event_deleted,
        headers={"Stripe-Signature": sig}
    )
    assert res.status_code == 200
    print("WEBHOOK RESPONSE:", res.json())

    # Verify deleted_at is set in database
    async with conn.cursor(aiomysql.DictCursor) as cur:
        await cur.execute("SELECT deleted_at, status FROM tenants WHERE id = %s", (webhook_tenant_id,))
        row = await cur.fetchone()
        assert row["deleted_at"] is not None
        assert row["status"] == "suspended"

    # Cleanup
    async with conn.cursor() as cur:
        await cur.execute("DELETE FROM tenants WHERE id = %s", (webhook_tenant_id,))
    await conn.commit()


@pytest.mark.anyio
async def test_tenant_purge_pipeline(client: AsyncClient, conn):
    # 1. Seed tenant and all related tables (operational + compliance)
    async with conn.cursor() as cur:
        # Clear existing
        await cur.execute("DELETE FROM websocket_sessions WHERE tenant_id = %s", (OFFBOARD_TENANT_ID,))
        await cur.execute("DELETE FROM kiosks WHERE tenant_id = %s", (OFFBOARD_TENANT_ID,))
        await cur.execute("DELETE FROM analytics_events WHERE tenant_id = %s", (OFFBOARD_TENANT_ID,))
        await cur.execute("DELETE FROM order_items WHERE tenant_id = %s", (OFFBOARD_TENANT_ID,))
        await cur.execute("DELETE FROM products WHERE tenant_id = %s", (OFFBOARD_TENANT_ID,))
        await cur.execute("DELETE FROM departments WHERE tenant_id = %s", (OFFBOARD_TENANT_ID,))
        await cur.execute("DELETE FROM admins WHERE tenant_id = %s", (OFFBOARD_TENANT_ID,))
        await cur.execute("DELETE FROM audit_logs WHERE tenant_id = %s", (OFFBOARD_TENANT_ID,))
        await cur.execute("DELETE FROM payments WHERE tenant_id = %s", (OFFBOARD_TENANT_ID,))
        await cur.execute("DELETE FROM orders WHERE tenant_id = %s", (OFFBOARD_TENANT_ID,))
        await cur.execute("DELETE FROM tenants WHERE id = %s", (OFFBOARD_TENANT_ID,))

        # Tenants (backdated deleted_at to 31 days ago)
        deleted_time = datetime.utcnow() - timedelta(days=31)
        await cur.execute(
            "INSERT INTO tenants (id, name, subdomain, plan, status, deleted_at) VALUES (%s, %s, %s, %s, %s, %s)",
            (OFFBOARD_TENANT_ID, "Offboard Purge Restaurant", OFFBOARD_SUBDOMAIN, "starter", "cancelled", deleted_time)
        )
        # Departments & Products
        await cur.execute(
            "INSERT INTO departments (id, tenant_id, name_en, name_ar, display_order, active) VALUES (%s, %s, %s, %s, %s, %s)",
            (990, OFFBOARD_TENANT_ID, "Purge Dept", "قسم الحذف", 1, True)
        )
        await cur.execute(
            "INSERT INTO products (id, tenant_id, department_id, name_en, name_ar, price, available) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (990, OFFBOARD_TENANT_ID, 990, "Purge Product", "منتج الحذف", 10.00, True)
        )
        # Kiosks & WS Sessions
        await cur.execute(
            "INSERT INTO kiosks (id, tenant_id, name, secret, status, device_id) VALUES (%s, %s, %s, %s, %s, %s)",
            ("kiosk-purge-id", OFFBOARD_TENANT_ID, "Purge Kiosk", "secret", "active", "device-purge")
        )
        await cur.execute(
            "INSERT INTO websocket_sessions (token, tenant_id, kiosk_id, device_id, expires_at) VALUES (%s, %s, %s, %s, %s)",
            ("purge-token", OFFBOARD_TENANT_ID, "kiosk-purge-id", "device-purge", datetime.utcnow() + timedelta(hours=1))
        )
        # Admins (staff seats)
        await cur.execute(
            "INSERT INTO admins (id, username, password_hash, role, tenant_id) VALUES (%s, %s, %s, %s, %s)",
            (990, "purge_admin", "hash", "admin", OFFBOARD_TENANT_ID)
        )
        # Audit Logs
        await cur.execute(
            "INSERT INTO audit_logs (tenant_id, user_id, action, target_type, after_state) VALUES (%s, %s, %s, %s, %s)",
            (OFFBOARD_TENANT_ID, 990, "ws_connection_failed", "kiosk", '{"detail": "Audit detail"}')
        )
        # Analytics Events
        await cur.execute(
            "INSERT INTO analytics_events (tenant_id, event_type, session_uid) VALUES (%s, %s, %s)",
            (OFFBOARD_TENANT_ID, "view_product", "session-purge")
        )
        # Orders & Order Items
        await cur.execute(
            "INSERT INTO orders (id, order_uid, tenant_id, status, total_price) VALUES (%s, %s, %s, %s, %s)",
            (990, "order-purge-uid", OFFBOARD_TENANT_ID, "completed", 20.00)
        )
        await cur.execute(
            "INSERT INTO order_items (order_id, product_id, quantity, unit_price, tenant_id) VALUES (%s, %s, %s, %s, %s)",
            (990, 990, 2, 10.00, OFFBOARD_TENANT_ID)
        )
        # Payments (compliance data)
        await cur.execute(
            "INSERT INTO payments (tenant_id, order_id, payment_method, amount_paid) VALUES (%s, %s, %s, %s)",
            (OFFBOARD_TENANT_ID, 990, "cash", 20.00)
        )
    await conn.commit()

    # 2. Run the Offboarding purge pipeline
    use_case = OffboardingUseCase(conn)
    purged_count = await use_case.purge_expired_tenants(grace_period_days=30)
    assert purged_count == 1

    # Commit changes
    await conn.commit()

    # 3. Assert all operational data is permanently purged
    async with conn.cursor(aiomysql.DictCursor) as cur:
        # websocket_sessions
        await cur.execute("SELECT COUNT(*) as count FROM websocket_sessions WHERE tenant_id = %s", (OFFBOARD_TENANT_ID,))
        assert (await cur.fetchone())["count"] == 0
        # kiosks
        await cur.execute("SELECT COUNT(*) as count FROM kiosks WHERE tenant_id = %s", (OFFBOARD_TENANT_ID,))
        assert (await cur.fetchone())["count"] == 0
        # analytics_events
        await cur.execute("SELECT COUNT(*) as count FROM analytics_events WHERE tenant_id = %s", (OFFBOARD_TENANT_ID,))
        assert (await cur.fetchone())["count"] == 0
        # order_items
        await cur.execute("SELECT COUNT(*) as count FROM order_items WHERE tenant_id = %s", (OFFBOARD_TENANT_ID,))
        assert (await cur.fetchone())["count"] == 0
        # products
        await cur.execute("SELECT COUNT(*) as count FROM products WHERE tenant_id = %s", (OFFBOARD_TENANT_ID,))
        assert (await cur.fetchone())["count"] == 0
        # departments
        await cur.execute("SELECT COUNT(*) as count FROM departments WHERE tenant_id = %s", (OFFBOARD_TENANT_ID,))
        assert (await cur.fetchone())["count"] == 0
        # admins
        await cur.execute("SELECT COUNT(*) as count FROM admins WHERE tenant_id = %s", (OFFBOARD_TENANT_ID,))
        assert (await cur.fetchone())["count"] == 0
        # audit_logs
        await cur.execute("SELECT COUNT(*) as count FROM audit_logs WHERE tenant_id = %s", (OFFBOARD_TENANT_ID,))
        assert (await cur.fetchone())["count"] == 0

    # 4. Assert compliance/financial tables STILL exist and are preserved/anonymized
    async with conn.cursor(aiomysql.DictCursor) as cur:
        # tenants: name is Deleted Tenant, subdomain is changed, status cancelled, deleted_at NULL
        await cur.execute("SELECT name, subdomain, status, deleted_at FROM tenants WHERE id = %s", (OFFBOARD_TENANT_ID,))
        row = await cur.fetchone()
        assert row is not None
        assert row["name"] == "Deleted Tenant"
        assert row["subdomain"] == f"deleted-{OFFBOARD_TENANT_ID[:8]}"
        assert row["status"] == "cancelled"
        assert row["deleted_at"] is None

        # orders: completed order record still exists
        await cur.execute("SELECT COUNT(*) as count FROM orders WHERE tenant_id = %s", (OFFBOARD_TENANT_ID,))
        assert (await cur.fetchone())["count"] == 1

        # payments: payment record still exists
        await cur.execute("SELECT COUNT(*) as count FROM payments WHERE tenant_id = %s", (OFFBOARD_TENANT_ID,))
        assert (await cur.fetchone())["count"] == 1

    # Cleanup remaining compliance records
    async with conn.cursor() as cur:
        await cur.execute("DELETE FROM payments WHERE tenant_id = %s", (OFFBOARD_TENANT_ID,))
        await cur.execute("DELETE FROM orders WHERE tenant_id = %s", (OFFBOARD_TENANT_ID,))
        await cur.execute("DELETE FROM tenants WHERE id = %s", (OFFBOARD_TENANT_ID,))
    await conn.commit()
