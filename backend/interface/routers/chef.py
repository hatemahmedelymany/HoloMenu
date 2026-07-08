"""
Chef workspace endpoints router.
"""
from fastapi import APIRouter, Depends

from backend.infrastructure.database.pool import get_db_conn
from backend.infrastructure.database.mysql_order_repo import MysqlOrderRepo
from backend.infrastructure.database.mysql_audit_repo import MysqlAuditRepo
from backend.infrastructure.database.mysql_product_repo import MysqlProductRepo
from backend.application.use_cases.orders import OrderUseCases
from backend.interface.dependencies import get_current_tenant_id, require_role

router = APIRouter(prefix="/api/chef", tags=["chef"])


@router.get("/orders")
async def get_chef_orders(
    tenant_id: str = Depends(get_current_tenant_id),
    user: dict = Depends(require_role("chef", "admin", "owner")),
    conn=Depends(get_db_conn),
):
    order_repo = MysqlOrderRepo(conn)
    audit_repo = MysqlAuditRepo(conn)
    product_repo = MysqlProductRepo(conn)
    use_cases = OrderUseCases(order_repo, audit_repo, product_repo)

    result = await use_cases.get_chef_orders(tenant_id)
    return result
