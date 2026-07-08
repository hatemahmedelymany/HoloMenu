"""
WebSocket connection management and server lifecycle.
"""
import time
import json
import asyncio
from gesture_engine.state import CONNECTED_CLIENTS, ENGINE_MODE
import gesture_engine.state as engine_state
from gesture_engine.transport.commands import handle_command

try:
    import websockets
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False


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
    """Handles incoming client web socket events flow."""
    CONNECTED_CLIENTS.add(websocket)
    print(f"WS client connected: {websocket.remote_address}")

    # Send current mode to newly connected client
    await websocket.send(json.dumps({"event": "engine_mode", "mode": engine_state.ENGINE_MODE}))

    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                await handle_command(data, broadcast_event)
            except json.JSONDecodeError:
                pass
    except websockets.exceptions.ConnectionClosedOK:
        pass
    except Exception as e:
        print(f"WS client error: {e}")
    finally:
        CONNECTED_CLIENTS.discard(websocket)
        print(f"WS client disconnected: {websocket.remote_address}")
