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
    def __init__(self, kiosk_repo: KioskRepository):
        self.kiosk_repo = kiosk_repo

    async def request_pairing(self, tenant_id: str, kiosk_name: str) -> str:
        """
        Request a 6-digit short-lived PIN for pairing a new kiosk.
        Verifies plan limits before generating PIN.
        """
        # Fetch limits
        limits = await self.kiosk_repo.get_tenant_limits(tenant_id)
        if not limits:
            raise ValueError("Tenant not found")

        max_kiosks = limits.get("max_kiosks", 1)

        # Count active kiosks
        active_count = await self.kiosk_repo.count_active_kiosks(tenant_id)

        if active_count >= max_kiosks:
            raise PermissionError("Kiosk limit reached for your subscription plan")

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
            "expires_at": expires_at
        }
        return pin

    async def verify_pairing(self, pin: str) -> dict:
        """
        Validate pairing PIN and create the kiosk and WebSocket session token.
        """
        # Clean expired PINs
        now = datetime.utcnow()
        expired_keys = [k for k, v in PENDING_PAIRS.items() if v["expires_at"] < now]
        for k in expired_keys:
            PENDING_PAIRS.pop(k, None)

        if pin not in PENDING_PAIRS:
            raise ValueError("Invalid or expired pairing PIN")

        pair_data = PENDING_PAIRS.pop(pin)
        tenant_id = pair_data["tenant_id"]
        kiosk_name = pair_data["name"]

        # Double check limits at verification time to prevent race conditions
        limits = await self.kiosk_repo.get_tenant_limits(tenant_id)
        if not limits:
            raise ValueError("Tenant not found")
        max_kiosks = limits.get("max_kiosks", 1)
        active_count = await self.kiosk_repo.count_active_kiosks(tenant_id)
        if active_count >= max_kiosks:
            raise PermissionError("Kiosk limit reached for your subscription plan")

        # Register kiosk
        kiosk_id = str(uuid.uuid4())
        secret = secrets.token_urlsafe(32)
        await self.kiosk_repo.create_kiosk(kiosk_id, tenant_id, kiosk_name, secret, "active")

        # Generate session token (24 hours expiry)
        token = create_websocket_session_token(tenant_id, kiosk_id, expires_in_hours=24)
        expires_at = datetime.utcnow() + timedelta(hours=24)

        # Save session to DB
        await self.kiosk_repo.create_websocket_session(token, tenant_id, kiosk_id, expires_at)

        return {
            "token": token,
            "kiosk_id": kiosk_id,
            "name": kiosk_name,
            "secret": secret
        }
