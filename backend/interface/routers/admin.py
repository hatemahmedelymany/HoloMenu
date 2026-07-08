"""
Administrative query endpoints router.
"""
from typing import List
from fastapi import APIRouter, Depends

from backend.infrastructure.database.pool import get_db_conn
from backend.infrastructure.database.mysql_order_repo import MysqlOrderRepo
from backend.application.use_cases.admin import AdminUseCases
from backend.interface.dependencies import get_current_tenant_id, require_role

router = APIRouter(tags=["admin"])


@router.get("/api/admin/orders")
async def get_admin_orders(
    tenant_id: str = Depends(get_current_tenant_id),
    user: dict = Depends(require_role("admin", "owner")),
    conn=Depends(get_db_conn),
):
    order_repo = MysqlOrderRepo(conn)
    use_cases = AdminUseCases(order_repo)
    return await use_cases.get_admin_orders(tenant_id)


@router.get("/api/admin/stats")
async def get_admin_stats(
    tenant_id: str = Depends(get_current_tenant_id),
    user: dict = Depends(require_role("admin", "owner")),
    conn=Depends(get_db_conn),
):
    order_repo = MysqlOrderRepo(conn)
    use_cases = AdminUseCases(order_repo)
    return await use_cases.get_admin_stats(tenant_id)
