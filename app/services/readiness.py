"""A bounded database probe using the existing request session."""

import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def check_database(session: AsyncSession) -> bool:
    try:
        async with asyncio.timeout(3):
            await session.execute(text("SELECT 1"))
    except Exception:
        # Connection exceptions can carry credentials; keep diagnostics private.
        logger.warning("Database readiness check failed")
        return False
    return True
