"""
MySQL implementation of the ProductRepository contract.
"""
from typing import Optional, List, Dict
import aiomysql
import json

from backend.application.interfaces.product_repository import ProductRepository


class MysqlProductRepo(ProductRepository):
    def __init__(self, conn: aiomysql.Connection):
        self.conn = conn

    async def get_product(self, tenant_id: str, product_id: int) -> Optional[dict]:
        async with self.conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT * FROM products WHERE tenant_id = %s AND id = %s",
                (tenant_id, product_id)
            )
            row = await cur.fetchone()
            if row:
                # Parse JSON fields to match main.py fetchall behavior
                for key in ("ingredients", "allergens"):
                    if key in row and isinstance(row[key], str):
                        try:
                            row[key] = json.loads(row[key])
                        except Exception:
                            row[key] = []
            return row

    async def get_department_products(self, tenant_id: str, department_id: int) -> List[Dict]:
        async with self.conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT * FROM products WHERE tenant_id = %s AND department_id = %s",
                (tenant_id, department_id)
            )
            rows = await cur.fetchall()
            for row in rows:
                for key in ("ingredients", "allergens"):
                    if key in row and isinstance(row[key], str):
                        try:
                            row[key] = json.loads(row[key])
                        except Exception:
                            row[key] = []
            return rows

    async def create_product(self, tenant_id: str, prod: dict) -> int:
        async with self.conn.cursor() as cur:
            await cur.execute(
                """INSERT INTO products
                   (tenant_id, department_id, name_en, name_ar, description_en, description_ar, price, currency,
                    ingredients, calories, allergens, media_type, media_path, thumbnail_path, available, featured, qr_order_url)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    tenant_id,
                    prod["department_id"],
                    prod["name_en"],
                    prod["name_ar"],
                    prod.get("description_en"),
                    prod.get("description_ar"),
                    prod["price"],
                    prod.get("currency", "EGP"),
                    json.dumps(prod.get("ingredients", [])),
                    prod.get("calories", 0),
                    json.dumps(prod.get("allergens", [])),
                    prod.get("media_type", "image"),
                    prod.get("media_path"),
                    prod.get("thumbnail_path"),
                    prod.get("available", True),
                    prod.get("featured", False),
                    prod.get("qr_order_url"),
                )
            )
            return cur.lastrowid

    async def update_product(self, tenant_id: str, product_id: int, prod: dict) -> None:
        async with self.conn.cursor() as cur:
            await cur.execute(
                """UPDATE products
                   SET department_id = %s, name_en = %s, name_ar = %s, description_en = %s, description_ar = %s,
                       price = %s, currency = %s, ingredients = %s, calories = %s, allergens = %s,
                       media_type = %s, media_path = %s, thumbnail_path = %s, available = %s, featured = %s, qr_order_url = %s
                   WHERE tenant_id = %s AND id = %s""",
                (
                    prod["department_id"],
                    prod["name_en"],
                    prod["name_ar"],
                    prod.get("description_en"),
                    prod.get("description_ar"),
                    prod["price"],
                    prod.get("currency", "EGP"),
                    json.dumps(prod.get("ingredients", [])),
                    prod.get("calories", 0),
                    json.dumps(prod.get("allergens", [])),
                    prod.get("media_type", "image"),
                    prod.get("media_path"),
                    prod.get("thumbnail_path"),
                    prod.get("available", True),
                    prod.get("featured", False),
                    prod.get("qr_order_url"),
                    tenant_id,
                    product_id,
                )
            )

    async def delete_product(self, tenant_id: str, product_id: int) -> None:
        async with self.conn.cursor() as cur:
            await cur.execute(
                "UPDATE products SET available = FALSE WHERE tenant_id = %s AND id = %s",
                (tenant_id, product_id)
            )

