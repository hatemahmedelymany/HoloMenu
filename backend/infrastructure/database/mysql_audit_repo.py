"""
MySQL database implementation of the AuditRepository contract.
"""
import json
from typing import Optional
import aiomysql

from backend.application.interfaces.audit_repository import AuditRepository


class MysqlAuditRepo(AuditRepository):
    def __init__(self, conn: aiomysql.Connection):
        self.conn = conn

    async def log_audit_event(
        self,
        tenant_id: str,
        action: str,
        target_type: str,
        target_id: Optional[str] = None,
        user_id: Optional[int] = None,
        before_state: Optional[dict] = None,
        after_state: Optional[dict] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        # Normalize JSON columns
        before_json = json.dumps(before_state) if before_state is not None else None
        after_json = json.dumps(after_state) if after_state is not None else None

        async with self.conn.cursor() as cur:
            await cur.execute(
                """INSERT INTO audit_logs (
                    tenant_id, user_id, action, target_type, target_id,
                    before_state, after_state, ip_address, user_agent
                   ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    tenant_id,
                    user_id,
                    action,
                    target_type,
                    target_id,
                    before_json,
                    after_json,
                    ip_address,
                    user_agent,
                ),
            )
