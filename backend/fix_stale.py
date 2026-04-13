import asyncio
from app.db import AsyncSessionLocal
from app.models import ResourceLock, Run
from sqlalchemy import select, func

async def fix():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(ResourceLock).where(ResourceLock.released_at.is_(None)))
        locks = result.scalars().all()
        print(f"Stale locks: {len(locks)}")
        for lock in locks:
            print(f"  Lock id={lock.id} resource={lock.resource_id} run={lock.run_id}")
            lock.released_at = func.now()

        result2 = await db.execute(select(Run).where(Run.status.in_(["running", "queued"])))
        stuck = result2.scalars().all()
        print(f"Stuck runs: {len(stuck)}")
        for r in stuck:
            print(f"  Run id={r.id} status={r.status}")
            r.status = "failed"
        await db.commit()
        print("Fixed!")

asyncio.run(fix())
