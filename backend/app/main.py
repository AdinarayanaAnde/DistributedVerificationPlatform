import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from sqlalchemy import select as sa_select, text
import os

from app.api.routes import router as api_router
from app.db import init_db
from app.services.notifications import NotificationService
from app.services.purge import periodic_purge

logger = logging.getLogger(__name__)

# ── Request body size limit middleware ──
MAX_REQUEST_BODY_BYTES = int(os.getenv("MAX_REQUEST_BODY_BYTES", str(10 * 1024 * 1024)))  # 10 MB


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_REQUEST_BODY_BYTES:
            return Response("Request body too large", status_code=413)
        return await call_next(request)


_smtp_username = os.getenv("SMTP_USERNAME", "")
_smtp_password = os.getenv("SMTP_PASSWORD", "")
if not _smtp_username or not _smtp_password:
    logger.warning("SMTP_USERNAME / SMTP_PASSWORD not set — email notifications disabled.")

notification_service = NotificationService(
    smtp_server=os.getenv("SMTP_SERVER", "smtp.gmail.com"),
    smtp_port=int(os.getenv("SMTP_PORT", "587")),
    smtp_username=_smtp_username,
    smtp_password=_smtp_password,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    app.state.notification_service = notification_service
    # Clean up stale locks and stuck runs from previous server restarts
    from app.db import AsyncSessionLocal
    from app.models import ResourceLock, Run, QueueEntry
    from sqlalchemy import select, delete
    from sqlalchemy import func as sqlfunc
    async with AsyncSessionLocal() as session:
        # Release all unreleased locks
        result = await session.execute(
            select(ResourceLock).where(ResourceLock.released_at.is_(None))
        )
        for lock in result.scalars().all():
            lock.released_at = sqlfunc.now()
        # Mark stuck running/queued/pending runs as failed
        result2 = await session.execute(
            select(Run).where(Run.status.in_(["running", "queued", "pending"]))
        )
        for r in result2.scalars().all():
            r.status = "failed"
            r.note = (r.note or "") + " [auto-failed: server restart]"
        # Purge stale queue entries
        await session.execute(
            delete(QueueEntry).where(
                QueueEntry.run_id.in_(
                    select(Run.id).where(Run.status.in_(["failed", "completed"]))
                )
            )
        )
        await session.commit()
    # Start periodic data purge background task
    import asyncio
    purge_task = asyncio.create_task(periodic_purge(AsyncSessionLocal))
    yield
    # Shutdown
    purge_task.cancel()


app = FastAPI(
    title="Distributed Verification Platform",
    description="Backend service for web-based test automation and queue management.",
    version="0.1.0",
    lifespan=lifespan,
)

# ── CORS – refuse wildcard with credentials ──
allowed_origins = os.getenv("CORS_ORIGINS", "https://localhost:5173,http://localhost:5173").split(",")
allow_credentials = "*" not in allowed_origins
if not allow_credentials:
    logger.warning(
        "CORS_ORIGINS contains '*' — credentials will NOT be sent. "
        "Set explicit origins for production."
    )
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestSizeLimitMiddleware)


@app.get("/health")
async def health_check() -> dict:
    from app.db import engine
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        logger.error("Health check DB probe failed: %s", exc)
        raise HTTPException(status_code=503, detail="database unavailable")
    return {"status": "ok"}


app.include_router(api_router, prefix="/api")

