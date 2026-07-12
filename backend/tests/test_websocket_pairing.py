import pytest
import os
import json
import subprocess
import sys
import jwt
from datetime import datetime, timedelta
from httpx import AsyncClient
import aiomysql

from backend.infrastructure.security.auth import create_access_token, create_websocket_session_token
from backend.application.use_cases.pairing import PENDING_PAIRS
from gesture_engine.transport.websocket_server import ws_handler, validate_command_payload

DEMO_TENANT_ID = "d4444444-4444-4444-4444-444444444444"

# Mock WebSocket connection class to test the handler in isolation
class MockWebSocket:
    def __init__(self, path: str):
        self.path = path
        self.closed = False
        self.close_code = None
        self.close_reason = None
        self.sent_messages = []
        self.incoming_messages = []
        self.request_headers = {}
        self.remote_address = ("127.0.0.1", 54321)

    async def send(self, message: str):
        self.sent_messages.append(message)

    async def close(self, code: int, reason: str = ""):
        self.closed = True
        self.close_code = code
        self.close_reason = reason

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.incoming_messages:
            raise StopAsyncIteration
        return self.incoming_messages.pop(0)


@pytest.mark.anyio
async def test_pairing_request_and_verify_flow(client: AsyncClient, conn):
    admin_token = create_access_token(DEMO_TENANT_ID, 100, "admin")
    headers = {"Authorization": f"Bearer {admin_token}", "X-Tenant": "demo"}

    # 1. Successful pairing PIN request (Admin role)
    res = await client.post(
        "/api/pairing/request",
        json={"name": "Kiosk #1"},
        headers=headers
    )
    assert res.status_code == 200
    data = res.json()
    assert "pin" in data
    assert len(data["pin"]) == 6
    pin = data["pin"]

    # 2. Verify pairing with valid PIN and device ID
    res_verify = await client.post(
        "/api/pairing/verify",
        json={"pin": pin, "device_id": "test-device-123"}
    )
    assert res_verify.status_code == 200
    verify_data = res_verify.json()
    assert "token" in verify_data
    assert "kiosk_id" in verify_data
    assert verify_data["name"] == "Kiosk #1"
    assert "secret" in verify_data


@pytest.mark.anyio
async def test_pairing_request_role_restriction(client: AsyncClient, conn):
    chef_token = create_access_token(DEMO_TENANT_ID, 101, "chef")
    headers = {"Authorization": f"Bearer {chef_token}", "X-Tenant": "demo"}

    # Operator with 'chef' role attempts to request pairing PIN -> 403 Forbidden
    res = await client.post(
        "/api/pairing/request",
        json={"name": "Chef Kiosk"},
        headers=headers
    )
    assert res.status_code == 403


@pytest.mark.anyio
async def test_pairing_verify_invalid_pin(client: AsyncClient):
    # Attempt verification using incorrect PIN -> 400 Bad Request
    res = await client.post(
        "/api/pairing/verify",
        json={"pin": "000000", "device_id": "test-device-123"}
    )
    assert res.status_code == 400
    assert "Invalid or expired" in res.json()["detail"]


@pytest.mark.anyio
async def test_pairing_limits_gating(client: AsyncClient, conn):
    # Set the demo tenant's max kiosks to 1 temporarily to test limits gating
    async with conn.cursor() as cur:
        await cur.execute(
            "UPDATE tenants SET max_kiosks = 1 WHERE id = %s",
            (DEMO_TENANT_ID,)
        )
        # Clean active kiosks list for demo tenant
        await cur.execute(
            "DELETE FROM kiosks WHERE tenant_id = %s",
            (DEMO_TENANT_ID,)
        )

    admin_token = create_access_token(DEMO_TENANT_ID, 100, "admin")
    headers = {"Authorization": f"Bearer {admin_token}", "X-Tenant": "demo"}

    # 1. Request and verify the first kiosk -> Should succeed (count = 1)
    res1 = await client.post(
        "/api/pairing/request",
        json={"name": "Kiosk 1"},
        headers=headers
    )
    assert res1.status_code == 200
    pin1 = res1.json()["pin"]

    res_verify1 = await client.post(
        "/api/pairing/verify",
        json={"pin": pin1, "device_id": "test-device-1"}
    )
    assert res_verify1.status_code == 200

    # 2. Attempt requesting a second kiosk -> Should fail with 403 (count exceeds max_kiosks=1)
    res2 = await client.post(
        "/api/pairing/request",
        json={"name": "Kiosk 2"},
        headers=headers
    )
    assert res2.status_code == 403
    assert "limit reached" in res2.json()["detail"].lower()

    # Reset max_kiosks back to 5 for other tests
    async with conn.cursor() as cur:
        await cur.execute(
            "UPDATE tenants SET max_kiosks = 5 WHERE id = %s",
            (DEMO_TENANT_ID,)
        )


@pytest.mark.anyio
async def test_pairing_rate_limiting_and_pin_exhaustion(client: AsyncClient, conn):
    admin_token = create_access_token(DEMO_TENANT_ID, 100, "admin")
    headers = {"Authorization": f"Bearer {admin_token}", "X-Tenant": "demo"}

    # Request pairing PIN
    res = await client.post(
        "/api/pairing/request",
        json={"name": "Kiosk PIN Exhaust Test"},
        headers=headers
    )
    assert res.status_code == 200
    pin = res.json()["pin"]

    # Perform 5 failed PIN attempts using correct format but wrong value
    # (Note: failed verifications must use incorrect PINs so they increment the target PIN's attempt counter if it matches,
    # or fail directly. Wait! The attempt counter is incremented only if the PIN is in PENDING_PAIRS. So we must verify the actual PIN but fail other parameters, or use a wrong PIN and check fallback, or verify correct PIN but with wrong signature.
    # Wait, the PairingUseCase verify_pairing logic increments the attempt counter of the PIN if it IS in PENDING_PAIRS.
    # So we can verify that specific PIN, but fail it by reaching the attempts limit on it.
    # Let's check: if we try verifying the CORRECT pin, but say, database limits fail? Or we can just call verify_pairing Use Case directly 5 times!)
    from backend.infrastructure.database.mysql_kiosk_repo import MysqlKioskRepo
    from backend.application.use_cases.pairing import PairingUseCase
    
    repo = MysqlKioskRepo(conn)
    use_case = PairingUseCase(repo)
    
    # 5 attempts with incorrect PIN will fail directly and use the fallback.
    # If we call use_case.verify_pairing with the CORRECT pin but fail it:
    # Wait! If we call it with correct PIN, it succeeds and deletes the PIN!
    # So to test attempt exhaustion, we can simulate verification failure. How?
    # In verify_pairing, attempts is incremented every time. If we verify a PIN that is in PENDING_PAIRS but we trigger a database error or limits error?
    # Wait! In verify_pairing, if we pass a PIN that is in PENDING_PAIRS, it increments attempts.
    # Let's say the limit is temporarily set to exceed max_kiosks (so it raises PermissionError). Each attempt will fail with PermissionError but increment attempts!
    # Let's test that!
    async with conn.cursor() as cur:
        await cur.execute("UPDATE tenants SET max_kiosks = 0 WHERE id = %s", (DEMO_TENANT_ID,))
    
    try:
        # Attempts 1 to 5 will raise PermissionError
        for _ in range(5):
            with pytest.raises(PermissionError):
                await use_case.verify_pairing(pin, "device-exhaust-test")
        
        # Attempt 6 will raise ValueError (exhausted/deleted)
        with pytest.raises(ValueError, match="Invalid or expired"):
            await use_case.verify_pairing(pin, "device-exhaust-test")
    finally:
        async with conn.cursor() as cur:
            await cur.execute("UPDATE tenants SET max_kiosks = 5 WHERE id = %s", (DEMO_TENANT_ID,))


@pytest.mark.anyio
async def test_websocket_auth_handshake():
    # 1. Connection with no token -> 4001 closing code
    ws_no_token = MockWebSocket("/")
    await ws_handler(ws_no_token)
    assert ws_no_token.closed
    assert ws_no_token.close_code == 4001

    # 2. Connection with invalid token -> 4003 closing code
    ws_invalid = MockWebSocket("/?token=invalid_jwt_token&device_id=test-device")
    await ws_handler(ws_invalid)
    assert ws_invalid.closed
    assert ws_invalid.close_code == 4003

    # 3. Connection with expired token -> 4002 closing code
    expired_token = create_websocket_session_token(
        DEMO_TENANT_ID,
        "mock-kiosk-id",
        "mock-device-id",
        expires_in_hours=-1
    )
    ws_expired = MockWebSocket(f"/?token={expired_token}&device_id=mock-device-id")
    await ws_handler(ws_expired)
    assert ws_expired.closed
    assert ws_expired.close_code == 4002

    # 4. Connection with valid token -> successful handshake
    valid_token = create_websocket_session_token(
        DEMO_TENANT_ID,
        "mock-kiosk-id",
        "mock-device-id",
        expires_in_hours=1
    )
    ws_valid = MockWebSocket(f"/?token={valid_token}&device_id=mock-device-id")
    ws_valid.incoming_messages = []
    await ws_handler(ws_valid)
    assert not ws_valid.closed


@pytest.mark.anyio
async def test_websocket_device_binding():
    token = create_websocket_session_token(
        DEMO_TENANT_ID,
        "mock-kiosk-id",
        "device-a",
        expires_in_hours=1
    )

    # 1. Connection with missing device_id query parameter -> 4003 code
    ws_missing = MockWebSocket(f"/?token={token}")
    await ws_handler(ws_missing)
    assert ws_missing.closed
    assert ws_missing.close_code == 4003

    # 2. Connection with mismatched device_id query parameter -> 4003 code
    ws_mismatched = MockWebSocket(f"/?token={token}&device_id=device-b")
    await ws_handler(ws_mismatched)
    assert ws_mismatched.closed
    assert ws_mismatched.close_code == 4003

    # 3. Connection with correct device_id -> successful
    ws_correct = MockWebSocket(f"/?token={token}&device_id=device-a")
    ws_correct.incoming_messages = []
    await ws_handler(ws_correct)
    assert not ws_correct.closed


@pytest.mark.anyio
async def test_websocket_unauthorized_origin():
    token = create_websocket_session_token(
        DEMO_TENANT_ID,
        "mock-kiosk-id",
        "device-a",
        expires_in_hours=1
    )
    ws = MockWebSocket(f"/?token={token}&device_id=device-a")
    ws.request_headers = {"Origin": "http://malicious-site.com"}
    await ws_handler(ws)
    assert ws.closed
    assert ws.close_code == 4004


@pytest.mark.anyio
async def test_websocket_schema_validation():
    valid_token = create_websocket_session_token(
        DEMO_TENANT_ID,
        "mock-kiosk-id",
        "mock-device-id",
        expires_in_hours=1
    )

    # 1. Valid command start_order with seq -> accepted
    ws = MockWebSocket(f"/?token={valid_token}&device_id=mock-device-id")
    ws.incoming_messages = ['{"cmd": "start_order", "seq": 1}']
    await ws_handler(ws)
    errors = [json.loads(m) for m in ws.sent_messages if "error" in m]
    assert len(errors) == 0

    # 2. Malformed command -> returns error
    ws_bad = MockWebSocket(f"/?token={valid_token}&device_id=mock-device-id")
    ws_bad.incoming_messages = ['{"cmd": "bad_command", "seq": 1}']
    await ws_handler(ws_bad)
    errors = [json.loads(m) for m in ws_bad.sent_messages if "error" in m]
    assert len(errors) == 1
    assert errors[0]["error"] == "Message malformed"

    # 3. Payload with injected extra keys -> returns error
    ws_extra = MockWebSocket(f"/?token={valid_token}&device_id=mock-device-id")
    ws_extra.incoming_messages = ['{"cmd": "start_order", "seq": 1, "extra_param": "malicious"}']
    await ws_handler(ws_extra)
    errors = [json.loads(m) for m in ws_extra.sent_messages if "error" in m]
    assert len(errors) == 1
    assert errors[0]["error"] == "Message malformed"


@pytest.mark.anyio
async def test_websocket_replay_protection_sequence():
    token = create_websocket_session_token(
        DEMO_TENANT_ID,
        "mock-kiosk-id",
        "device-a",
        expires_in_hours=1
    )

    # 1. First message has seq=1 -> accepted
    ws = MockWebSocket(f"/?token={token}&device_id=device-a")
    ws.incoming_messages = ['{"cmd": "start_order", "seq": 1}']
    await ws_handler(ws)
    assert not ws.closed

    # 2. First message has seq=2 (expected 1) -> closed with 4005
    ws_bad_start = MockWebSocket(f"/?token={token}&device_id=device-a")
    ws_bad_start.incoming_messages = ['{"cmd": "start_order", "seq": 2}']
    await ws_handler(ws_bad_start)
    assert ws_bad_start.closed
    assert ws_bad_start.close_code == 4005

    # 3. Sequence gaps: first message seq=1, second message seq=3 (expected 2) -> closed with 4005
    ws_gap = MockWebSocket(f"/?token={token}&device_id=device-a")
    ws_gap.incoming_messages = [
        '{"cmd": "start_order", "seq": 1}',
        '{"cmd": "end_session", "seq": 3}'
    ]
    await ws_handler(ws_gap)
    assert ws_gap.closed
    assert ws_gap.close_code == 4005


@pytest.mark.anyio
async def test_websocket_active_order_desync_reconnect_simulation(client: AsyncClient, conn):
    # Insert chef admin to satisfy audit log/order constraints
    async with conn.cursor() as cur:
        await cur.execute(
            "INSERT IGNORE INTO admins (id, tenant_id, username, password_hash, role) VALUES (%s, %s, %s, %s, %s)",
            (9999, DEMO_TENANT_ID, "chef_reconnect_test", "hash", "chef")
        )

    chef_token = create_access_token(DEMO_TENANT_ID, 9999, "chef")
    headers = {
        "Authorization": f"Bearer {chef_token}",
        "X-Tenant": "demo"
    }

    # 1. Create a real order in the database via the API client
    resp_create = await client.post("/api/orders", headers=headers)
    assert resp_create.status_code == 201
    order = resp_create.json()
    order_uid = order["order_uid"]
    assert order["status"] == "pending"

    # Count matching orders in DB initially
    async with conn.cursor(aiomysql.DictCursor) as cur:
        await cur.execute("SELECT id, status FROM orders WHERE order_uid = %s", (order_uid,))
        rows_before = await cur.fetchall()
        assert len(rows_before) == 1
        assert rows_before[0]["status"] == "pending"

    # 2. Simulate WebSocket token generation and initial pairing context
    ws_token = create_websocket_session_token(
        DEMO_TENANT_ID,
        "mock-kiosk-id",
        "device-a",
        expires_in_hours=1
    )

    # 3. Simulate sequence mismatch error (client sends seq=3 instead of 2)
    # This triggers server disconnect with code 4005
    ws2 = MockWebSocket(f"/?token={ws_token}&device_id=device-a")
    # Set expected server state to expect seq=2 by sending a valid seq=1 first
    ws2.incoming_messages = [
        '{"cmd": "start_order", "seq": 1}',
        '{"cmd": "end_session", "seq": 3}' # gap! expected 2
    ]
    await ws_handler(ws2)
    assert ws2.closed
    assert ws2.close_code == 4005

    # 4. Reconnect Simulator: Client receives disconnect.
    # It reconnects with the SAME token & device_id, resetting sequence back to 1.
    ws3 = MockWebSocket(f"/?token={ws_token}&device_id=device-a")
    ws3.incoming_messages = [
        '{"cmd": "start_order", "seq": 1}'
    ]
    await ws_handler(ws3)
    
    # Assert socket remains open
    assert not ws3.closed

    # 5. Query the actual orders table afterward and assert:
    # - The same order ID still exists
    # - Its status is unchanged ("pending")
    # - No duplicate order was created for this session
    async with conn.cursor(aiomysql.DictCursor) as cur:
        await cur.execute("SELECT id, status FROM orders WHERE order_uid = %s", (order_uid,))
        rows_after = await cur.fetchall()
        assert len(rows_after) == 1
        assert rows_after[0]["status"] == "pending"
        assert rows_after[0]["id"] == rows_before[0]["id"]


@pytest.mark.anyio
async def test_ws_audit_logging_on_failure(conn):
    # connection failure should insert an audit log record
    from backend.infrastructure.config.settings import DB_CONFIG
    ws_no_token = MockWebSocket("/")
    
    await ws_handler(ws_no_token)
    assert ws_no_token.closed

    # Query audit logs using a fresh connection to avoid repeatable-read snapshot isolation issues
    conn2 = await aiomysql.connect(**DB_CONFIG)
    try:
        async with conn2.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT action, target_type, after_state FROM audit_logs ORDER BY id DESC LIMIT 1")
            row = await cur.fetchone()
            assert row is not None
            assert row["action"] == "ws_connection_failed"
            assert row["target_type"] == "kiosk"
            assert "Authentication token missing" in row["after_state"]
    finally:
        conn2.close()


def test_production_auth_safeguard():
    # Attempting to load settings when ENV=production and DISABLE_WS_AUTH=true must raise RuntimeError
    env = os.environ.copy()
    env["ENV"] = "production"
    env["DISABLE_WS_AUTH"] = "true"
    
    cmd = [sys.executable, "-c", "import backend.infrastructure.config.settings"]
    res = subprocess.run(cmd, env=env, capture_output=True, text=True)
    assert res.returncode != 0
    assert "RuntimeError: Cannot disable WebSocket auth in production" in res.stderr

    # Same check for gesture engine settings file
    cmd_ge = [sys.executable, "-c", "import gesture_engine.config.settings"]
    res_ge = subprocess.run(cmd_ge, env=env, capture_output=True, text=True)
    assert res_ge.returncode != 0
    assert "RuntimeError: Cannot disable WebSocket auth in production" in res_ge.stderr
