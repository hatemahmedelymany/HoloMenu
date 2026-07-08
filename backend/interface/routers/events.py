"""
Server-Sent Events (SSE) router.
"""
import asyncio
from typing import AsyncGenerator
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from backend.infrastructure.events.sse import _sse_subscribers

router = APIRouter(tags=["events"])


@router.get("/api/events/stream")
async def events_stream(request: Request):
    """Server-Sent Events endpoint. Each client gets its own queue."""
    tenant_id = request.state.tenant_id
    q: asyncio.Queue = asyncio.Queue(maxsize=50)
    if tenant_id not in _sse_subscribers:
        _sse_subscribers[tenant_id] = []
    _sse_subscribers[tenant_id].append(q)

    async def generator() -> AsyncGenerator[str, None]:
        # Send initial ping so browser considers connection established
        yield "data: {\"type\": \"connected\"}\n\n"
        try:
            while True:
                try:
                    payload = await asyncio.wait_for(q.get(), timeout=25)
                    yield f"data: {payload}\n\n"
                except asyncio.TimeoutError:
                    # Keepalive comment every 25s
                    yield ": keepalive\n\n"
        finally:
            if tenant_id in _sse_subscribers and q in _sse_subscribers[tenant_id]:
                _sse_subscribers[tenant_id].remove(q)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "http://localhost:8000",
        },
    )
