"""
Abstract boundary contract for Order Data Access (Repository Pattern).
"""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, List, Dict


class OrderRepository(ABC):
    @abstractmethod
    async def create_order(self, tenant_id: str, order_uid: str) -> None:
        """Create a new order in pending status."""
        pass

    @abstractmethod
    async def get_order_by_uid(self, tenant_id: str, order_uid: str) -> Optional[dict]:
        """Fetch order record by UID."""
        pass

    @abstractmethod
    async def get_order_by_id(self, tenant_id: str, order_id: int) -> Optional[dict]:
        """Fetch order record by ID."""
        pass

    @abstractmethod
    async def get_item(self, tenant_id: str, order_id: int, product_id: int) -> Optional[dict]:
        """Get specific order item details."""
        pass

    @abstractmethod
    async def add_item(self, tenant_id: str, order_id: int, product_id: int, quantity: int, unit_price: float) -> None:
        """Insert a new item line into order_items."""
        pass

    @abstractmethod
    async def update_item_quantity(self, tenant_id: str, order_id: int, product_id: int, quantity: int) -> None:
        """Update the quantity of an existing item line."""
        pass

    @abstractmethod
    async def remove_item(self, tenant_id: str, order_id: int, product_id: int) -> None:
        """Delete an item line from order_items."""
        pass

    @abstractmethod
    async def get_order_items(self, tenant_id: str, order_id: int) -> List[Dict]:
        """Fetch all item rows with product meta (name, etc.) for an order."""
        pass

    @abstractmethod
    async def update_order_status(self, order_id: int, status: str) -> None:
        """Update status of order by primary ID."""
        pass

    @abstractmethod
    async def update_order_status_by_uid(self, order_uid: str, status: str) -> None:
        """Update status of order by UID."""
        pass

    @abstractmethod
    async def set_order_price(self, order_id: int, total_price: float) -> None:
        """Set total order price."""
        pass

    @abstractmethod
    async def get_chef_pipeline(self, tenant_id: str) -> List[Dict]:
        """Fetch cooking workflow orders for Chef board."""
        pass

    @abstractmethod
    async def get_cashier_pipeline(self, tenant_id: str) -> List[Dict]:
        """Fetch unpaid pipelines (cooking/ready/completed) for Cashier board."""
        pass

    @abstractmethod
    async def record_payment(
        self,
        tenant_id: str,
        order_id: int,
        payment_method: str,
        amount_tendered: Optional[float],
        amount_paid: float
    ) -> None:
        """Write payment registration record."""
        pass

    @abstractmethod
    async def set_order_completed_at(self, order_id: int, completed_at: datetime) -> None:
        """Set order closure timestamp."""
        pass

    @abstractmethod
    async def get_admin_orders(self, tenant_id: str) -> List[Dict]:
        """Fetch all orders for administrative panel view."""
        pass

    @abstractmethod
    async def get_admin_order_items(self, tenant_id: str, order_ids: List[int]) -> List[Dict]:
        """Fetch order item lines for a collection of order IDs."""
        pass

    @abstractmethod
    async def get_admin_stats(self, tenant_id: str) -> dict:
        """Fetch administrative dashboard metric counts and aggregations."""
        pass

