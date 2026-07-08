"""
MySQL implementation of the AnalyticsRepository contract.
"""
import json
from typing import List, Dict
import aiomysql

from backend.application.interfaces.analytics_repository import AnalyticsRepository


class MysqlAnalyticsRepo(AnalyticsRepository):
    def __init__(self, conn: aiomysql.Connection):
        self.conn = conn

    async def log_event(self, tenant_id: str, event_data: dict) -> None:
        async with self.conn.cursor() as cur:
            await cur.execute(
                """INSERT INTO analytics_events
                   (tenant_id, event_type, product_id, department_id, session_uid, meta)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (
                    tenant_id,
                    event_data["event_type"],
                    event_data.get("product_id"),
                    event_data.get("department_id"),
                    event_data["session_uid"],
                    json.dumps(event_data["meta"]) if event_data.get("meta") else None,
                ),
            )

    async def get_event_summary(self, tenant_id: str) -> List[Dict]:
        async with self.conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                """SELECT event_type, COUNT(*) AS count
                   FROM analytics_events
                   WHERE tenant_id = %s
                   GROUP BY event_type ORDER BY count DESC""",
                (tenant_id,)
            )
            return await cur.fetchall()
