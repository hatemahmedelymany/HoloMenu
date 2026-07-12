import asyncio
import os
import uuid
import time
from contextlib import asynccontextmanager
from typing import Optional

import aiomysql
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from contextvars import ContextVar
from prometheus_client import Counter, Histogram, generate_latest

from backend.infrastructure.logging.json_logger import logger, request_id_ctx
from backend.infrastructure.security.sentry import init_sentry
from backend.infrastructure.monitoring.prometheus import REQUEST_COUNT, REQUEST_LATENCY

init_sentry()

from backend.infrastructure.security.limiter import limiter



async def get_tenant_by_subdomain(subdomain: str) -> Optional[dict]:
    """Helper to fetch tenant by subdomain. Uses the raw sql executor direct connection."""
    # Since pool is not local, we acquire a temporary connection to avoid circular dependency.
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT id, subdomain, status FROM tenants WHERE subdomain = %s",
                (subdomain,),
            )
            return await cur.fetchone()


from backend.interface.routers.orders import router as orders_router
from backend.interface.routers.chef import router as chef_router
from backend.interface.routers.cashier import router as cashier_router
from backend.interface.routers.products import router as products_router
from backend.interface.routers.departments import router as departments_router
from backend.interface.routers.auth import router as auth_router
from backend.interface.routers.admin import router as admin_router
from backend.interface.routers.analytics import router as analytics_router
from backend.interface.routers.events import router as events_router
from backend.interface.routers.pairing import router as pairing_router


load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))


from backend.infrastructure.config.settings import DB_CONFIG

import backend.infrastructure.database.pool as db_pool
pool: Optional[aiomysql.Pool] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool
    db_pool.pool = await aiomysql.create_pool(minsize=2, maxsize=10, **DB_CONFIG)
    pool = db_pool.pool
    print("DB pool created")
    
    # Auto-seed default admin if missing
    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT COUNT(*) FROM admins WHERE username = 'admin'")
                row = await cur.fetchone()
                if not row or row[0] == 0:
                    import bcrypt
                    admin_hash = bcrypt.hashpw(b"admin123", bcrypt.gensalt()).decode()
                    DEMO_TENANT_ID = "d4444444-4444-4444-4444-444444444444"
                    await cur.execute(
                        "INSERT INTO admins (username, password_hash, role, tenant_id) VALUES (%s, %s, %s, %s)",
                        ("admin", admin_hash, "admin", DEMO_TENANT_ID)
                    )
                    print("[Auto-Seed] Default admin seeded under demo tenant (username: admin, password: admin123)")
    except Exception as e:
        print(f"[Auto-Seed Warning] Could not check/seed default admin: {e}")
        
    yield
    pool.close()
    await pool.wait_closed()
    print("DB pool closed")


app = FastAPI(title="HoloMenu API", version="2.0.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.include_router(orders_router)
app.include_router(chef_router)
app.include_router(cashier_router)
app.include_router(products_router)
app.include_router(departments_router)
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(analytics_router)
app.include_router(events_router)
app.include_router(pairing_router)


from fastapi import Response
from prometheus_client import CONTENT_TYPE_LATEST

@app.get("/api/health")
async def health_check():
    try:
        if pool is None:
            raise Exception("Database pool is not initialized")
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("SELECT 1")
                await cur.execute("SELECT status, COUNT(*) as count FROM orders GROUP BY status")
                rows = await cur.fetchall()
                status_counts = {row["status"]: row["count"] for row in rows}
                return {
                    "status": "ok",
                    "database": "connected",
                    "status_counts": status_counts
                }
    except Exception as e:
        logger.error("health_check_failed", extra={"error": str(e)})
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "database": "disconnected",
                "detail": str(e)
            }
        )

@app.get("/api/metrics")
async def metrics_endpoint():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

from backend.infrastructure.config.settings import CORS_ALLOWED_ORIGINS

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Middleware: JSON logging & Metrics (Section 2 & 3) ───────────────────────

@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    req_id = str(uuid.uuid4())
    request_id_ctx.set(req_id)
    start = time.time()
    
    # Initialize request state user_id
    request.state.user_id = None
    
    response = await call_next(request)
    elapsed_ms = round((time.time() - start) * 1000, 2)

    route_path = f"{request.method} {request.url.path}"
    
    # Log requests
    logger.info(
        "request_completed",
        extra={
            "tenant_id": getattr(request.state, "tenant_id", None),
            "user_id": getattr(request.state, "user_id", None),
            "route": route_path,
            "status_code": response.status_code,
            "execution_time_ms": elapsed_ms,
        },
    )
    
    # Update Prometheus metrics (Section 3.3)
    REQUEST_COUNT.labels(route=route_path, status_code=str(response.status_code)).inc()
    REQUEST_LATENCY.labels(route=route_path).observe(elapsed_ms)
    
    response.headers["X-Request-ID"] = req_id
    return response


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    return response


@app.middleware("http")
async def tenant_middleware(request: Request, call_next):
    path = request.url.path
    tenant_slug = None
    
    tenant_slug_param = request.query_params.get("tenant")
    tenant_header = request.headers.get("X-Tenant")
    
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 3 and parts[0] == "api" and parts[1] == "t":
        tenant_slug = parts[2]
        new_parts = ["api"] + parts[3:]
        new_path = "/" + "/".join(new_parts)
        request.scope["path"] = new_path
    elif tenant_slug_param:
        tenant_slug = tenant_slug_param
    elif tenant_header:
        tenant_slug = tenant_header
    else:
        tenant_slug = "demo"

    # Health check is system-wide, all other api routes require tenant resolution
    is_api_route = path.startswith("/api")
    if is_api_route and not path.startswith("/api/health") and not path.startswith("/api/metrics"):
        try:
            tenant = await get_tenant_by_subdomain(tenant_slug)
            if not tenant:
                return JSONResponse(
                    status_code=404,
                    content={"detail": f"Tenant '{tenant_slug}' not found."}
                )
            if tenant["status"] != "active":
                return JSONResponse(
                    status_code=403,
                    content={"detail": f"Tenant '{tenant_slug}' is {tenant['status']}."}
                )
            request.state.tenant_id = tenant["id"]
            request.state.tenant_slug = tenant_slug
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"detail": f"Database error resolving tenant: {str(e)}"}
            )
    else:
        request.state.tenant_id = "d4444444-4444-4444-4444-444444444444"
        request.state.tenant_slug = "demo"

    response = await call_next(request)
    return response


# All endpoints migrated to clean architecture layers
