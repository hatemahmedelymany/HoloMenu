"""
MySQL deployment implementation of the OrderRepository contract using aiomysql.
"""
import json
from datetime import datetime
from typing import Optional, List, Dict
import aiomysql

from backend.application.interfaces.order_repository import OrderRepository


class MysqlOrderRepo(OrderRepository):
    def __init__(self, conn: aiomysql.Connection):
        self.conn = conn

    async def create_order(self, tenant_id: str, order_uid: str) -> None:
        async with self.conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO orders (order_uid, tenant_id, status) VALUES (%s, %s, 'pending')",
                (order_uid, tenant_id)
            )

    async def get_order_by_uid(self, tenant_id: str, order_uid: str) -> Optional[dict]:
        async with self.conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT * FROM orders WHERE tenant_id = %s AND order_uid = %s",
                (tenant_id, order_uid)
            )
            return await cur.fetchone()

    async def get_order_by_id(self, tenant_id: str, order_id: int) -> Optional[dict]:
        async with self.conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT * FROM orders WHERE tenant_id = %s AND id = %s",
                (tenant_id, order_id)
            )
            return await cur.fetchone()

    async def get_item(self, tenant_id: str, order_id: int, product_id: int) -> Optional[dict]:
        async with self.conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT id, quantity FROM order_items WHERE tenant_id = %s AND order_id = %s AND product_id = %s",
                (tenant_id, order_id, product_id)
            )
            return await cur.fetchone()

    async def add_item(self, tenant_id: str, order_id: int, product_id: int, quantity: int, unit_price: float) -> None:
        async with self.conn.cursor() as cur:
            await cur.execute(
                """INSERT INTO order_items (tenant_id, order_id, product_id, quantity, unit_price)
                   VALUES (%s, %s, %s, %s, %s)""",
                (tenant_id, order_id, product_id, quantity, unit_price)
            )

    async def update_item_quantity(self, tenant_id: str, order_id: int, product_id: int, quantity: int) -> None:
        async with self.conn.cursor() as cur:
            await cur.execute(
                "UPDATE order_items SET quantity = %s WHERE tenant_id = %s AND order_id = %s AND product_id = %s",
                (quantity, tenant_id, order_id, product_id)
            )

    async def remove_item(self, tenant_id: str, order_id: int, product_id: int) -> None:
        async with self.conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM order_items WHERE tenant_id = %s AND order_id = %s AND product_id = %s",
                (tenant_id, order_id, product_id)
            )

    async def get_order_items(self, tenant_id: str, order_id: int) -> List[Dict]:
        async with self.conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                """SELECT oi.product_id, oi.quantity, oi.unit_price, p.name_en, p.name_ar
                   FROM order_items oi
                   JOIN products p ON oi.product_id = p.id
                   WHERE oi.tenant_id = %s AND oi.order_id = %s""",
                (tenant_id, order_id)
            )
            rows = await cur.fetchall()
            for r in rows:
                if "unit_price" in r and r["unit_price"] is not None:
                    r["unit_price"] = float(r["unit_price"])
            return rows

    async def update_order_status(self, order_id: int, status: str) -> None:
        completed_at = datetime.utcnow() if status in ("completed", "cancelled") else None
        async with self.conn.cursor() as cur:
            await cur.execute(
                "UPDATE orders SET status = %s, completed_at = %s WHERE id = %s",
                (status, completed_at, order_id)
            )

    async def update_order_status_by_uid(self, order_uid: str, status: str) -> None:
        completed_at = datetime.utcnow() if status in ("completed", "cancelled") else None
        async with self.conn.cursor() as cur:
            await cur.execute(
                "UPDATE orders SET status = %s, completed_at = %s WHERE order_uid = %s",
                (status, completed_at, order_uid)
            )

    async def set_order_price(self, order_id: int, total_price: float) -> None:
        async with self.conn.cursor() as cur:
            await cur.execute(
                "UPDATE orders SET total_price = %s WHERE id = %s",
                (total_price, order_id)
            )

    async def get_chef_pipeline(self, tenant_id: str) -> List[Dict]:
        async with self.conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                """SELECT id, order_uid, status, total_price, started_at
                   FROM orders
                   WHERE tenant_id = %s AND status IN ('confirmed', 'cooking', 'ready')
                   ORDER BY started_at ASC""",
                (tenant_id,)
            )
            orders = await cur.fetchall()
            if not orders:
                return []

            order_ids = [o["id"] for o in orders]
            format_strings = ','.join(['%s'] * len(order_ids))
            await cur.execute(
                f"""SELECT oi.order_id, oi.product_id, oi.quantity, p.name_en, p.name_ar
                   FROM order_items oi
                   JOIN products p ON oi.product_id = p.id
                   WHERE oi.order_id IN ({format_strings})""",
                tuple(order_ids)
            )
            items = await cur.fetchall()

            items_by_order = {}
            for item in items:
                oid = item["order_id"]
                if oid not in items_by_order:
                    items_by_order[oid] = []
                items_by_order[oid].append({
                    "product_id": item["product_id"],
                    "quantity": item["quantity"],
                    "name_en": item["name_en"],
                    "name_ar": item["name_ar"]
                })

            for o in orders:
                o["items"] = items_by_order.get(o["id"], [])
                if o.get("total_price") is not None:
                    o["total_price"] = float(o["total_price"])
            return orders

    async def get_cashier_pipeline(self, tenant_id: str) -> List[Dict]:
        async with self.conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                """SELECT id, order_uid, status, total_price, started_at
                   FROM orders
                   WHERE tenant_id = %s AND status IN ('confirmed', 'cooking', 'ready')
                   ORDER BY started_at ASC""",
                (tenant_id,)
            )
            orders = await cur.fetchall()
            if not orders:
                return []

            order_ids = [o["id"] for o in orders]
            format_strings = ','.join(['%s'] * len(order_ids))
            await cur.execute(
                f"""SELECT oi.order_id, oi.product_id, oi.quantity, oi.unit_price, p.name_en, p.name_ar
                   FROM order_items oi
                   JOIN products p ON oi.product_id = p.id
                   WHERE oi.order_id IN ({format_strings})""",
                tuple(order_ids)
            )
            items = await cur.fetchall()

            items_by_order = {}
            for item in items:
                oid = item["order_id"]
                if oid not in items_by_order:
                    items_by_order[oid] = []
                items_by_order[oid].append({
                    "product_id": item["product_id"],
                    "quantity": item["quantity"],
                    "unit_price": float(item["unit_price"]),
                    "name_en": item["name_en"],
                    "name_ar": item["name_ar"]
                })

            for o in orders:
                o["items"] = items_by_order.get(o["id"], [])
                if o.get("total_price") is not None:
                    o["total_price"] = float(o["total_price"])
                if o.get("started_at") and not isinstance(o["started_at"], str):
                    o["started_at"] = o["started_at"].isoformat()
            return orders

    async def record_payment(
        self,
        tenant_id: str,
        order_id: int,
        payment_method: str,
        amount_tendered: Optional[float],
        amount_paid: float
    ) -> None:
        async with self.conn.cursor() as cur:
            await cur.execute(
                """INSERT INTO payments (tenant_id, order_id, payment_method, amount_tendered, amount_paid)
                   VALUES (%s, %s, %s, %s, %s)""",
                (tenant_id, order_id, payment_method, amount_tendered, amount_paid)
            )

    async def set_order_completed_at(self, order_id: int, completed_at: datetime) -> None:
        async with self.conn.cursor() as cur:
            await cur.execute(
                "UPDATE orders SET completed_at = %s WHERE id = %s",
                (completed_at, order_id)
            )

    async def get_admin_orders(self, tenant_id: str) -> List[Dict]:
        async with self.conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                """SELECT id, order_uid, status, total_price, started_at, completed_at
                   FROM orders
                   WHERE tenant_id = %s
                   ORDER BY started_at DESC""",
                (tenant_id,)
            )
            orders = await cur.fetchall()
            return orders

    async def get_admin_order_items(self, tenant_id: str, order_ids: List[int]) -> List[Dict]:
        async with self.conn.cursor(aiomysql.DictCursor) as cur:
            format_strings = ','.join(['%s'] * len(order_ids))
            await cur.execute(
                f"""SELECT oi.order_id, oi.product_id, oi.quantity, p.name_en, p.name_ar, oi.unit_price
                    FROM order_items oi
                    JOIN products p ON oi.product_id = p.id
                    WHERE oi.tenant_id = %s AND oi.order_id IN ({format_strings})""",
                tuple([tenant_id] + list(order_ids))
            )
            items = await cur.fetchall()
            for r in items:
                if "unit_price" in r and r["unit_price"] is not None:
                    r["unit_price"] = float(r["unit_price"])
            return items

    async def get_admin_stats(self, tenant_id: str) -> dict:
        async with self.conn.cursor(aiomysql.DictCursor) as cur:
            # 1. Total completed order count and completed revenue
            await cur.execute(
                """SELECT COUNT(*) as total_orders, COALESCE(SUM(total_price), 0) as total_revenue
                   FROM orders WHERE tenant_id = %s AND status = 'completed'""",
                (tenant_id,)
            )
            revenue_stats = await cur.fetchone()

            # 2. Avg Order Value
            await cur.execute(
                """SELECT COALESCE(AVG(total_price), 0) as avg_order_value
                   FROM orders WHERE tenant_id = %s AND status = 'completed'""",
                (tenant_id,)
            )
            avg_stats = await cur.fetchone()

            # 3. Counts by status
            await cur.execute(
                """SELECT status, COUNT(*) as count FROM orders WHERE tenant_id = %s GROUP BY status""",
                (tenant_id,)
            )
            status_rows = await cur.fetchall()
            status_counts = {r["status"]: r["count"] for r in status_rows}

            # 4. Popular Items
            await cur.execute(
                """SELECT p.name_en, COUNT(oi.id) as order_count, SUM(oi.quantity) as total_quantity
                   FROM order_items oi
                   JOIN products p ON oi.product_id = p.id
                   WHERE p.tenant_id = %s
                   GROUP BY p.id
                   ORDER BY total_quantity DESC LIMIT 5""",
                (tenant_id,)
            )
            popular_items = await cur.fetchall()

            return {
                "completed_orders": revenue_stats["total_orders"],
                "total_revenue": float(revenue_stats["total_revenue"]),
                "avg_order_value": float(avg_stats["avg_order_value"]),
                "status_counts": status_counts,
                "popular_items": popular_items
            }

