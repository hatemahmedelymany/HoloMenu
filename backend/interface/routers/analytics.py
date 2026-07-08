"""
Telemetry and user interaction analytics event logging endpoints router.
"""
from typing import Optional, List
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from backend.infrastructure.database.pool import get_db_conn
from backend.infrastructure.database.mysql_analytics_repo import MysqlAnalyticsRepo
from backend.application.use_cases.analytics import AnalyticsUseCases
from backend.interface.dependencies import get_current_tenant_id, require_role

router = APIRouter(tags=["analytics"])


class AnalyticsEvent(BaseModel):
    event_type: str
    session_uid: str
    product_id: Optional[int] = None
    department_id: Optional[int] = None
    meta: Optional[dict] = None
    model_config = ConfigDict(extra="forbid")


@router.post("/api/analytics/events", status_code=201)
async def log_event(
    evt: AnalyticsEvent,
    tenant_id: str = Depends(get_current_tenant_id),
    conn=Depends(get_db_conn),
):
    analytics_repo = MysqlAnalyticsRepo(conn)
    use_cases = AnalyticsUseCases(analytics_repo)
    return await use_cases.log_event(tenant_id, evt.model_dump())


@router.get("/api/analytics/summary")
async def analytics_summary(
    tenant_id: str = Depends(get_current_tenant_id),
    user: dict = Depends(require_role("admin", "owner")),
    conn=Depends(get_db_conn),
):
    analytics_repo = MysqlAnalyticsRepo(conn)
    use_cases = AnalyticsUseCases(analytics_repo)
    return await use_cases.get_event_summary(tenant_id)
