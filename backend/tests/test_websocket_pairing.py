import pytest
import os
import json
import subprocess
import sys
import jwt
from datetime import datetime, timedelta
from httpx import AsyncClient

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

    # 2. Verify pairing with valid PIN
    res_verify = await client.post(
        "/api/pairing/verify",
        json={"pin": pin}
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
        json={"pin": "000000"}
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

    res_verify1 = await client.post("/api/pairing/verify", json={"pin": pin1})
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
async def test_websocket_auth_handshake():
    # 1. Connection with no token -> 4001 closing code
    ws_no_token = MockWebSocket("/")
    await ws_handler(ws_no_token)
    assert ws_no_token.closed
    assert ws_no_token.close_code == 4001

    # 2. Connection with invalid token -> 4003 closing code
    ws_invalid = MockWebSocket("/?token=invalid_jwt_token")
    await ws_handler(ws_invalid)
    assert ws_invalid.closed
    assert ws_invalid.close_code == 4003

    # 3. Connection with expired token -> 4002 closing code
    expired_token = create_websocket_session_token(
        DEMO_TENANT_ID,
        "mock-kiosk-id",
        expires_in_hours=-1
    )
    ws_expired = MockWebSocket(f"/?token={expired_token}")
    await ws_handler(ws_expired)
    assert ws_expired.closed
    assert ws_expired.close_code == 4002

    # 4. Connection with valid token -> successful handshake
    valid_token = create_websocket_session_token(
        DEMO_TENANT_ID,
        "mock-kiosk-id",
        expires_in_hours=1
    )
    ws_valid = MockWebSocket(f"/?token={valid_token}")
    # Prime incoming message flow to exit handler after connection
    ws_valid.incoming_messages = []
    await ws_handler(ws_valid)
    assert not ws_valid.closed


@pytest.mark.anyio
async def test_websocket_schema_validation():
    valid_token = create_websocket_session_token(
        DEMO_TENANT_ID,
        "mock-kiosk-id",
        expires_in_hours=1
    )

    # 1. Valid command start_order -> accepted
    ws = MockWebSocket(f"/?token={valid_token}")
    ws.incoming_messages = ['{"cmd": "start_order"}']
    await ws_handler(ws)
    # The handler sends an initial engine_mode event, and does not return an error
    errors = [json.loads(m) for m in ws.sent_messages if "error" in m]
    assert len(errors) == 0

    # 2. Malformed command -> returns error
    ws_bad = MockWebSocket(f"/?token={valid_token}")
    ws_bad.incoming_messages = ['{"cmd": "bad_command"}']
    await ws_handler(ws_bad)
    errors = [json.loads(m) for m in ws_bad.sent_messages if "error" in m]
    assert len(errors) == 1
    assert errors[0]["error"] == "Message malformed"

    # 3. Payload with injected extra keys -> returns error
    ws_extra = MockWebSocket(f"/?token={valid_token}")
    ws_extra.incoming_messages = ['{"cmd": "start_order", "extra_param": "malicious"}']
    await ws_handler(ws_extra)
    errors = [json.loads(m) for m in ws_extra.sent_messages if "error" in m]
    assert len(errors) == 1
    assert errors[0]["error"] == "Message malformed"


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
