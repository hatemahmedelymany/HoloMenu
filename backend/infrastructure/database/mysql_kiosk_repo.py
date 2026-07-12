import aiomysql
from typing import Optional
from backend.application.interfaces.kiosk_repository import KioskRepository

class MysqlKioskRepo(KioskRepository):
    def __init__(self, conn: aiomysql.Connection):
        self.conn = conn

    async def count_active_kiosks(self, tenant_id: str) -> int:
        async with self.conn.cursor() as cur:
            await cur.execute(
                "SELECT COUNT(*) FROM kiosks WHERE tenant_id = %s AND status = 'active'",
                (tenant_id,)
            )
            row = await cur.fetchone()
            return row[0] if row else 0

    async def create_kiosk(
        self, kiosk_id: str, tenant_id: str, name: str, secret: str, status: str = "active"
    ) -> None:
        async with self.conn.cursor() as cur:
            await cur.execute(
                """INSERT INTO kiosks (id, tenant_id, name, secret, status)
                   VALUES (%s, %s, %s, %s, %s)""",
                (kiosk_id, tenant_id, name, secret, status)
            )

    async def get_kiosk(self, tenant_id: str, kiosk_id: str) -> Optional[dict]:
        async with self.conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT id, tenant_id, name, secret, status FROM kiosks WHERE tenant_id = %s AND id = %s",
                (tenant_id, kiosk_id)
            )
            return await cur.fetchone()

    async def create_websocket_session(
        self, token: str, tenant_id: str, kiosk_id: str, expires_at
    ) -> None:
        async with self.conn.cursor() as cur:
            await cur.execute(
                """INSERT INTO websocket_sessions (token, tenant_id, kiosk_id, expires_at)
                   VALUES (%s, %s, %s, %s)""",
                (token, tenant_id, kiosk_id, expires_at)
            )

    async def verify_websocket_session(self, tenant_id: str, token: str) -> bool:
        async with self.conn.cursor() as cur:
            await cur.execute(
                "SELECT id FROM websocket_sessions WHERE token = %s AND tenant_id = %s AND expires_at > NOW()",
                (token, tenant_id)
            )
            row = await cur.fetchone()
            return row is not None

    async def get_tenant_limits(self, tenant_id: str) -> Optional[dict]:
        async with self.conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT plan_tier, max_kiosks FROM tenants WHERE id = %s",
                (tenant_id,)
            )
            return await cur.fetchone()

