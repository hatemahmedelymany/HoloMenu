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


@router.post("/api/admin/tenants/{tenant_id}/offboard")
async def offboard_tenant(
    tenant_id: str,
    user: dict = Depends(require_role("admin", "owner")),
    conn=Depends(get_db_conn),
):
    from fastapi import HTTPException
    from datetime import datetime
    
    if user["tenant_id"] != tenant_id:
        raise HTTPException(status_code=403, detail="Cannot offboard another tenant")
        
    now = datetime.utcnow()
    async with conn.cursor() as cur:
        await cur.execute(
            "UPDATE tenants SET status = 'cancelled', deleted_at = %s WHERE id = %s",
            (now, tenant_id)
        )
    return {"status": "success", "detail": "Tenant offboarding soft-delete initiated."}
