"""
MySQL implementation of the DepartmentRepository contract.
"""
from typing import Optional, List, Dict
import aiomysql

from backend.application.interfaces.department_repository import DepartmentRepository


class MysqlDepartmentRepo(DepartmentRepository):
    def __init__(self, conn: aiomysql.Connection):
        self.conn = conn

    async def get_departments(self, tenant_id: str) -> List[Dict]:
        async with self.conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT * FROM departments WHERE tenant_id = %s AND active = TRUE ORDER BY display_order ASC",
                (tenant_id,)
            )
            return await cur.fetchall()

    async def get_department(self, tenant_id: str, dept_id: int) -> Optional[dict]:
        async with self.conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT * FROM departments WHERE tenant_id = %s AND id = %s",
                (tenant_id, dept_id)
            )
            return await cur.fetchone()

    async def create_department(self, tenant_id: str, dept: dict) -> int:
        async with self.conn.cursor() as cur:
            await cur.execute(
                """INSERT INTO departments (tenant_id, name_en, name_ar, display_order, active)
                   VALUES (%s, %s, %s, %s, %s)""",
                (
                    tenant_id,
                    dept["name_en"],
                    dept["name_ar"],
                    dept.get("display_order", 0),
                    dept.get("active", True),
                )
            )
            return cur.lastrowid

    async def update_department(self, tenant_id: str, dept_id: int, dept: dict) -> None:
        async with self.conn.cursor() as cur:
            await cur.execute(
                """UPDATE departments
                   SET name_en = %s, name_ar = %s, display_order = %s, active = %s
                   WHERE tenant_id = %s AND id = %s""",
                (
                    dept["name_en"],
                    dept["name_ar"],
                    dept.get("display_order", 0),
                    dept.get("active", True),
                    tenant_id,
                    dept_id,
                )
            )

    async def delete_department(self, tenant_id: str, dept_id: int) -> None:
        async with self.conn.cursor() as cur:
            # Soft delete by setting active = FALSE
            await cur.execute(
                "UPDATE departments SET active = FALSE WHERE tenant_id = %s AND id = %s",
                (tenant_id, dept_id)
            )
