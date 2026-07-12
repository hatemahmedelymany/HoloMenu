from abc import ABC, abstractmethod
from typing import Optional, List, Dict

class KioskRepository(ABC):
    @abstractmethod
    async def count_active_kiosks(self, tenant_id: str) -> int:
        """Count the number of active kiosks for a specific tenant."""
        pass

    @abstractmethod
    async def create_kiosk(
        self, kiosk_id: str, tenant_id: str, name: str, secret: str, device_id: str, status: str = "active"
    ) -> None:
        """Create a new kiosk record."""
        pass

    @abstractmethod
    async def get_kiosk(self, tenant_id: str, kiosk_id: str) -> Optional[dict]:
        """Fetch kiosk details by ID and tenant."""
        pass

    @abstractmethod
    async def create_websocket_session(
        self, token: str, tenant_id: str, kiosk_id: str, device_id: str, expires_at
    ) -> None:
        """Save a new WebSocket session token record."""
        pass

    @abstractmethod
    async def verify_websocket_session(self, tenant_id: str, token: str) -> bool:
        """Check if a WebSocket session token is active and valid."""
        pass

    @abstractmethod
    async def get_tenant_limits(self, tenant_id: str) -> Optional[dict]:
        """Fetch the plan tier and kiosk limit for a tenant."""
        pass

