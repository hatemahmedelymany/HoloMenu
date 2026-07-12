"""
Stripe billing webhooks router.
"""
from datetime import datetime, timedelta
import hmac
import hashlib
import os
import time
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
import aiomysql

from backend.infrastructure.database.pool import get_db_conn
from backend.infrastructure.logging.json_logger import logger

router = APIRouter(prefix="/api/billing", tags=["billing"])


def verify_stripe_signature(payload: bytes, signature_header: Optional[str], secret: Optional[str]) -> bool:
    """
    Verify Stripe webhook signature using constant-time HMAC-SHA256 comparison and 5-minute replay window check.
    """
    if not signature_header or not secret:
        return False
    try:
        # Parse signature header
        pairs = [pair.split('=') for pair in signature_header.split(',')]
        params = {pair[0]: pair[1] for pair in pairs if len(pair) == 2}
        
        t = params.get('t')
        v1 = params.get('v1')
        if not t or not v1:
            return False
        
        # Check timestamp age (within 5 minutes / 300 seconds) to prevent replay attacks
        if abs(time.time() - int(t)) > 300:
            return False
            
        # Verify HMAC-SHA256
        signed_payload = f"{t}.".encode('utf-8') + payload
        computed_mac = hmac.new(
            secret.encode('utf-8'),
            signed_payload,
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(computed_mac, v1)
    except Exception as e:
        logger.error(f"Error validating Stripe signature: {e}")
        return False


PLAN_LIMITS = {
    "trial": 1,
    "starter": 1,
    "pro": 5,
    "enterprise": 20
}


@router.post("/webhook")
async def handle_stripe_webhook(
    request: Request,
    conn=Depends(get_db_conn)
):
    """
    Listen to Stripe webhook events, verify their signature, check idempotency,
    and process subscription transitions, grace periods, payment successes/failures, and offboarding triggers.
    """
    payload = await request.body()
    sig_header = request.headers.get("Stripe-Signature")
    
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "mock_stripe_webhook_secret")
    
    if not verify_stripe_signature(payload, sig_header, secret):
        logger.warning("Stripe signature verification failed")
        raise HTTPException(status_code=400, detail="Invalid Stripe signature")

    import json
    try:
        event = json.loads(payload)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Malformed JSON payload")

    event_id = event.get("id")
    event_type = event.get("type")
    
    if not event_id or not event_type:
        raise HTTPException(status_code=400, detail="Event ID or type missing")

    # 1. Idempotency Check: Verify if event has already been processed
    async with conn.cursor() as cur:
        await cur.execute("SELECT 1 FROM stripe_processed_events WHERE event_id = %s", (event_id,))
        if await cur.fetchone():
            return {"status": "already_processed", "event_id": event_id}

    # Process Handled Events
    event_obj = event.get("data", {}).get("object", {})
    metadata = event_obj.get("metadata", {})
    tenant_id = metadata.get("tenant_id")
    
    # Fallback to customer metadata or check Stripe customer billing lookup if not on subscription object
    if not tenant_id and event_type.startswith("invoice."):
        # For invoice events, metadata could be nested or we check customer_id
        # In a real setup, checkout session stores tenant_id in customer/subscription metadata
        pass

    if event_type in (
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
        "invoice.payment_failed",
        "invoice.payment_succeeded"
    ):
        if not tenant_id:
            # If no tenant context is bound to this Stripe event's metadata, log and ignore it gracefully
            logger.info(f"Ignored event {event_type} - missing tenant_id in metadata")
            return {"status": "ignored", "reason": "missing tenant_id"}

        # Fetch current tenant state to prevent overwriting active subscriptions with stale webhooks
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT plan, status, grace_period_ends_at FROM tenants WHERE id = %s", (tenant_id,))
            tenant = await cur.fetchone()
            if not tenant:
                logger.warning(f"Tenant {tenant_id} not found for event {event_type}")
                return {"status": "ignored", "reason": "tenant not found"}

        # Default parameters to update
        plan = metadata.get("plan", tenant["plan"]) # e.g. "starter", "pro", "enterprise"
        status_val = tenant["status"]
        grace_period_ends_at = tenant["grace_period_ends_at"]
        max_kiosks = PLAN_LIMITS.get(plan, 1)

        now = datetime.utcnow()

        if event_type == "customer.subscription.created":
            status_val = "active"
            grace_period_ends_at = None

        elif event_type == "customer.subscription.updated":
            sub_status = event_obj.get("status") # active, trialing, past_due, canceled, unpaid
            if sub_status in ("active", "trialing"):
                status_val = "active"
                grace_period_ends_at = None
            elif sub_status == "past_due":
                status_val = "active"
                # If grace period not already set, set it to 7 days from now
                if not grace_period_ends_at:
                    grace_period_ends_at = now + timedelta(days=7)
            elif sub_status in ("canceled", "unpaid"):
                status_val = "suspended"
                grace_period_ends_at = None

        elif event_type == "customer.subscription.deleted":
            status_val = "suspended"
            grace_period_ends_at = None

        elif event_type == "invoice.payment_failed":
            status_val = "active"
            if not grace_period_ends_at:
                grace_period_ends_at = now + timedelta(days=7)

        elif event_type == "invoice.payment_succeeded":
            status_val = "active"
            grace_period_ends_at = None

        # Apply update to Database
        async with conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE tenants 
                SET plan = %s, status = %s, max_kiosks = %s, grace_period_ends_at = %s 
                WHERE id = %s
                """,
                (plan, status_val, max_kiosks, grace_period_ends_at, tenant_id)
            )

        logger.info(f"Processed event {event_type} for tenant {tenant_id}: plan={plan}, status={status_val}")

    else:
        # Unhandled events: Stripe requires a 200 OK so it doesn't retry indefinitely
        logger.info(f"Unhandled Stripe event type ignored: {event_type}")

    # 2. Save event to processed table to maintain idempotency
    async with conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO stripe_processed_events (event_id) VALUES (%s)",
            (event_id,)
        )

    return {"status": "success" if event_type in (
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
        "invoice.payment_failed",
        "invoice.payment_succeeded"
    ) else "ignored", "event_id": event_id}
