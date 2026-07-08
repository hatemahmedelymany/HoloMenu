"""
Product configuration CRUD endpoints router.
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from backend.infrastructure.database.pool import get_db_conn
from backend.infrastructure.database.mysql_product_repo import MysqlProductRepo
from backend.infrastructure.database.mysql_audit_repo import MysqlAuditRepo
from backend.application.use_cases.products import ProductUseCases, ProductNotFoundError
from backend.interface.dependencies import get_current_tenant_id, require_role

router = APIRouter(tags=["products"])


class ProductSchema(BaseModel):
    department_id: int
    name_en: str
    name_ar: str
    description_en: Optional[str] = None
    description_ar: Optional[str] = None
    price: float
    currency: str = "EGP"
    ingredients: Optional[list] = None
    calories: Optional[int] = 0
    allergens: Optional[list] = None
    media_type: Optional[str] = "image"
    media_path: Optional[str] = None
    thumbnail_path: Optional[str] = None
    available: Optional[bool] = True
    featured: Optional[bool] = False
    qr_order_url: Optional[str] = None
    model_config = ConfigDict(extra="forbid")


@router.get("/api/products/{product_id}")
async def get_product(
    product_id: int,
    tenant_id: str = Depends(get_current_tenant_id),
    conn=Depends(get_db_conn),
):
    product_repo = MysqlProductRepo(conn)
    audit_repo = MysqlAuditRepo(conn)
    use_cases = ProductUseCases(product_repo, audit_repo)

    try:
        result = await use_cases.get_product(tenant_id, product_id)
        return result
    except ProductNotFoundError:
        raise HTTPException(status_code=404, detail="Product not found")


@router.get("/api/departments/{dept_id}/products")
async def get_department_products(
    dept_id: int,
    tenant_id: str = Depends(get_current_tenant_id),
    conn=Depends(get_db_conn),
):
    product_repo = MysqlProductRepo(conn)
    audit_repo = MysqlAuditRepo(conn)
    use_cases = ProductUseCases(product_repo, audit_repo)

    result = await use_cases.get_department_products(tenant_id, dept_id)
    return result


@router.post("/api/products", status_code=201)
async def create_product(
    request: Request,
    prod: ProductSchema,
    tenant_id: str = Depends(get_current_tenant_id),
    user: dict = Depends(require_role("admin", "owner")),
    conn=Depends(get_db_conn),
):
    product_repo = MysqlProductRepo(conn)
    audit_repo = MysqlAuditRepo(conn)
    use_cases = ProductUseCases(product_repo, audit_repo)

    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    result = await use_cases.create_product(
        tenant_id=tenant_id,
        user_id=user["admin_id"],
        prod_data=prod.model_dump(),
        ip_address=ip,
        user_agent=ua,
    )
    return result


@router.put("/api/products/{product_id}")
async def update_product(
    request: Request,
    product_id: int,
    prod: ProductSchema,
    tenant_id: str = Depends(get_current_tenant_id),
    user: dict = Depends(require_role("admin", "owner")),
    conn=Depends(get_db_conn),
):
    product_repo = MysqlProductRepo(conn)
    audit_repo = MysqlAuditRepo(conn)
    use_cases = ProductUseCases(product_repo, audit_repo)

    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    try:
        result = await use_cases.update_product(
            tenant_id=tenant_id,
            product_id=product_id,
            user_id=user["admin_id"],
            prod_data=prod.model_dump(),
            ip_address=ip,
            user_agent=ua,
        )
        return result
    except ProductNotFoundError:
        raise HTTPException(status_code=404, detail="Product not found")


@router.delete("/api/products/{product_id}")
async def delete_product(
    request: Request,
    product_id: int,
    tenant_id: str = Depends(get_current_tenant_id),
    user: dict = Depends(require_role("admin", "owner")),
    conn=Depends(get_db_conn),
):
    product_repo = MysqlProductRepo(conn)
    audit_repo = MysqlAuditRepo(conn)
    use_cases = ProductUseCases(product_repo, audit_repo)

    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    try:
        result = await use_cases.delete_product(
            tenant_id=tenant_id,
            product_id=product_id,
            user_id=user["admin_id"],
            ip_address=ip,
            user_agent=ua,
        )
        return result
    except ProductNotFoundError:
        raise HTTPException(status_code=404, detail="Product not found")
