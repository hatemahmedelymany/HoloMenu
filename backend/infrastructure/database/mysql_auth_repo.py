"""
MySQL implementation of the AuthRepository contract.
"""
from datetime import datetime
from typing import Optional
import aiomysql

from backend.application.interfaces.auth_repository import AuthRepository


class MysqlAuthRepo(AuthRepository):
    def __init__(self, conn: aiomysql.Connection):
        self.conn = conn

    async def get_admin_by_username(self, tenant_id: str, username: str) -> Optional[dict]:
        async with self.conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT id, username, password_hash, role FROM admins WHERE tenant_id = %s AND username = %s",
                (tenant_id, username)
            )
            return await cur.fetchone()

    async def save_refresh_token(
        self, tenant_id: str, admin_id: int, token: str, expires_at: datetime
    ) -> None:
        async with self.conn.cursor() as cur:
            await cur.execute(
                """INSERT INTO refresh_tokens (tenant_id, admin_id, token, expires_at)
                   VALUES (%s, %s, %s, %s)""",
                (tenant_id, admin_id, token, expires_at)
            )

    async def verify_refresh_token(self, tenant_id: str, token: str) -> bool:
        async with self.conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT id FROM refresh_tokens WHERE token = %s AND tenant_id = %s",
                (token, tenant_id)
            )
            row = await cur.fetchone()
            return row is not None

    async def delete_refresh_token(self, token: str) -> None:
        async with self.conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM refresh_tokens WHERE token = %s",
                (token,)
            )
