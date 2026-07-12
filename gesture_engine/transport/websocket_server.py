"""
WebSocket connection management and server lifecycle.
"""
import time
import json
import asyncio
from urllib.parse import urlparse, parse_qs
import jwt

from gesture_engine.state import CONNECTED_CLIENTS, ENGINE_MODE
import gesture_engine.state as engine_state
from gesture_engine.transport.commands import handle_command
from gesture_engine.config.settings import DISABLE_WS_AUTH
from backend.infrastructure.security.auth import decode_websocket_session_token

try:
    import websockets
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False


import aiomysql
from backend.infrastructure.config.settings import DB_CONFIG
from backend.infrastructure.database.mysql_audit_repo import MysqlAuditRepo

ALLOWED_ORIGINS = {
    "http://localhost:8000", "http://127.0.0.1:8000",
    "http://localhost:8080", "http://127.0.0.1:8080",
    "tauri://localhost", "http://tauri.localhost", "https://tauri.localhost"
}


def validate_command_payload(data: dict) -> bool:
    """Validate that incoming websocket messages follow the strict expected schema."""
    if not isinstance(data, dict):
        return False
    if "cmd" not in data:
        return False
    if data["cmd"] not in ("start_order", "end_session"):
        return False
    if "seq" not in data:
        return False
    if len(data) > 2:
        return False
    return True


async def log_ws_audit_event(tenant_id: str, action: str, error_msg: str = None, device_id: str = None, kiosk_id: str = None):
    try:
        conn = await aiomysql.connect(**DB_CONFIG)
        try:
            repo = MysqlAuditRepo(conn)
            await repo.log_audit_event(
                tenant_id=tenant_id,
                action=action,
                target_type="kiosk",
                target_id=kiosk_id,
                after_state={"error": error_msg, "device_id": device_id} if error_msg else {"device_id": device_id}
            )
        finally:
            conn.close()
    except Exception as e:
        print(f"Failed to log WS audit event to database: {e}")


async def broadcast_event(event_dict: dict):
    """Broadcasting utility wrapper for state change monitoring."""
    # Update state activity timer
    engine_state.LAST_ACTIVITY_TIME = time.time()

    if not WEBSOCKETS_AVAILABLE:
        print(f"[WS-off] {json.dumps(event_dict)}")
        return

    if CONNECTED_CLIENTS:
        message = json.dumps(event_dict)
        for ws in list(CONNECTED_CLIENTS):
            try:
                await ws.send(message)
            except websockets.exceptions.ConnectionClosed:
                CONNECTED_CLIENTS.discard(ws)
            except Exception as e:
                print(f"WS send error: {e}")


async def ws_handler(websocket):
    """Handles incoming client web socket events flow with authentication and schema checks."""
    tenant_id = "d4444444-4444-4444-4444-444444444444"
    kiosk_id = None
    device_id = None

    # 1. Origin Header check
    origin = websocket.request_headers.get("Origin")
    if origin and origin not in ALLOWED_ORIGINS:
        print(f"WS connection rejected: unauthorized origin '{origin}'")
        await log_ws_audit_event(
            tenant_id=tenant_id,
            action="ws_connection_failed",
            error_msg=f"Unauthorized origin: {origin}"
        )
        await websocket.close(code=4004, reason="Unauthorized origin")
        return

    # Extract parameters
    query = urlparse(websocket.path).query
    params = parse_qs(query)
    token = params.get("token", [None])[0]
    device_id = params.get("device_id", [None])[0]

    if not DISABLE_WS_AUTH:
        if not token:
            print("WS connection rejected: missing token")
            await log_ws_audit_event(
                tenant_id=tenant_id,
                action="ws_connection_failed",
                error_msg="Authentication token missing",
                device_id=device_id
            )
            await websocket.close(code=4001, reason="Authentication token missing")
            return

        try:
            payload = decode_websocket_session_token(token)
            tenant_id = payload.get("tenant_id")
            kiosk_id = payload.get("sub")
            token_device_id = payload.get("device_id")

            # Validate device binding
            if not device_id or device_id != token_device_id:
                print("WS connection rejected: device binding mismatch")
                await log_ws_audit_event(
                    tenant_id=tenant_id or "d4444444-4444-4444-4444-444444444444",
                    action="ws_connection_failed",
                    error_msg="Device ID mismatch",
                    device_id=device_id,
                    kiosk_id=kiosk_id
                )
                await websocket.close(code=4003, reason="Device ID mismatch")
                return

            # Gating: Query tenant billing status from DB
            try:
                conn_billing = await aiomysql.connect(**DB_CONFIG)
                try:
                    async with conn_billing.cursor(aiomysql.DictCursor) as cur:
                        await cur.execute("SELECT status, grace_period_ends_at, deleted_at FROM tenants WHERE id = %s", (tenant_id,))
                        tenant = await cur.fetchone()
                        if not tenant or tenant["status"] != "active" or tenant["deleted_at"] is not None:
                            status_val = tenant["status"] if tenant else "not_found"
                            is_deleted = tenant["deleted_at"] is not None if tenant else False
                            print(f"WS connection rejected: tenant suspended or deactivated (status: {status_val}, deleted: {is_deleted})")
                            await log_ws_audit_event(
                                tenant_id=tenant_id,
                                action="ws_connection_failed",
                                error_msg="Tenant subscription suspended or deactivated",
                                device_id=device_id,
                                kiosk_id=kiosk_id
                            )
                            await websocket.close(code=4006, reason="Tenant subscription suspended or deactivated")
                            return
                        if tenant["grace_period_ends_at"]:
                            from datetime import datetime
                            if datetime.utcnow() > tenant["grace_period_ends_at"]:
                                print("WS connection rejected: tenant grace period expired")
                                await log_ws_audit_event(
                                    tenant_id=tenant_id,
                                    action="ws_connection_failed",
                                    error_msg="Billing grace period expired",
                                    device_id=device_id,
                                    kiosk_id=kiosk_id
                                )
                                await websocket.close(code=4006, reason="Billing grace period expired")
                                return
                finally:
                    conn_billing.close()
            except Exception as e:
                print(f"Failed to query billing status from DB during WS handshake: {e}")

            print(f"WS connection authenticated successfully for tenant {tenant_id} / kiosk {kiosk_id} / device {device_id}")
            await log_ws_audit_event(
                tenant_id=tenant_id,
                action="ws_connection_success",
                device_id=device_id,
                kiosk_id=kiosk_id
            )
        except jwt.ExpiredSignatureError:
            print("WS connection rejected: token expired")
            await log_ws_audit_event(
                tenant_id="d4444444-4444-4444-4444-444444444444",
                action="ws_connection_failed",
                error_msg="Token has expired",
                device_id=device_id
            )
            await websocket.close(code=4002, reason="Token has expired")
            return
        except jwt.PyJWTError as e:
            print(f"WS connection rejected: invalid token: {e}")
            await log_ws_audit_event(
                tenant_id="d4444444-4444-4444-4444-444444444444",
                action="ws_connection_failed",
                error_msg=f"Invalid token: {e}",
                device_id=device_id
            )
            await websocket.close(code=4003, reason="Invalid token")
            return

    CONNECTED_CLIENTS.add(websocket)
    print(f"WS client connected: {websocket.remote_address}")

    # Send current mode to newly connected client
    await websocket.send(json.dumps({"event": "engine_mode", "mode": engine_state.ENGINE_MODE}))

    last_seen_seq = 0

    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                if not validate_command_payload(data):
                    print(f"WS payload rejected (malformed): {message}")
                    await websocket.send(json.dumps({"error": "Message malformed"}))
                    continue

                # Replay protection sequence check
                msg_seq = data.get("seq")
                if not isinstance(msg_seq, int) or msg_seq != last_seen_seq + 1:
                    print(f"WS connection closed: sequence mismatch. Expected {last_seen_seq + 1}, got {msg_seq}")
                    await log_ws_audit_event(
                        tenant_id=tenant_id,
                        action="ws_connection_failed",
                        error_msg=f"Sequence number mismatch: expected {last_seen_seq + 1}, got {msg_seq}",
                        device_id=device_id,
                        kiosk_id=kiosk_id
                    )
                    await websocket.close(code=4005, reason="Sequence number mismatch")
                    return

                last_seen_seq = msg_seq
                await handle_command(data, broadcast_event)
            except json.JSONDecodeError:
                await websocket.send(json.dumps({"error": "Message malformed"}))
    except websockets.exceptions.ConnectionClosedOK:
        pass
    except Exception as e:
        print(f"WS client error: {e}")
    finally:
        CONNECTED_CLIENTS.discard(websocket)
        print(f"WS client disconnected: {websocket.remote_address}")
