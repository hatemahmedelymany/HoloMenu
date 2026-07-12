import pytest
import os
import aiomysql
from dotenv import load_dotenv

# Load env variables before importing settings
load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

import backend.infrastructure.database.pool as db_pool
from backend.infrastructure.config.settings import DB_CONFIG

@pytest.fixture(autouse=True)
async def db_pool_setup():
    """Fixture to initialize and clean up database connection pool for each test."""
    db_pool.pool = await aiomysql.create_pool(minsize=1, maxsize=5, **DB_CONFIG)
    
    # Assign the test pool to backend.main.pool for middleware queries
    import backend.main
    backend.main.pool = db_pool.pool
    
    yield db_pool.pool
    db_pool.pool.close()
    await db_pool.pool.wait_closed()

@pytest.fixture(autouse=True)
def mock_tenant_resolver():
    """Mock the tenant subdomain resolver in main.py to allow resolving test tenants inside transactions."""
    import backend.main
    original_resolver = backend.main.get_tenant_by_subdomain
    
    async def mock_resolver(subdomain: str):
        if subdomain == "tenantb":
            return {
                "id": "b4444444-4444-4444-4444-444444444444",
                "subdomain": "tenantb",
                "status": "active"
            }
        if subdomain == "demo":
            return {
                "id": "d4444444-4444-4444-4444-444444444444",
                "subdomain": "demo",
                "status": "active"
            }
        return await original_resolver(subdomain)
        
    backend.main.get_tenant_by_subdomain = mock_resolver
    yield
    backend.main.get_tenant_by_subdomain = original_resolver

@pytest.fixture
async def conn():
    """Fixture that yields a database connection inside a rolled-back transaction."""
    async with db_pool.pool.acquire() as connection:
        await connection.begin()
        yield connection
        await connection.rollback()

@pytest.fixture
async def client(conn):
    """Fixture providing an AsyncClient with overridden DB dependency for rollback protection."""
    from httpx import AsyncClient, ASGITransport
    from backend.main import app
    from backend.infrastructure.database.pool import get_db_conn
    
    async def override_get_db_conn():
        yield conn
        
    app.dependency_overrides[get_db_conn] = override_get_db_conn
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
        
    app.dependency_overrides.clear()
