"""
Use cases orchestration administrative functions.
"""
from typing import List, Dict
from datetime import datetime

from backend.application.interfaces.order_repository import OrderRepository


class AdminUseCases:
    def __init__(self, order_repo: OrderRepository):
        self.order_repo = order_repo

    async def get_admin_orders(self, tenant_id: str) -> List[Dict]:
        orders = await self.order_repo.get_admin_orders(tenant_id)
        if not orders:
            return []

        order_ids = [o["id"] for o in orders]
        items = await self.order_repo.get_admin_order_items(tenant_id, order_ids)

        # Group items by order ID
        items_by_order = {}
        for item in items:
            oid = item["order_id"]
            if oid not in items_by_order:
                items_by_order[oid] = []
            items_by_order[oid].append({
                "product_id": item["product_id"],
                "quantity": item["quantity"],
                "name_en": item["name_en"],
                "name_ar": item["name_ar"],
                "unit_price": item["unit_price"]
            })

        # Format and group items
        for o in orders:
            o["items"] = items_by_order.get(o["id"], [])
            o["total_price"] = float(o["total_price"])
            if o.get("started_at") and not isinstance(o["started_at"], str):
                o["started_at"] = o["started_at"].isoformat()
            if o.get("completed_at") and not isinstance(o["completed_at"], str):
                o["completed_at"] = o["completed_at"].isoformat()

        return orders

    async def get_admin_stats(self, tenant_id: str) -> dict:
        return await self.order_repo.get_admin_stats(tenant_id)
