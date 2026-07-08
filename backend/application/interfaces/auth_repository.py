"""
Abstract contract for Auth Data Access (Repository Pattern).
"""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional


class AuthRepository(ABC):
    @abstractmethod
    async def get_admin_by_username(self, tenant_id: str, username: str) -> Optional[dict]:
        """Fetch admin record by tenant/username match."""
        pass

    @abstractmethod
    async def save_refresh_token(
        self, tenant_id: str, admin_id: int, token: str, expires_at: datetime
    ) -> None:
        """Persist a new refresh token for a user."""
        pass

    @abstractmethod
    async def verify_refresh_token(self, tenant_id: str, token: str) -> bool:
        """Check if refresh token exists and matches tenant context."""
        pass

    @abstractmethod
    async def delete_refresh_token(self, token: str) -> None:
        """Revoke a refresh token from database."""
        pass
