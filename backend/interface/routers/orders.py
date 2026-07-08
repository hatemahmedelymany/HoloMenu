"""
Customer ordering endpoints router.
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
    ProductNotFoundError,
    ProductUnavailableError,
)
from backend.domain.order_rules import InvalidStatusTransitionError
from backend.interface.dependencies import get_current_tenant_id, require_role
from backend.infrastructure.events.sse import broadcast_event

router = APIRouter(prefix="/api/orders", tags=["orders"])


class AddItemRequest(BaseModel):
    product_id: int
    quantity: int = 1
    model_config = ConfigDict(extra="forbid")


class UpdateItemRequest(BaseModel):
    product_id: int
    quantity: int
    model_config = ConfigDict(extra="forbid")


class StatusUpdateRequest(BaseModel):
    status: str
    model_config = ConfigDict(extra="forbid")


@router.post("", status_code=201)
async def create_order(
    tenant_id: str = Depends(get_current_tenant_id),
    conn=Depends(get_db_conn)
):
    order_repo = MysqlOrderRepo(conn)
    audit_repo = MysqlAuditRepo(conn)
    product_repo = MysqlProductRepo(conn)
    use_cases = OrderUseCases(order_repo, audit_repo, product_repo)
    
    result = await use_cases.create_order(tenant_id)
    return result


@router.post("/{order_uid}/items", status_code=201)
async def add_order_item(
    order_uid: str,
    req: AddItemRequest,
    tenant_id: str = Depends(get_current_tenant_id),
    conn=Depends(get_db_conn)
):
    if req.quantity <= 0:
        raise HTTPException(status_code=422, detail="quantity must be > 0")

    order_repo = MysqlOrderRepo(conn)
    audit_repo = MysqlAuditRepo(conn)
    product_repo = MysqlProductRepo(conn)
    use_cases = OrderUseCases(order_repo, audit_repo, product_repo)

    try:
        result = await use_cases.add_order_item(
            tenant_id=tenant_id,
            order_uid=order_uid,
            product_id=req.product_id,
            quantity=req.quantity,
        )
        return result
    except OrderNotFoundError:
        raise HTTPException(status_code=404, detail="Active order not found")
    except OrderStatusConflictError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except (ProductNotFoundError, ProductUnavailableError):
        raise HTTPException(status_code=404, detail="Product not found")


@router.put("/{order_uid}/items")
async def update_order_item(
    order_uid: str,
    req: UpdateItemRequest,
    tenant_id: str = Depends(get_current_tenant_id),
    conn=Depends(get_db_conn)
):
    order_repo = MysqlOrderRepo(conn)
    audit_repo = MysqlAuditRepo(conn)
    product_repo = MysqlProductRepo(conn)
    use_cases = OrderUseCases(order_repo, audit_repo, product_repo)

    try:
        result = await use_cases.update_order_item(
            tenant_id=tenant_id,
            order_uid=order_uid,
            product_id=req.product_id,
            quantity=req.quantity,
        )
        return result
    except OrderNotFoundError:
        raise HTTPException(status_code=404, detail="Active order not found")
    except OrderStatusConflictError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except (ProductNotFoundError, ProductUnavailableError):
        raise HTTPException(status_code=404, detail="Product not found")


@router.post("/{order_uid}/confirm")
async def confirm_order(
    request: Request,
    order_uid: str,
    tenant_id: str = Depends(get_current_tenant_id),
    conn=Depends(get_db_conn)
):
    order_repo = MysqlOrderRepo(conn)
    audit_repo = MysqlAuditRepo(conn)
    product_repo = MysqlProductRepo(conn)
    use_cases = OrderUseCases(order_repo, audit_repo, product_repo)

    try:
        user_id = getattr(request.state, "user_id", None)
        ip = request.client.host if request.client else None
        ua = request.headers.get("user-agent")
        
        result = await use_cases.confirm_order(
            tenant_id=tenant_id,
            order_uid=order_uid,
            ip_address=ip,
            user_agent=ua,
        )
        
        # We need the primary ID for the broadcast payload
        order = await order_repo.get_order_by_uid(tenant_id, order_uid)
        order_number = order["id"] if order else 0

        # Broadcast SSE event
        await broadcast_event(
            tenant_id, "order_update", {"id": order_number, "status": "confirmed"}
        )

        return {
            "status": "confirmed",
            "order_uid": order_uid,
            "order_number": order_number,
            "qr_payload": f"https://example.com/pickup/{order_uid}",
            "total_price": result["total_price"],
        }
    except OrderNotFoundError:
        raise HTTPException(status_code=404, detail="Order not found")
    except InvalidStatusTransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/{order_uid}/cancel")
async def cancel_order(
    request: Request,
    order_uid: str,
    reason: str = "user_cancelled",
    tenant_id: str = Depends(get_current_tenant_id),
    conn=Depends(get_db_conn)
):
    order_repo = MysqlOrderRepo(conn)
    audit_repo = MysqlAuditRepo(conn)
    product_repo = MysqlProductRepo(conn)
    use_cases = OrderUseCases(order_repo, audit_repo, product_repo)

    try:
        ip = request.client.host if request.client else None
        ua = request.headers.get("user-agent")

        # Get order before cancel for primary ID in broadcast
        order = await order_repo.get_order_by_uid(tenant_id, order_uid)
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        order_number = order["id"]

        await use_cases.cancel_order(
            tenant_id=tenant_id,
            order_uid=order_uid,
            reason=reason,
            ip_address=ip,
            user_agent=ua,
        )

        # Broadcast SSE event
        await broadcast_event(
            tenant_id, "order_update", {"id": order_number, "status": "cancelled"}
        )

        return {"status": "cancelled", "reason": reason}
    except OrderNotFoundError:
        raise HTTPException(status_code=404, detail="Order not found")
    except InvalidStatusTransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/{order_id}/status")
async def update_order_status(
    request: Request,
    order_id: int,
    req: StatusUpdateRequest,
    tenant_id: str = Depends(get_current_tenant_id),
    user: dict = Depends(require_role("chef", "cashier", "admin", "owner")),
    conn=Depends(get_db_conn)
):
    from backend.domain.order_rules import VALID_TRANSITIONS
    
    all_statuses = set(VALID_TRANSITIONS.keys())
    if req.status not in all_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of {sorted(all_statuses)}",
        )

    order_repo = MysqlOrderRepo(conn)
    audit_repo = MysqlAuditRepo(conn)
    product_repo = MysqlProductRepo(conn)
    use_cases = OrderUseCases(order_repo, audit_repo, product_repo)

    try:
        ip = request.client.host if request.client else None
        ua = request.headers.get("user-agent")
        
        result = await use_cases.update_order_status(
            tenant_id=tenant_id,
            order_id=order_id,
            new_status=req.status,
            user_id=user["admin_id"],
            ip_address=ip,
            user_agent=ua,
        )
        
        # Broadcast SSE event
        await broadcast_event(
            tenant_id, "order_update", {"id": order_id, "status": req.status}
        )
        
        return result
    except OrderNotFoundError:
        raise HTTPException(status_code=404, detail="Order not found")
    except InvalidStatusTransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))
