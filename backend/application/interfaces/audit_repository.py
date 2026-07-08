"""
Abstract boundary contract for Audit Log Data Access (Repository Pattern).
"""
from abc import ABC, abstractmethod
from typing import Optional


class AuditRepository(ABC):
    @abstractmethod
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
        """Write an audit log event into persistent storage during the active connection transaction."""
        pass
