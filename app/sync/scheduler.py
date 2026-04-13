"""APScheduler-based background scheduler for automatic sync runs."""

import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings
from app.sync.manager import start_sync, progress, SyncState

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None
JOB_ID = "auto_sync"


async def _scheduled_sync():
    if progress.state != SyncState.IDLE:
        logger.info("Skipping scheduled sync – current state: %s", progress.state)
        return
    logger.info("Scheduled sync triggered")
    await start_sync()


def start_scheduler():
    global _scheduler
    _scheduler = AsyncIOScheduler(timezone="UTC")
    _scheduler.add_job(
        _scheduled_sync,
        trigger=IntervalTrigger(minutes=settings.SYNC_INTERVAL_MINUTES),
        id=JOB_ID,
        replace_existing=True,
        max_instances=1,
    )
    _scheduler.start()
    logger.info("Scheduler started – interval %d min", settings.SYNC_INTERVAL_MINUTES)


def stop_scheduler():
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")


def update_interval(minutes: int):
    """Update the sync interval at runtime without restarting."""
    if _scheduler and _scheduler.running:
        _scheduler.reschedule_job(
            JOB_ID,
            trigger=IntervalTrigger(minutes=minutes),
        )
        logger.info("Sync interval updated to %d min", minutes)
