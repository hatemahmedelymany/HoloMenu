"""
Abstract contract for Product Data Access (Repository Pattern).
"""
from abc import ABC, abstractmethod
from typing import Optional, List, Dict


class ProductRepository(ABC):
    @abstractmethod
    async def get_product(self, tenant_id: str, product_id: int) -> Optional[dict]:
        """Fetch product record by primary ID."""
        pass

    @abstractmethod
    async def get_department_products(self, tenant_id: str, department_id: int) -> List[Dict]:
        """Fetch products under a department."""
        pass

    @abstractmethod
    async def create_product(self, tenant_id: str, prod_data: dict) -> int:
        """Insert new product into database and return its primary ID."""
        pass

    @abstractmethod
    async def update_product(self, tenant_id: str, product_id: int, prod_data: dict) -> None:
        """Update existing product details."""
        pass

    @abstractmethod
    async def delete_product(self, tenant_id: str, product_id: int) -> None:
        """Remove product from database."""
        pass

