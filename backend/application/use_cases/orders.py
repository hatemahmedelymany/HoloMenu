"""
Application Use Cases for Order management and workflow routing.
"""
import uuid
from datetime import datetime
from typing import Optional, List, Dict

from backend.application.interfaces.order_repository import OrderRepository
from backend.application.interfaces.audit_repository import AuditRepository
from backend.application.interfaces.product_repository import ProductRepository
from backend.domain.order_rules import assert_valid_transition, InvalidStatusTransitionError


class OrderNotFoundError(Exception):
    pass


class ProductNotFoundError(Exception):
    pass


class OrderStatusConflictError(Exception):
    pass


class ProductUnavailableError(Exception):
    pass


class OrderUseCases:
    def __init__(
        self,
        order_repo: OrderRepository,
        audit_repo: AuditRepository,
        product_repo: ProductRepository,
    ):
        self.order_repo = order_repo
        self.audit_repo = audit_repo
        self.product_repo = product_repo

    async def create_order(self, tenant_id: str) -> dict:
        uid = str(uuid.uuid4())
        await self.order_repo.create_order(tenant_id, uid)
        await self.audit_repo.log_audit_event(
            tenant_id=tenant_id,
            action="create_order",
            target_type="order",
            target_id=uid,
        )
        return {"order_uid": uid, "status": "pending"}

    async def add_order_item(
        self, tenant_id: str, order_uid: str, product_id: int, quantity: int
    ) -> dict:
        order = await self.order_repo.get_order_by_uid(tenant_id, order_uid)
        if not order:
            raise OrderNotFoundError("Order not found")

        if order["status"] != "pending":
            raise OrderStatusConflictError("Items can only be added to pending orders")

        product = await self.product_repo.get_product(tenant_id, product_id)
        if not product:
            raise ProductNotFoundError("Product not found")

        if not product.get("available", True):
            raise ProductUnavailableError("Product is not available")

        # Upsert line item
        # Upsert line item
        existing = await self.order_repo.get_item(tenant_id, order["id"], product_id)
        if existing:
            new_qty = existing["quantity"] + quantity
            await self.order_repo.update_item_quantity(tenant_id, order["id"], product_id, new_qty)
        else:
            price = float(product["price"])
            await self.order_repo.add_item(tenant_id, order["id"], product_id, quantity, price)

        return {"status": "item_added"}

    async def update_order_item(
        self, tenant_id: str, order_uid: str, product_id: int, quantity: int
    ) -> dict:
        order = await self.order_repo.get_order_by_uid(tenant_id, order_uid)
        if not order:
            raise OrderNotFoundError("Order not found")

        if order["status"] != "pending":
            raise OrderStatusConflictError("Items can only be updated in pending orders")

        product = await self.product_repo.get_product(tenant_id, product_id)
        if not product:
            raise ProductNotFoundError("Product not found")

        if quantity <= 0:
            await self.order_repo.remove_item(tenant_id, order["id"], product_id)
        else:
            existing = await self.order_repo.get_item(tenant_id, order["id"], product_id)
            if not existing:
                # Add item if it wasn't already in the order
                if not product.get("available", True):
                    raise ProductUnavailableError("Product is not available")
                await self.order_repo.add_item(
                    tenant_id, order["id"], product_id, quantity, float(product["price"])
                )
            else:
                await self.order_repo.update_item_quantity(tenant_id, order["id"], product_id, quantity)

        return {"status": "item_updated"}

    async def confirm_order(
        self,
        tenant_id: str,
        order_uid: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> dict:
        order = await self.order_repo.get_order_by_uid(tenant_id, order_uid)
        if not order:
            raise OrderNotFoundError("Order not found")

        assert_valid_transition(order["status"], "confirmed")

        items = await self.order_repo.get_order_items(tenant_id, order["id"])
        total = sum(float(item["unit_price"]) * item["quantity"] for item in items)

        # Set status and price
        await self.order_repo.update_order_status(order["id"], "confirmed")
        await self.order_repo.set_order_price(order["id"], total)

        # Audit log
        before_state = dict(order)
        if before_state.get("started_at") and not isinstance(before_state["started_at"], str):
            before_state["started_at"] = before_state["started_at"].isoformat()

        after_state = dict(before_state)
        after_state["status"] = "confirmed"
        after_state["total_price"] = total

        await self.audit_repo.log_audit_event(
            tenant_id=tenant_id,
            action="order_status_change",
            target_type="order",
            target_id=str(order["id"]),
            before_state=before_state,
            after_state=after_state,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return {"order_uid": order_uid, "status": "confirmed", "total_price": total}

    async def cancel_order(
        self,
        tenant_id: str,
        order_uid: str,
        reason: str = "user_cancelled",
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> dict:
        order = await self.order_repo.get_order_by_uid(tenant_id, order_uid)
        if not order:
            raise OrderNotFoundError("Order not found")

        assert_valid_transition(order["status"], "cancelled")

        # Set status
        await self.order_repo.update_order_status(order["id"], "cancelled")

        # Audit log
        before_state = dict(order)
        if before_state.get("started_at") and not isinstance(before_state["started_at"], str):
            before_state["started_at"] = before_state["started_at"].isoformat()

        after_state = dict(before_state)
        after_state["status"] = "cancelled"

        await self.audit_repo.log_audit_event(
            tenant_id=tenant_id,
            action="order_status_change",
            target_type="order",
            target_id=str(order["id"]),
            before_state=before_state,
            after_state=after_state,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return {"order_uid": order_uid, "status": "cancelled"}

    async def get_chef_orders(self, tenant_id: str) -> List[Dict]:
        return await self.order_repo.get_chef_pipeline(tenant_id)

    async def get_cashier_orders(self, tenant_id: str) -> List[Dict]:
        return await self.order_repo.get_cashier_pipeline(tenant_id)

    async def pay_order(
        self,
        tenant_id: str,
        order_id: int,
        payment_method: str,
        amount_tendered: Optional[float],
        user_id: int,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> dict:
        valid_methods = ("cash", "card", "wallet")
        if payment_method not in valid_methods:
            raise ValueError(f"Invalid payment method. Must be one of {valid_methods}")

        order = await self.order_repo.get_order_by_id(tenant_id, order_id)
        if not order:
            raise OrderNotFoundError("Order not found")

        if order["status"] == "completed":
            raise OrderStatusConflictError("Order is already completed")

        assert_valid_transition(order["status"], "completed")

        # Record payment
        total_price = float(order["total_price"])
        await self.order_repo.record_payment(
            tenant_id, order_id, payment_method, amount_tendered, total_price
        )

        # Update order status & closed time
        now = datetime.utcnow()
        await self.order_repo.update_order_status(order_id, "completed")
        await self.order_repo.set_order_completed_at(order_id, now)

        # Audit log logic
        before_state = dict(order)
        if before_state.get("started_at") and not isinstance(before_state["started_at"], str):
            before_state["started_at"] = before_state["started_at"].isoformat()

        after_state = dict(before_state)
        after_state["status"] = "completed"
        after_state["completed_at"] = now.isoformat()

        await self.audit_repo.log_audit_event(
            tenant_id=tenant_id,
            action="order_status_change",
            target_type="order",
            target_id=str(order_id),
            user_id=user_id,
            before_state=before_state,
            after_state=after_state,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        change = None
        if payment_method == "cash" and amount_tendered is not None:
            change = round(amount_tendered - total_price, 2)

        return {
            "status": "paid",
            "order_id": order_id,
            "payment_method": payment_method,
            "total_price": total_price,
            "amount_tendered": amount_tendered,
            "change": change,
        }

    async def update_order_status(
        self,
        tenant_id: str,
        order_id: int,
        new_status: str,
        user_id: int,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> dict:
        order = await self.order_repo.get_order_by_id(tenant_id, order_id)
        if not order:
            raise OrderNotFoundError("Order not found")

        assert_valid_transition(order["status"], new_status)

        await self.order_repo.update_order_status(order_id, new_status)

        # Audit
        before_state = dict(order)
        if before_state.get("started_at") and not isinstance(before_state["started_at"], str):
            before_state["started_at"] = before_state["started_at"].isoformat()

        after_state = dict(before_state)
        after_state["status"] = new_status

        await self.audit_repo.log_audit_event(
            tenant_id=tenant_id,
            action="order_status_change",
            target_type="order",
            target_id=str(order_id),
            user_id=user_id,
            before_state=before_state,
            after_state=after_state,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return {"status": "updated", "id": order_id, "new_status": new_status}
