"""
Production CLI script to purge expired soft-deleted tenants (older than 30 days).
Run daily via crontab / systemd timer:
PYTHONPATH=. .venv/Scripts/python backend/scripts/purge_tenants.py
"""
import asyncio
import aiomysql
import sys

from backend.infrastructure.config.settings import DB_CONFIG
from backend.application.use_cases.offboarding import OffboardingUseCase
from backend.infrastructure.logging.json_logger import logger

async def run_purge():
    logger.info("Starting cron job: Purging expired soft-deleted tenants...")
    try:
        conn = await aiomysql.connect(**DB_CONFIG)
        use_case = OffboardingUseCase(conn)
        purged_count = await use_case.purge_expired_tenants(grace_period_days=30)
        logger.info(f"Cron job complete. Total tenants purged: {purged_count}")
        conn.close()
    except Exception as e:
        logger.error(f"Error executing purge cron job: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(run_purge())
