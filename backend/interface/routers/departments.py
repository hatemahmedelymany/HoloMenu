"""
Department configuration CRUD endpoints router.
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from backend.infrastructure.database.pool import get_db_conn
from backend.infrastructure.database.mysql_department_repo import MysqlDepartmentRepo
from backend.infrastructure.database.mysql_audit_repo import MysqlAuditRepo
from backend.application.use_cases.departments import DepartmentUseCases, DepartmentNotFoundError
from backend.interface.dependencies import get_current_tenant_id, require_role

router = APIRouter(tags=["departments"])


class DepartmentSchema(BaseModel):
    name_en: str
    name_ar: str
    display_order: int = 0
    active: bool = True
    model_config = ConfigDict(extra="forbid")


@router.get("/api/departments")
async def get_departments(
    tenant_id: str = Depends(get_current_tenant_id),
    conn=Depends(get_db_conn),
):
    department_repo = MysqlDepartmentRepo(conn)
    audit_repo = MysqlAuditRepo(conn)
    use_cases = DepartmentUseCases(department_repo, audit_repo)

    result = await use_cases.get_departments(tenant_id)
    return result


@router.post("/api/departments", status_code=201)
async def create_department(
    request: Request,
    dept: DepartmentSchema,
    tenant_id: str = Depends(get_current_tenant_id),
    user: dict = Depends(require_role("admin", "owner")),
    conn=Depends(get_db_conn),
):
    department_repo = MysqlDepartmentRepo(conn)
    audit_repo = MysqlAuditRepo(conn)
    use_cases = DepartmentUseCases(department_repo, audit_repo)

    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    result = await use_cases.create_department(
        tenant_id=tenant_id,
        user_id=user["admin_id"],
        dept_data=dept.model_dump(),
        ip_address=ip,
        user_agent=ua,
    )
    return result


@router.put("/api/departments/{dept_id}")
async def update_department(
    request: Request,
    dept_id: int,
    dept: DepartmentSchema,
    tenant_id: str = Depends(get_current_tenant_id),
    user: dict = Depends(require_role("admin", "owner")),
    conn=Depends(get_db_conn),
):
    department_repo = MysqlDepartmentRepo(conn)
    audit_repo = MysqlAuditRepo(conn)
    use_cases = DepartmentUseCases(department_repo, audit_repo)

    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    try:
        result = await use_cases.update_department(
            tenant_id=tenant_id,
            dept_id=dept_id,
            user_id=user["admin_id"],
            dept_data=dept.model_dump(),
            ip_address=ip,
            user_agent=ua,
        )
        return result
    except DepartmentNotFoundError:
        raise HTTPException(status_code=404, detail="Department not found")


@router.delete("/api/departments/{dept_id}")
async def delete_department(
    request: Request,
    dept_id: int,
    tenant_id: str = Depends(get_current_tenant_id),
    user: dict = Depends(require_role("admin", "owner")),
    conn=Depends(get_db_conn),
):
    department_repo = MysqlDepartmentRepo(conn)
    audit_repo = MysqlAuditRepo(conn)
    use_cases = DepartmentUseCases(department_repo, audit_repo)

    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    try:
        result = await use_cases.delete_department(
            tenant_id=tenant_id,
            dept_id=dept_id,
            user_id=user["admin_id"],
            ip_address=ip,
            user_agent=ua,
        )
        return result
    except DepartmentNotFoundError:
        raise HTTPException(status_code=404, detail="Department not found")
