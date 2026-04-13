from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import QueueEntry, Resource, ResourceLock, Run


class ResourceQueueManager:
    @staticmethod
    async def find_or_create_resource(db: AsyncSession, name: str) -> Resource:
        statement = select(Resource).where(Resource.name == name)
        result = await db.execute(statement)
        resource = result.scalars().first()
        if resource:
            return resource

        resource = Resource(name=name, description=f"Managed resource {name}")
        db.add(resource)
        await db.commit()
        await db.refresh(resource)
        return resource

    @staticmethod
    async def acquire_lock(db: AsyncSession, run: Run, resource: Resource) -> bool:
        statement = select(ResourceLock).where(
            ResourceLock.resource_id == resource.id,
            ResourceLock.released_at.is_(None),
        )
        result = await db.execute(statement)
        existing = result.scalars().first()
        if existing:
            # Auto-release stale locks held by completed/failed/pending runs
            holder = await db.get(Run, existing.run_id)
            if holder and holder.status in ("completed", "failed", "pending", "cancelled"):
                existing.released_at = func.now()
                await db.commit()
                # Re-check that no other request grabbed a lock in the meantime
                re_result = await db.execute(statement)
                if re_result.scalars().first() is not None:
                    return False
            else:
                return False

        lock = ResourceLock(resource_id=resource.id, run_id=run.id)
        db.add(lock)
        run.resource_id = resource.id
        run.status = "running"
        await db.commit()
        await db.refresh(run)
        return True

    @staticmethod
    async def enqueue_run(db: AsyncSession, run: Run, resource: Resource) -> QueueEntry:
        statement = select(func.max(QueueEntry.position)).where(QueueEntry.resource_id == resource.id)
        result = await db.execute(statement)
        max_position = result.scalar_one_or_none() or 0
        queue_item = QueueEntry(
            resource_id=resource.id,
            run_id=run.id,
            client_id=run.client_id,
            position=max_position + 1,
        )
        db.add(queue_item)
        run.status = "queued"
        await db.commit()
        await db.refresh(queue_item)
        return queue_item

    @staticmethod
    async def release_resource(db: AsyncSession, resource: Resource, run_id: int | None = None) -> int | None:
        """Release a resource lock and start the next queued run.

        If run_id is given, only release the lock held by that specific run
        (prevents accidentally releasing a different run's lock on double-call).
        """
        lock_filter = [
            ResourceLock.resource_id == resource.id,
            ResourceLock.released_at.is_(None),
        ]
        if run_id is not None:
            lock_filter.append(ResourceLock.run_id == run_id)
        statement = select(ResourceLock).where(*lock_filter)
        result = await db.execute(statement)
        current_lock = result.scalars().first()
        if current_lock:
            current_lock.released_at = func.now()
            await db.commit()

        next_statement = select(QueueEntry).where(
            QueueEntry.resource_id == resource.id,
            QueueEntry.status == "waiting",
        ).order_by(QueueEntry.position)
        next_result = await db.execute(next_statement)
        next_item = next_result.scalars().first()
        if next_item:
            next_item.status = "running"
            await db.commit()
            run_statement = select(Run).where(Run.id == next_item.run_id)
            run_result = await db.execute(run_statement)
            next_run = run_result.scalars().first()
            if next_run:
                next_run.status = "running"
                next_run.resource_id = resource.id
                lock = ResourceLock(resource_id=resource.id, run_id=next_run.id)
                db.add(lock)
                await db.commit()
                return next_run.id
        return None
