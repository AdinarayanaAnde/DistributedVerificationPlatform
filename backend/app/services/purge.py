"""
Automatic data purge service.

Deletes runs (and associated logs, locks, queue entries, report files)
older than a configurable retention period.  Default: 7 days.
"""

import asyncio
import logging
import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import LogEntry, QueueEntry, ResourceLock, Run

logger = logging.getLogger(__name__)

RETENTION_DAYS = int(os.getenv("DATA_RETENTION_DAYS", "7"))
PURGE_INTERVAL_HOURS = int(os.getenv("PURGE_INTERVAL_HOURS", "24"))

REPORTS_DIR = Path(__file__).resolve().parents[2] / "reports"


async def purge_old_runs(session: AsyncSession, retention_days: int = RETENTION_DAYS) -> dict:
    """Delete runs older than *retention_days* and all related data.

    Returns a summary dict with counts of deleted rows and cleaned-up report dirs.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)

    # Find IDs of runs that are finished AND older than cutoff
    result = await session.execute(
        select(Run.id).where(
            Run.status.in_(["completed", "failed", "cancelled"]),
            Run.created_at < cutoff,
        )
    )
    run_ids = [row[0] for row in result.all()]

    if not run_ids:
        return {"purged_runs": 0, "purged_logs": 0, "purged_locks": 0,
                "purged_queue_entries": 0, "purged_report_dirs": 0}

    # Delete child rows first (FK order)
    del_logs = await session.execute(
        delete(LogEntry).where(LogEntry.run_id.in_(run_ids))
    )
    del_locks = await session.execute(
        delete(ResourceLock).where(ResourceLock.run_id.in_(run_ids))
    )
    del_queue = await session.execute(
        delete(QueueEntry).where(QueueEntry.run_id.in_(run_ids))
    )
    del_runs = await session.execute(
        delete(Run).where(Run.id.in_(run_ids))
    )

    await session.commit()

    # Clean up on-disk report directories
    purged_dirs = 0
    for run_id in run_ids:
        report_dir = REPORTS_DIR / str(run_id)
        if report_dir.is_dir():
            shutil.rmtree(report_dir, ignore_errors=True)
            purged_dirs += 1

    summary = {
        "purged_runs": del_runs.rowcount,
        "purged_logs": del_logs.rowcount,
        "purged_locks": del_locks.rowcount,
        "purged_queue_entries": del_queue.rowcount,
        "purged_report_dirs": purged_dirs,
    }
    logger.info("Data purge complete (retention=%d days): %s", retention_days, summary)
    return summary


async def periodic_purge(session_factory) -> None:
    """Background loop that runs purge_old_runs every PURGE_INTERVAL_HOURS."""
    while True:
        try:
            async with session_factory() as session:
                await purge_old_runs(session)
        except Exception:
            logger.exception("Periodic purge failed")
        await asyncio.sleep(PURGE_INTERVAL_HOURS * 3600)
