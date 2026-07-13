from datetime import datetime, timedelta
import aiomysql
from backend.infrastructure.logging.json_logger import logger

class OffboardingUseCase:
    """
    Handles soft-delete offboarding cycles and permanent data purges for tenants.
    """
    def __init__(self, conn):
        self.conn = conn

    async def get_expired_tenants(self, grace_period_days: int = 30) -> list:
        """
        Fetch all tenants whose soft-delete grace period has expired.
        """
        cutoff_date = datetime.utcnow() - timedelta(days=grace_period_days)
        async with self.conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT id, subdomain FROM tenants WHERE deleted_at IS NOT NULL AND deleted_at < %s",
                (cutoff_date,)
            )
            return await cur.fetchall()

    async def purge_tenant(self, tenant_id: str) -> None:
        """
        Permanently delete operational data for a tenant while preserving minimal anonymized financial history.
        """
        logger.info(f"Initiating permanent data purge for tenant: {tenant_id}")
        
        await self.conn.begin()
        try:
            async with self.conn.cursor() as cur:
                # 1. Delete WS sessions
                await cur.execute("DELETE FROM websocket_sessions WHERE tenant_id = %s", (tenant_id,))
                
                # 2. Delete kiosks
                await cur.execute("DELETE FROM kiosks WHERE tenant_id = %s", (tenant_id,))
                
                # 3. Delete analytics events
                await cur.execute("DELETE FROM analytics_events WHERE tenant_id = %s", (tenant_id,))
                
                # 4. Delete order items (breaks dependency on products)
                await cur.execute("DELETE FROM order_items WHERE tenant_id = %s", (tenant_id,))
                
                # 5. Delete products
                await cur.execute("DELETE FROM products WHERE tenant_id = %s", (tenant_id,))
                
                # 6. Delete departments
                await cur.execute("DELETE FROM departments WHERE tenant_id = %s", (tenant_id,))
                
                # 7. Delete admins (staff seats)
                await cur.execute("DELETE FROM admins WHERE tenant_id = %s", (tenant_id,))
                
                # 8. Delete audit logs
                await cur.execute("DELETE FROM audit_logs WHERE tenant_id = %s", (tenant_id,))
                
                # 9. Anonymize/Scrub the tenant row to preserve integrity of compliance history (orders/payments)
                # Replaces details and moves subdomain to 'deleted-{id_prefix}' to free it up for future registrants.
                # Note: legal_business_name is explicitly untouched and preserved, and deleted_at is kept NOT NULL.
                scrubbed_subdomain = f"deleted-{tenant_id[:8]}"
                await cur.execute(
                    """
                    UPDATE tenants 
                    SET name = 'Deleted Tenant', 
                        subdomain = %s, 
                        status = 'cancelled' 
                    WHERE id = %s
                    """,
                    (scrubbed_subdomain, tenant_id)
                )
            await self.conn.commit()
            logger.info(f"Successfully purged tenant {tenant_id}. Subdomain freed.")
        except Exception as e:
            await self.conn.rollback()
            logger.error(f"Failed to purge tenant {tenant_id}, transaction rolled back: {str(e)}")
            raise e

    async def purge_expired_tenants(self, grace_period_days: int = 30) -> int:
        """
        Find and purge all tenants whose soft-delete grace period has expired.
        """
        tenants = await self.get_expired_tenants(grace_period_days)
        count = 0
        for tenant in tenants:
            await self.purge_tenant(tenant["id"])
            count += 1
        return count
