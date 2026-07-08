"""
Abstract contract for Department Data Access (Repository Pattern).
"""
from abc import ABC, abstractmethod
from typing import Optional, List, Dict


class DepartmentRepository(ABC):
    @abstractmethod
    async def get_departments(self, tenant_id: str) -> List[Dict]:
        """Fetch all active departments ordered by display order."""
        pass

    @abstractmethod
    async def get_department(self, tenant_id: str, dept_id: int) -> Optional[dict]:
        """Fetch a specific department details by primary ID."""
        pass

    @abstractmethod
    async def create_department(self, tenant_id: str, dept_data: dict) -> int:
        """Insert a new department and return its primary ID."""
        pass

    @abstractmethod
    async def update_department(self, tenant_id: str, dept_id: int, dept_data: dict) -> None:
        """Update existing department metadata."""
        pass

    @abstractmethod
    async def delete_department(self, tenant_id: str, dept_id: int) -> None:
        """Remove department from the database."""
        pass
