"""
Global database connection pool holds and dependencies.
"""
from typing import Optional, AsyncGenerator
import aiomysql

# Global pool instance populated on lifespan startup
pool: Optional[aiomysql.Pool] = None


async def get_db_conn() -> AsyncGenerator[aiomysql.Cursor, None]:
    """Dependency that yields a database connection context."""
    global pool
    if pool is None:
        raise RuntimeError("Database connection pool is not initialized.")
    async with pool.acquire() as conn:
        yield conn
        # Note: autocommit is True by default in DB_CONFIG
