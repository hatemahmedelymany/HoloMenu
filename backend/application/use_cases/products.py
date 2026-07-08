"""
Application Use Cases for Product execution.
"""
from typing import Optional, List, Dict

from backend.application.interfaces.product_repository import ProductRepository
from backend.application.interfaces.audit_repository import AuditRepository


class ProductNotFoundError(Exception):
    """Raised when a product details fetch misses."""
    pass


class ProductUseCases:
    def __init__(self, product_repo: ProductRepository, audit_repo: AuditRepository):
        self.product_repo = product_repo
        self.audit_repo = audit_repo

    async def get_product(self, tenant_id: str, product_id: int) -> dict:
        product = await self.product_repo.get_product(tenant_id, product_id)
        if not product:
            raise ProductNotFoundError("Product not found")
        return product

    async def get_department_products(self, tenant_id: str, department_id: int) -> List[Dict]:
        return await self.product_repo.get_department_products(tenant_id, department_id)

    async def create_product(
        self,
        tenant_id: str,
        user_id: int,
        prod_data: dict,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> dict:
        product_id = await self.product_repo.create_product(tenant_id, prod_data)

        # Audit logging
        await self.audit_repo.log_audit_event(
            tenant_id=tenant_id,
            action="create_product",
            target_type="product",
            target_id=str(product_id),
            user_id=user_id,
            after_state=prod_data,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return {"status": "created", "id": product_id}

    async def update_product(
        self,
        tenant_id: str,
        product_id: int,
        user_id: int,
        prod_data: dict,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> dict:
        # Fetch current record for audit before state
        before_state = await self.product_repo.get_product(tenant_id, product_id)
        if not before_state:
            raise ProductNotFoundError("Product not found")

        # Perform database update
        await self.product_repo.update_product(tenant_id, product_id, prod_data)

        # Audit log transition
        await self.audit_repo.log_audit_event(
            tenant_id=tenant_id,
            action="update_product",
            target_type="product",
            target_id=str(product_id),
            user_id=user_id,
            before_state=before_state,
            after_state=prod_data,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return {"status": "updated", "id": product_id}

    async def delete_product(
        self,
        tenant_id: str,
        product_id: int,
        user_id: int,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> dict:
        # Fetch current record for audit before state
        before_state = await self.product_repo.get_product(tenant_id, product_id)
        if not before_state:
            raise ProductNotFoundError("Product not found")

        # Perform deletion
        await self.product_repo.delete_product(tenant_id, product_id)

        # Audit logging of deletion (soft delete has status updated)
        after_state = dict(before_state)
        after_state["available"] = 0

        await self.audit_repo.log_audit_event(
            tenant_id=tenant_id,
            action="delete_product",
            target_type="product",
            target_id=str(product_id),
            user_id=user_id,
            before_state=before_state,
            after_state=after_state,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return {"status": "deleted_soft", "id": product_id}
