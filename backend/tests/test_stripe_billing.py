import pytest
import time
import hmac
import hashlib
import json
from datetime import datetime, timedelta
from httpx import AsyncClient
import aiomysql

from backend.infrastructure.security.auth import create_access_token, create_websocket_session_token
from gesture_engine.transport.websocket_server import ws_handler
from backend.tests.test_websocket_pairing import MockWebSocket

DEMO_TENANT_ID = "d4444444-4444-4444-4444-444444444444"
SECRET = "mock_stripe_webhook_secret"


def generate_stripe_signature(payload: bytes, secret: str, timestamp: int = None) -> str:
    if timestamp is None:
        timestamp = int(time.time())
    signed_payload = f"{timestamp}.".encode('utf-8') + payload
    v1 = hmac.new(
        secret.encode('utf-8'),
        signed_payload,
        hashlib.sha256
    ).hexdigest()
    return f"t={timestamp},v1={v1}"


@pytest.mark.anyio
async def test_stripe_signature_security(client: AsyncClient):
    event_payload = json.dumps({
        "id": "evt_test_sig",
        "type": "charge.refunded",
        "data": {"object": {}}
    }).encode("utf-8")

    # 1. Valid signature -> returns 200 OK (ignored status since it is unhandled)
    sig = generate_stripe_signature(event_payload, SECRET)
    res = await client.post(
        "/api/billing/webhook",
        content=event_payload,
        headers={"Stripe-Signature": sig}
    )
    assert res.status_code == 200
    assert res.json()["status"] == "ignored"

    # 2. Invalid secret -> returns 400 Bad Request
    bad_sig = generate_stripe_signature(event_payload, "wrong_secret")
    res_bad = await client.post(
        "/api/billing/webhook",
        content=event_payload,
        headers={"Stripe-Signature": bad_sig}
    )
    assert res_bad.status_code == 400

    # 3. Expired timestamp (> 5 minutes ago) -> returns 400 Bad Request
    old_time = int(time.time()) - 360  # 6 minutes ago
    expired_sig = generate_stripe_signature(event_payload, SECRET, timestamp=old_time)
    res_expired = await client.post(
        "/api/billing/webhook",
        content=event_payload,
        headers={"Stripe-Signature": expired_sig}
    )
    assert res_expired.status_code == 400


@pytest.mark.anyio
async def test_stripe_webhook_idempotency_and_unhandled(client: AsyncClient, conn):
    # Clear idempotency table
    async with conn.cursor() as cur:
        await cur.execute("DELETE FROM stripe_processed_events")

    event_payload = json.dumps({
        "id": "evt_test_idempotency",
        "type": "charge.refunded",
        "data": {"object": {}}
    }).encode("utf-8")

    sig = generate_stripe_signature(event_payload, SECRET)

    # First request -> success/ignored (200)
    res1 = await client.post(
        "/api/billing/webhook",
        content=event_payload,
        headers={"Stripe-Signature": sig}
    )
    assert res1.status_code == 200
    assert res1.json()["status"] == "ignored"

    # Second request with same event_id -> returns already_processed
    res2 = await client.post(
        "/api/billing/webhook",
        content=event_payload,
        headers={"Stripe-Signature": sig}
    )
    assert res2.status_code == 200
    assert res2.json()["status"] == "already_processed"


@pytest.mark.anyio
async def test_stripe_webhook_subscription_lifecycle(client: AsyncClient, conn):
    # Ensure demo tenant starts as starter / active
    async with conn.cursor() as cur:
        await cur.execute(
            "UPDATE tenants SET plan = 'starter', status = 'active', grace_period_ends_at = NULL WHERE id = %s",
            (DEMO_TENANT_ID,)
        )

    # 1. customer.subscription.created -> upgrade to pro
    event_created = json.dumps({
        "id": "evt_sub_created",
        "type": "customer.subscription.created",
        "data": {
            "object": {
                "id": "sub_1",
                "customer": "cus_1",
                "status": "active",
                "metadata": {"tenant_id": DEMO_TENANT_ID, "plan": "pro"}
            }
        }
    }).encode("utf-8")

    sig1 = generate_stripe_signature(event_created, SECRET)
    res1 = await client.post(
        "/api/billing/webhook",
        content=event_created,
        headers={"Stripe-Signature": sig1}
    )
    assert res1.status_code == 200
    assert res1.json()["status"] == "success"

    # Check DB updates (plan=pro, max_kiosks=5)
    async with conn.cursor(aiomysql.DictCursor) as cur:
        await cur.execute("SELECT plan, status, max_kiosks, grace_period_ends_at FROM tenants WHERE id = %s", (DEMO_TENANT_ID,))
        row = await cur.fetchone()
        assert row["plan"] == "pro"
        assert row["max_kiosks"] == 5
        assert row["status"] == "active"
        assert row["grace_period_ends_at"] is None

    # 2. customer.subscription.updated (past_due) -> grace period set
    event_past_due = json.dumps({
        "id": "evt_sub_past_due",
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "id": "sub_1",
                "customer": "cus_1",
                "status": "past_due",
                "metadata": {"tenant_id": DEMO_TENANT_ID, "plan": "pro"}
            }
        }
    }).encode("utf-8")

    sig2 = generate_stripe_signature(event_past_due, SECRET)
    res2 = await client.post(
        "/api/billing/webhook",
        content=event_past_due,
        headers={"Stripe-Signature": sig2}
    )
    assert res2.status_code == 200

    # Check DB updates (status=active, grace_period_ends_at is set to future date)
    async with conn.cursor(aiomysql.DictCursor) as cur:
        await cur.execute("SELECT plan, status, grace_period_ends_at FROM tenants WHERE id = %s", (DEMO_TENANT_ID,))
        row = await cur.fetchone()
        assert row["status"] == "active"
        assert row["grace_period_ends_at"] is not None
        # Should be roughly 7 days from now
        diff = row["grace_period_ends_at"] - datetime.utcnow()
        assert diff.days == 6 or diff.days == 7

    # 3. invoice.payment_succeeded -> recovery path (clears grace period)
    event_recovered = json.dumps({
        "id": "evt_invoice_succeeded",
        "type": "invoice.payment_succeeded",
        "data": {
            "object": {
                "id": "in_1",
                "customer": "cus_1",
                "metadata": {"tenant_id": DEMO_TENANT_ID}
            }
        }
    }).encode("utf-8")

    sig3 = generate_stripe_signature(event_recovered, SECRET)
    res3 = await client.post(
        "/api/billing/webhook",
        content=event_recovered,
        headers={"Stripe-Signature": sig3}
    )
    assert res3.status_code == 200

    # Check DB updates (status=active, grace_period_ends_at is cleared)
    async with conn.cursor(aiomysql.DictCursor) as cur:
        await cur.execute("SELECT plan, status, grace_period_ends_at FROM tenants WHERE id = %s", (DEMO_TENANT_ID,))
        row = await cur.fetchone()
        assert row["status"] == "active"
        assert row["grace_period_ends_at"] is None

    # 4. customer.subscription.deleted -> suspended
    event_deleted = json.dumps({
        "id": "evt_sub_deleted",
        "type": "customer.subscription.deleted",
        "data": {
            "object": {
                "id": "sub_1",
                "customer": "cus_1",
                "status": "canceled",
                "metadata": {"tenant_id": DEMO_TENANT_ID}
            }
        }
    }).encode("utf-8")

    sig4 = generate_stripe_signature(event_deleted, SECRET)
    res4 = await client.post(
        "/api/billing/webhook",
        content=event_deleted,
        headers={"Stripe-Signature": sig4}
    )
    assert res4.status_code == 200

    # Check DB updates (status=suspended)
    async with conn.cursor(aiomysql.DictCursor) as cur:
        await cur.execute("SELECT plan, status, grace_period_ends_at FROM tenants WHERE id = %s", (DEMO_TENANT_ID,))
        row = await cur.fetchone()
        assert row["status"] == "suspended"
        assert row["grace_period_ends_at"] is None


@pytest.mark.anyio
async def test_stripe_webhook_lazy_gating(client: AsyncClient, conn):
    # Set demo tenant status to active but grace_period_ends_at to 5 minutes ago (expired)
    expired_time = datetime.utcnow() - timedelta(minutes=5)
    async with conn.cursor() as cur:
        await cur.execute(
            "UPDATE tenants SET plan = 'pro', status = 'active', grace_period_ends_at = %s WHERE id = %s",
            (expired_time, DEMO_TENANT_ID)
        )
    await conn.commit()

    # 1. HTTP Endpoint Gating Check -> returns 402 Payment Required
    headers = {"X-Tenant": "demo"}
    res = await client.get("/api/departments", headers=headers)
    assert res.status_code == 402
    assert "Subscription past due" in res.json()["detail"]

    # 2. WebSocket Gating Check -> close code 4006
    token = create_websocket_session_token(
        DEMO_TENANT_ID,
        "mock-kiosk-id",
        "device-a",
        expires_in_hours=1
    )
    ws = MockWebSocket(f"/?token={token}&device_id=device-a")
    await ws_handler(ws)
    assert ws.closed
    assert ws.close_code == 4006
    assert ws.close_reason == "Billing grace period expired"

    # Reset tenant for subsequent tests
    async with conn.cursor() as cur:
        await cur.execute(
            "UPDATE tenants SET plan = 'starter', status = 'active', grace_period_ends_at = NULL WHERE id = %s",
            (DEMO_TENANT_ID,)
        )
    await conn.commit()


@pytest.mark.anyio
async def test_stripe_webhook_kiosk_grandfathering(client: AsyncClient, conn):
    # Ensure clean kiosks list
    async with conn.cursor() as cur:
        await cur.execute("DELETE FROM kiosks WHERE tenant_id = %s", (DEMO_TENANT_ID,))
        # Set plan to pro (max kiosks = 5)
        await cur.execute("UPDATE tenants SET plan = 'pro', status = 'active', max_kiosks = 5 WHERE id = %s", (DEMO_TENANT_ID,))
    await conn.commit()

    # Pair 2 kiosks under Pro
    admin_token = create_access_token(DEMO_TENANT_ID, 100, "admin")
    headers = {"Authorization": f"Bearer {admin_token}", "X-Tenant": "demo"}

    # Register Kiosk 1
    res1 = await client.post("/api/pairing/request", json={"name": "Grandfathered Kiosk 1"}, headers=headers)
    pin1 = res1.json()["pin"]
    verify_res1 = await client.post("/api/pairing/verify", json={"pin": pin1, "device_id": "device-kiosk-1"})
    token1 = verify_res1.json()["token"]
    kiosk_id1 = verify_res1.json()["kiosk_id"]

    # Register Kiosk 2
    res2 = await client.post("/api/pairing/request", json={"name": "Grandfathered Kiosk 2"}, headers=headers)
    pin2 = res2.json()["pin"]
    verify_res2 = await client.post("/api/pairing/verify", json={"pin": pin2, "device_id": "device-kiosk-2"})
    token2 = verify_res2.json()["token"]
    kiosk_id2 = verify_res2.json()["kiosk_id"]

    # Downgrade plan to starter (max kiosks = 1)
    async with conn.cursor() as cur:
        await cur.execute("UPDATE tenants SET plan = 'starter', max_kiosks = 1 WHERE id = %s", (DEMO_TENANT_ID,))
    await conn.commit()

    # 1. Existing kiosks connect via WS -> successfully connect (grandfathered)
    ws1 = MockWebSocket(f"/?token={token1}&device_id=device-kiosk-1")
    ws1.incoming_messages = []
    await ws_handler(ws1)
    assert not ws1.closed

    ws2 = MockWebSocket(f"/?token={token2}&device_id=device-kiosk-2")
    ws2.incoming_messages = []
    await ws_handler(ws2)
    assert not ws2.closed

    # 2. Attempt pairing a new kiosk -> returns 403 limits reached
    res3 = await client.post("/api/pairing/request", json={"name": "Kiosk 3"}, headers=headers)
    assert res3.status_code == 403
    assert "limit reached" in res3.json()["detail"].lower()

    # Reset
    async with conn.cursor() as cur:
        await cur.execute("DELETE FROM kiosks WHERE tenant_id = %s", (DEMO_TENANT_ID,))
    await conn.commit()
