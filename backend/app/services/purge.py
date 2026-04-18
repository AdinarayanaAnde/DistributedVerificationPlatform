"""
Automatic data purge service.

Deletes runs (and associated logs, locks, queue entries, report files)
older than a configurable retention period.  Default: 7 days.
Also enforces a maximum report count (default: 50) to prevent disk bloat.
"""

import asyncio
import logging
import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import delete, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Client, LogEntry, QueueEntry, ResourceLock, Run, ReportData, RunSuiteLink

logger = logging.getLogger(__name__)

RETENTION_DAYS = int(os.getenv("DATA_RETENTION_DAYS", "7"))
PURGE_INTERVAL_HOURS = int(os.getenv("PURGE_INTERVAL_HOURS", "24"))
MAX_REPORT_COUNT = int(os.getenv("MAX_REPORT_COUNT", "50"))

REPORTS_DIR = Path(__file__).resolve().parents[3] / "reports"


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
    await session.execute(
        delete(ReportData).where(ReportData.run_id.in_(run_ids))
    )
    await session.execute(
        delete(RunSuiteLink).where(RunSuiteLink.run_id.in_(run_ids))
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


async def prune_excess_reports(session: AsyncSession, max_count: int = MAX_REPORT_COUNT) -> dict:
    """Delete the oldest completed/failed/cancelled runs PER CLIENT when their count exceeds max_count.

    Keeps the most recent `max_count` finished runs per client and removes the rest.
    Running/pending/queued runs are never pruned.
    """
    # Get all clients that have finished runs
    client_ids_result = await session.execute(
        select(Run.client_id).where(
            Run.status.in_(["completed", "failed", "cancelled"])
        ).group_by(Run.client_id)
    )
    client_ids = [row[0] for row in client_ids_result.all()]

    total_pruned_runs = 0
    total_pruned_dirs = 0

    for cid in client_ids:
        # Count finished runs for this client
        total_finished = (await session.execute(
            select(func.count(Run.id)).where(
                Run.client_id == cid,
                Run.status.in_(["completed", "failed", "cancelled"])
            )
        )).scalar_one()

        if total_finished <= max_count:
            continue

        # Find IDs of runs to prune (oldest finished runs beyond the limit)
        excess = total_finished - max_count
        result = await session.execute(
            select(Run.id).where(
                Run.client_id == cid,
                Run.status.in_(["completed", "failed", "cancelled"])
            ).order_by(Run.created_at.asc()).limit(excess)
        )
        run_ids = [row[0] for row in result.all()]

        if not run_ids:
            continue

        # Delete child rows first (FK order)
        await session.execute(delete(LogEntry).where(LogEntry.run_id.in_(run_ids)))
        await session.execute(delete(ResourceLock).where(ResourceLock.run_id.in_(run_ids)))
        await session.execute(delete(QueueEntry).where(QueueEntry.run_id.in_(run_ids)))
        await session.execute(delete(ReportData).where(ReportData.run_id.in_(run_ids)))
        await session.execute(delete(RunSuiteLink).where(RunSuiteLink.run_id.in_(run_ids)))
        del_runs = await session.execute(delete(Run).where(Run.id.in_(run_ids)))

        total_pruned_runs += del_runs.rowcount

        # Clean up on-disk report directories
        for run_id in run_ids:
            report_dir = REPORTS_DIR / str(run_id)
            if report_dir.is_dir():
                shutil.rmtree(report_dir, ignore_errors=True)
                total_pruned_dirs += 1

    if total_pruned_runs:
        await session.commit()

    summary = {
        "pruned_runs": total_pruned_runs,
        "pruned_report_dirs": total_pruned_dirs,
    }
    if total_pruned_runs:
        logger.info("Per-client report pruning complete (max=%d per client): %s", max_count, summary)
    return summary


async def cleanup_orphaned_report_dirs(session: AsyncSession) -> dict:
    """Remove report directories on disk that have no matching run in the database."""
    if not REPORTS_DIR.is_dir():
        return {"orphaned_dirs_removed": 0}

    # Get all run IDs that exist in the DB
    result = await session.execute(select(Run.id))
    valid_ids = {row[0] for row in result.all()}

    removed = 0
    for entry in REPORTS_DIR.iterdir():
        if not entry.is_dir():
            continue
        try:
            run_id = int(entry.name)
        except ValueError:
            continue
        if run_id not in valid_ids:
            shutil.rmtree(entry, ignore_errors=True)
            removed += 1

    if removed:
        logger.info("Cleaned up %d orphaned report directories", removed)
    return {"orphaned_dirs_removed": removed}


async def periodic_purge(session_factory) -> None:
    """Background loop that runs purge on startup immediately, then every PURGE_INTERVAL_HOURS."""
    # Run immediately on startup, then on schedule
    first_run = True
    while True:
        try:
            async with session_factory() as session:
                await purge_old_runs(session)
                await prune_excess_reports(session)
                if first_run:
                    await cleanup_orphaned_report_dirs(session)
                    first_run = False
        except Exception:
            logger.exception("Periodic purge failed")
        await asyncio.sleep(PURGE_INTERVAL_HOURS * 3600)
