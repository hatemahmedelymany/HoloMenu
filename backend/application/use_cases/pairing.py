import random
import uuid
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict
from backend.application.interfaces.kiosk_repository import KioskRepository
from backend.infrastructure.security.auth import create_websocket_session_token

# In-memory store for pending pairing PINs.
# Format: { "pin": { "tenant_id": str, "name": str, "expires_at": datetime } }
PENDING_PAIRS: Dict[str, dict] = {}

class PairingUseCase:
    def __init__(self, kiosk_repo: KioskRepository, audit_repo=None):
        self.kiosk_repo = kiosk_repo
        self.audit_repo = audit_repo

    async def request_pairing(self, tenant_id: str, kiosk_name: str) -> str:
        """
        Request a 6-digit short-lived PIN for pairing a new kiosk.
        Verifies plan limits before generating PIN.
        """
        # Fetch limits
        limits = await self.kiosk_repo.get_tenant_limits(tenant_id)
        if not limits:
            if self.audit_repo:
                await self.audit_repo.log_audit_event(
                    tenant_id=tenant_id,
                    action="request_pairing_failed",
                    target_type="kiosk",
                    after_state={"kiosk_name": kiosk_name, "error": "Tenant not found"}
                )
            raise ValueError("Tenant not found")

        max_kiosks = limits.get("max_kiosks", 1)

        # Count active kiosks
        active_count = await self.kiosk_repo.count_active_kiosks(tenant_id)

        if active_count >= max_kiosks:
            if self.audit_repo:
                await self.audit_repo.log_audit_event(
                    tenant_id=tenant_id,
                    action="request_pairing_failed",
                    target_type="kiosk",
                    after_state={"kiosk_name": kiosk_name, "error": "Kiosk limit reached"}
                )
            raise PermissionError("Kiosk limit reached for your subscription plan")

        # Clean up any duplicate active pairing requests for this kiosk name and tenant
        for key, val in list(PENDING_PAIRS.items()):
            if val["tenant_id"] == tenant_id and val["name"] == kiosk_name:
                PENDING_PAIRS.pop(key, None)

        # Generate a unique 6-digit PIN
        pin = None
        for _ in range(10):  # Retry to handle rare collisions
            temp_pin = f"{random.randint(100000, 999999)}"
            if temp_pin not in PENDING_PAIRS:
                pin = temp_pin
                break
        
        if not pin:
            raise RuntimeError("Failed to generate pairing PIN")

        # Store in-memory, valid for 5 minutes
        expires_at = datetime.utcnow() + timedelta(minutes=5)
        PENDING_PAIRS[pin] = {
            "tenant_id": tenant_id,
            "name": kiosk_name,
            "expires_at": expires_at,
            "attempts": 0
        }

        if self.audit_repo:
            await self.audit_repo.log_audit_event(
                tenant_id=tenant_id,
                action="request_pairing_success",
                target_type="kiosk",
                after_state={"kiosk_name": kiosk_name}
            )

        return pin

    async def verify_pairing(self, pin: str, device_id: str) -> dict:
        """
        Validate pairing PIN and create the kiosk and WebSocket session token.
        """
        # Clean expired PINs
        now = datetime.utcnow()
        expired_keys = [k for k, v in PENDING_PAIRS.items() if v["expires_at"] < now]
        for k in expired_keys:
            PENDING_PAIRS.pop(k, None)

        if pin not in PENDING_PAIRS:
            if self.audit_repo:
                await self.audit_repo.log_audit_event(
                    tenant_id="d4444444-4444-4444-4444-444444444444",
                    action="verify_pairing_failed",
                    target_type="kiosk",
                    after_state={"error": "Invalid or expired pairing PIN", "device_id": device_id}
                )
            raise ValueError("Invalid or expired pairing PIN")

        pair_data = PENDING_PAIRS[pin]
        tenant_id = pair_data["tenant_id"]
        kiosk_name = pair_data["name"]

        # Increment attempts
        pair_data["attempts"] = pair_data.get("attempts", 0) + 1
        if pair_data["attempts"] > 5:
            PENDING_PAIRS.pop(pin, None)
            if self.audit_repo:
                await self.audit_repo.log_audit_event(
                    tenant_id=tenant_id,
                    action="verify_pairing_failed",
                    target_type="kiosk",
                    after_state={"error": "PIN attempts exhausted", "kiosk_name": kiosk_name, "device_id": device_id}
                )
            raise ValueError("Invalid or expired pairing PIN")

        # Double check limits at verification time to prevent race conditions
        limits = await self.kiosk_repo.get_tenant_limits(tenant_id)
        if not limits:
            if self.audit_repo:
                await self.audit_repo.log_audit_event(
                    tenant_id=tenant_id,
                    action="verify_pairing_failed",
                    target_type="kiosk",
                    after_state={"error": "Tenant not found", "kiosk_name": kiosk_name, "device_id": device_id}
                )
            raise ValueError("Tenant not found")
            
        max_kiosks = limits.get("max_kiosks", 1)
        active_count = await self.kiosk_repo.count_active_kiosks(tenant_id)
        if active_count >= max_kiosks:
            if self.audit_repo:
                await self.audit_repo.log_audit_event(
                    tenant_id=tenant_id,
                    action="verify_pairing_failed",
                    target_type="kiosk",
                    after_state={"error": "Kiosk limit reached", "kiosk_name": kiosk_name, "device_id": device_id}
                )
            raise PermissionError("Kiosk limit reached for your subscription plan")

        # PIN verified successfully! Pop it.
        PENDING_PAIRS.pop(pin)

        # Register kiosk
        kiosk_id = str(uuid.uuid4())
        secret = secrets.token_urlsafe(32)
        await self.kiosk_repo.create_kiosk(kiosk_id, tenant_id, kiosk_name, secret, device_id, "active")

        # Generate session token (24 hours expiry)
        token = create_websocket_session_token(tenant_id, kiosk_id, device_id, expires_in_hours=24)
        expires_at = datetime.utcnow() + timedelta(hours=24)

        # Save session to DB
        await self.kiosk_repo.create_websocket_session(token, tenant_id, kiosk_id, device_id, expires_at)

        if self.audit_repo:
            await self.audit_repo.log_audit_event(
                tenant_id=tenant_id,
                action="verify_pairing_success",
                target_type="kiosk",
                target_id=kiosk_id,
                after_state={"kiosk_name": kiosk_name, "device_id": device_id}
            )

        return {
            "token": token,
            "kiosk_id": kiosk_id,
            "name": kiosk_name,
            "secret": secret
        }
