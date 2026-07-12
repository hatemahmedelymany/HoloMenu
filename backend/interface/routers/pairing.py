from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, Field
import aiomysql

from backend.infrastructure.database.pool import get_db_conn
from backend.infrastructure.database.mysql_kiosk_repo import MysqlKioskRepo
from backend.infrastructure.database.mysql_audit_repo import MysqlAuditRepo
from backend.application.use_cases.pairing import PairingUseCase
from backend.interface.dependencies import get_current_tenant_id, require_role
from backend.infrastructure.security.limiter import limiter

router = APIRouter(tags=["pairing"])


class PairingRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class PairingVerification(BaseModel):
    pin: str = Field(..., min_length=6, max_length=6)
    device_id: str = Field(..., min_length=1, max_length=255)


@router.post("/api/pairing/request")
@limiter.limit("5/minute")
async def request_pairing(
    request: Request,
    payload: PairingRequest,
    conn: aiomysql.Connection = Depends(get_db_conn),
    tenant_id: str = Depends(get_current_tenant_id),
    _user: dict = Depends(require_role("admin")),
):
    """
    Request a 6-digit PIN for pairing a new kiosk.
    Requires Admin privileges and verifies the kiosk limits of the tenant.
    """
    repo = MysqlKioskRepo(conn)
    audit_repo = MysqlAuditRepo(conn)
    use_case = PairingUseCase(repo, audit_repo)
    try:
        pin = await use_case.request_pairing(tenant_id, payload.name)
        return {"pin": pin, "expires_in": 300}
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/api/pairing/verify")
@limiter.limit("20/minute")
async def verify_pairing(
    request: Request,
    payload: PairingVerification,
    conn: aiomysql.Connection = Depends(get_db_conn),
):
    """
    Verify the pairing PIN and return a signed short-lived WebSocket token.
    This does not require a prior user token since the kiosk itself is not yet paired.
    """
    repo = MysqlKioskRepo(conn)
    audit_repo = MysqlAuditRepo(conn)
    use_case = PairingUseCase(repo, audit_repo)
    try:
        result = await use_case.verify_pairing(payload.pin, payload.device_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
