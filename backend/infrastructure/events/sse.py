"""
Server-Sent Events (SSE) state management and dispatch utility.
"""
import asyncio
import json

# Thread-safe queues partitioned by tenant_id
_sse_subscribers: dict[str, list[asyncio.Queue]] = {}


async def broadcast_event(tenant_id: str, event_type: str, data: dict) -> None:
    """Push a JSON event to all connected SSE clients belonging to tenant_id."""
    payload = json.dumps({"type": event_type, **data})
    queues = _sse_subscribers.get(tenant_id, [])
    dead = []
    for q in queues:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        if q in queues:
            queues.remove(q)
