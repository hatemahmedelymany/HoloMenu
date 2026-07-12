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


def validate_command_payload(data: dict) -> bool:
    """Validate that incoming websocket messages follow the strict expected schema."""
    if not isinstance(data, dict):
        return False
    if "cmd" not in data:
        return False
    if data["cmd"] not in ("start_order", "end_session"):
        return False
    if len(data) > 1:
        return False
    return True


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
    if not DISABLE_WS_AUTH:
        # Extract token from path query parameters
        query = urlparse(websocket.path).query
        params = parse_qs(query)
        token = params.get("token", [None])[0]

        if not token:
            print("WS connection rejected: missing token")
            await websocket.close(code=4001, reason="Authentication token missing")
            return

        try:
            payload = decode_websocket_session_token(token)
            print(f"WS connection authenticated successfully for tenant {payload.get('tenant_id')} / kiosk {payload.get('sub')}")
        except jwt.ExpiredSignatureError:
            print("WS connection rejected: token expired")
            await websocket.close(code=4002, reason="Token has expired")
            return
        except jwt.PyJWTError as e:
            print(f"WS connection rejected: invalid token: {e}")
            await websocket.close(code=4003, reason="Invalid token")
            return

    CONNECTED_CLIENTS.add(websocket)
    print(f"WS client connected: {websocket.remote_address}")

    # Send current mode to newly connected client
    await websocket.send(json.dumps({"event": "engine_mode", "mode": engine_state.ENGINE_MODE}))

    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                if not validate_command_payload(data):
                    print(f"WS payload rejected (malformed): {message}")
                    await websocket.send(json.dumps({"error": "Message malformed"}))
                    continue
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
