"""
Error tracking integration via Sentry.
"""
import os
from backend.infrastructure.logging.json_logger import logger


def init_sentry():
    sentry_dsn = os.getenv("SENTRY_DSN")
    if sentry_dsn:
        try:
            import sentry_sdk
            from sentry_sdk.integrations.fastapi import FastApiIntegration
            sentry_sdk.init(
                dsn=sentry_dsn,
                integrations=[FastApiIntegration()],
                traces_sample_rate=0.1,
            )
            logger.info("Sentry initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Sentry: {e}")
    else:
        logger.info("SENTRY_DSN not configured; Sentry tracking is disabled")
