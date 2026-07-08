"""
WebSocket client commands dispatcher.
"""
import json
from gesture_engine.state import set_engine_mode


async def handle_command(data: dict, broadcast_callback):
    """Router for websocket commands."""
    cmd = data.get("cmd")
    if cmd == "start_order":
        set_engine_mode("active")
        await broadcast_callback({"event": "engine_mode", "mode": "active"})
    elif cmd == "end_session":
        set_engine_mode("idle")
        await broadcast_callback({"event": "engine_mode", "mode": "idle"})
