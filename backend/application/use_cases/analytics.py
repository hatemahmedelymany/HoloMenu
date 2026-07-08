"""
Use cases orchestration for client analytics and telemetry event logs.
"""
from typing import List, Dict

from backend.application.interfaces.analytics_repository import AnalyticsRepository


class AnalyticsUseCases:
    def __init__(self, analytics_repo: AnalyticsRepository):
        self.analytics_repo = analytics_repo

    async def log_event(self, tenant_id: str, event_data: dict) -> dict:
        await self.analytics_repo.log_event(tenant_id, event_data)
        return {"status": "logged"}

    async def get_event_summary(self, tenant_id: str) -> List[Dict]:
        return await self.analytics_repo.get_event_summary(tenant_id)
