"""
Application Use Cases for Department execution.
"""
from typing import Optional, List, Dict

from backend.application.interfaces.department_repository import DepartmentRepository
from backend.application.interfaces.audit_repository import AuditRepository


class DepartmentNotFoundError(Exception):
    """Raised when a department query fails."""
    pass


class DepartmentUseCases:
    def __init__(self, department_repo: DepartmentRepository, audit_repo: AuditRepository):
        self.department_repo = department_repo
        self.audit_repo = audit_repo

    async def get_departments(self, tenant_id: str) -> List[Dict]:
        return await self.department_repo.get_departments(tenant_id)

    async def create_department(
        self,
        tenant_id: str,
        user_id: int,
        dept_data: dict,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> dict:
        dept_id = await self.department_repo.create_department(tenant_id, dept_data)

        # Audit log creation
        await self.audit_repo.log_audit_event(
            tenant_id=tenant_id,
            action="create_department",
            target_type="department",
            target_id=str(dept_id),
            user_id=user_id,
            after_state=dept_data,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return {"status": "created", "id": dept_id}

    async def update_department(
        self,
        tenant_id: str,
        dept_id: int,
        user_id: int,
        dept_data: dict,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> dict:
        before_state = await self.department_repo.get_department(tenant_id, dept_id)
        if not before_state:
            raise DepartmentNotFoundError("Department not found")

        await self.department_repo.update_department(tenant_id, dept_id, dept_data)

        # Audit logupdate
        await self.audit_repo.log_audit_event(
            tenant_id=tenant_id,
            action="update_department",
            target_type="department",
            target_id=str(dept_id),
            user_id=user_id,
            before_state=before_state,
            after_state=dept_data,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return {"status": "updated", "id": dept_id}

    async def delete_department(
        self,
        tenant_id: str,
        dept_id: int,
        user_id: int,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> dict:
        before_state = await self.department_repo.get_department(tenant_id, dept_id)
        if not before_state:
            raise DepartmentNotFoundError("Department not found")

        await self.department_repo.delete_department(tenant_id, dept_id)

        after_state = dict(before_state)
        after_state["active"] = 0  # soft delete flag

        # Audit log soft-deletion
        await self.audit_repo.log_audit_event(
            tenant_id=tenant_id,
            action="delete_department",
            target_type="department",
            target_id=str(dept_id),
            user_id=user_id,
            before_state=before_state,
            after_state=after_state,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return {"status": "deleted_soft", "id": dept_id}
