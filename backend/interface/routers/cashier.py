"""
Cashier checkout workspace endpoints router.
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from backend.infrastructure.database.pool import get_db_conn
from backend.infrastructure.database.mysql_order_repo import MysqlOrderRepo
from backend.infrastructure.database.mysql_audit_repo import MysqlAuditRepo
from backend.infrastructure.database.mysql_product_repo import MysqlProductRepo
from backend.application.use_cases.orders import (
    OrderUseCases,
    OrderNotFoundError,
    OrderStatusConflictError,
)
from backend.domain.order_rules import InvalidStatusTransitionError
from backend.interface.dependencies import get_current_tenant_id, require_role
from backend.infrastructure.events.sse import broadcast_event

router = APIRouter(tags=["cashier"])


class PaymentRequest(BaseModel):
    payment_method: str  # "cash" | "card" | "wallet"
    amount_tendered: Optional[float] = None
    model_config = ConfigDict(extra="forbid")


@router.get("/api/cashier/orders")
async def get_cashier_orders(
    tenant_id: str = Depends(get_current_tenant_id),
    user: dict = Depends(require_role("cashier", "admin", "owner")),
    conn=Depends(get_db_conn),
):
    order_repo = MysqlOrderRepo(conn)
    audit_repo = MysqlAuditRepo(conn)
    product_repo = MysqlProductRepo(conn)
    use_cases = OrderUseCases(order_repo, audit_repo, product_repo)

    result = await use_cases.get_cashier_orders(tenant_id)
    return result


@router.post("/api/orders/{order_id}/pay")
async def pay_order(
    request: Request,
    order_id: int,
    req: PaymentRequest,
    tenant_id: str = Depends(get_current_tenant_id),
    user: dict = Depends(require_role("cashier", "admin", "owner")),
    conn=Depends(get_db_conn),
):
    order_repo = MysqlOrderRepo(conn)
    audit_repo = MysqlAuditRepo(conn)
    product_repo = MysqlProductRepo(conn)
    use_cases = OrderUseCases(order_repo, audit_repo, product_repo)

    try:
        ip = request.client.host if request.client else None
        ua = request.headers.get("user-agent")

        result = await use_cases.pay_order(
            tenant_id=tenant_id,
            order_id=order_id,
            payment_method=req.payment_method,
            amount_tendered=req.amount_tendered,
            user_id=user["admin_id"],
            ip_address=ip,
            user_agent=ua,
        )

        # Broadcast SSE event
        await broadcast_event(
            tenant_id, "order_update", {"id": order_id, "status": "completed"}
        )

        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except OrderNotFoundError:
        raise HTTPException(status_code=404, detail="Order not found")
    except OrderStatusConflictError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except InvalidStatusTransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))
