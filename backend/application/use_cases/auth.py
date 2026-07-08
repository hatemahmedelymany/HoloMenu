"""
Use Cases for Authentication, JWT rotation, and audit logs.
"""
from datetime import datetime, timedelta
from typing import Optional, Tuple
import jwt

from backend.application.interfaces.auth_repository import AuthRepository
from backend.application.interfaces.audit_repository import AuditRepository
from backend.infrastructure.security.auth import (
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    REFRESH_TOKEN_EXPIRE_DAYS,
)


class InvalidCredentialsError(Exception):
    pass


class RevokedTokenError(Exception):
    pass


class AuthUseCases:
    def __init__(self, auth_repo: AuthRepository, audit_repo: AuditRepository):
        self.auth_repo = auth_repo
        self.audit_repo = audit_repo

    async def login(
        self,
        tenant_id: str,
        username: str,
        password: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Tuple[dict, str]:
        """
        Authenticate admin username and password.
        Returns: Tuple[auth_result_dict, refresh_token_string]
        """
        admin = await self.auth_repo.get_admin_by_username(tenant_id, username)

        if not admin or not verify_password(password, admin["password_hash"]):
            # Log failed login attempt
            await self.audit_repo.log_audit_event(
                tenant_id=tenant_id,
                action="login_failed",
                target_type="admin",
                target_id=username,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            raise InvalidCredentialsError("Invalid username or password")

        access_token = create_access_token(tenant_id, admin["id"], admin["role"])
        refresh_token = create_refresh_token(tenant_id, admin["id"], admin["role"])

        # Persist refresh token in database
        expires_at = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        await self.auth_repo.save_refresh_token(
            tenant_id=tenant_id,
            admin_id=admin["id"],
            token=refresh_token,
            expires_at=expires_at,
        )

        # Log successful login
        await self.audit_repo.log_audit_event(
            tenant_id=tenant_id,
            action="login_success",
            target_type="admin",
            target_id=str(admin["id"]),
            user_id=admin["id"],
            ip_address=ip_address,
            user_agent=user_agent,
        )

        result_dict = {
            "access_token": access_token,
            "token_type": "bearer",
            "role": admin["role"],
        }
        return result_dict, refresh_token

    async def refresh(self, refresh_token: str) -> dict:
        """
        Validate database session and generate new access token.
        """
        try:
            payload = decode_refresh_token(refresh_token)
            admin_id = int(payload.get("sub"))
            tenant_id = payload.get("tenant_id")
            role = payload.get("role")
        except jwt.ExpiredSignatureError:
            raise InvalidCredentialsError("Refresh token has expired")
        except jwt.PyJWTError:
            raise InvalidCredentialsError("Invalid refresh token")

        # Verify against MySQL refresh_tokens table
        valid = await self.auth_repo.verify_refresh_token(tenant_id, refresh_token)
        if not valid:
            raise RevokedTokenError("Revoked or invalid refresh token")

        # Return new access token
        access_token = create_access_token(tenant_id, admin_id, role)
        return {"access_token": access_token, "token_type": "bearer"}

    async def logout(
        self,
        refresh_token: Optional[str],
        fallback_tenant_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        """
        Revoke refresh token and log audit info.
        """
        logged_out_admin_id = None
        tenant_id = fallback_tenant_id

        if refresh_token:
            try:
                # Decapsulate to retrieve metadata even if expired
                payload = decode_refresh_token(refresh_token)
                logged_out_admin_id = int(payload.get("sub"))
                if not tenant_id:
                    tenant_id = payload.get("tenant_id")
            except Exception:
                pass

            # Drop session
            await self.auth_repo.delete_refresh_token(refresh_token)

        # Log logout audit trail if tenant_id is available
        if tenant_id:
            await self.audit_repo.log_audit_event(
                tenant_id=tenant_id,
                action="logout",
                target_type="admin",
                target_id=str(logged_out_admin_id) if logged_out_admin_id else None,
                user_id=logged_out_admin_id,
                ip_address=ip_address,
                user_agent=user_agent,
            )
