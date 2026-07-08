"""
Abstract contract for Analytics Event logging and retrieval.
"""
from abc import ABC, abstractmethod
from typing import List, Dict


class AnalyticsRepository(ABC):
    @abstractmethod
    async def log_event(self, tenant_id: str, event_data: dict) -> None:
        """Insert a telemetry/analytics event."""
        pass

    @abstractmethod
    async def get_event_summary(self, tenant_id: str) -> List[Dict]:
        """Aggregate telemetry/activity event counts by type."""
        pass
