"""
Authentication and session endpoints router.
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response, Cookie
from pydantic import BaseModel, ConfigDict

from backend.infrastructure.database.pool import get_db_conn
from backend.infrastructure.database.mysql_auth_repo import MysqlAuthRepo
from backend.infrastructure.database.mysql_audit_repo import MysqlAuditRepo
from backend.application.use_cases.auth import (
    AuthUseCases,
    InvalidCredentialsError,
    RevokedTokenError,
)
from backend.infrastructure.security.auth import REFRESH_TOKEN_EXPIRE_DAYS

router = APIRouter(tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str
    model_config = ConfigDict(extra="forbid")


@router.post("/api/auth/login")
async def login(
    request: Request,
    login_data: LoginRequest,
    response: Response,
    conn=Depends(get_db_conn),
):
    # Retrieve tenant slug/id context from request state
    tenant_slug = getattr(request.state, "tenant_slug", "demo")
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context missing")

    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    auth_repo = MysqlAuthRepo(conn)
    audit_repo = MysqlAuditRepo(conn)
    use_cases = AuthUseCases(auth_repo, audit_repo)

    try:
        res_dict, refresh_token = await use_cases.login(
            tenant_id=tenant_id,
            username=login_data.username,
            password=login_data.password,
            ip_address=ip,
            user_agent=ua,
        )

        # Set persistent secure cookie
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        )

        return res_dict
    except InvalidCredentialsError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.post("/api/auth/refresh")
async def refresh(
    request: Request,
    response: Response,
    refresh_token: Optional[str] = Cookie(None),
    conn=Depends(get_db_conn),
):
    if not refresh_token:
        raise HTTPException(status_code=400, detail="Refresh token missing")

    auth_repo = MysqlAuthRepo(conn)
    audit_repo = MysqlAuditRepo(conn)
    use_cases = AuthUseCases(auth_repo, audit_repo)

    try:
        new_res = await use_cases.refresh(refresh_token)
        return new_res
    except InvalidCredentialsError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except RevokedTokenError as e:
        response.delete_cookie("refresh_token")
        raise HTTPException(status_code=401, detail=str(e))


@router.post("/api/auth/logout")
async def logout(
    request: Request,
    response: Response,
    refresh_token: Optional[str] = Cookie(None),
    conn=Depends(get_db_conn),
):
    tenant_id = getattr(request.state, "tenant_id", None)
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    auth_repo = MysqlAuthRepo(conn)
    audit_repo = MysqlAuditRepo(conn)
    use_cases = AuthUseCases(auth_repo, audit_repo)

    # Invalidate session in use actions
    await use_cases.logout(
        refresh_token=refresh_token,
        fallback_tenant_id=tenant_id,
        ip_address=ip,
        user_agent=ua,
    )

    # Erase browser cookie
    response.delete_cookie("refresh_token")
    return {"detail": "Logged out successfully"}
