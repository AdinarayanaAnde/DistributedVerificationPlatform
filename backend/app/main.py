
# --- Robust logging setup: root logger ---
import logging
import os
from pathlib import Path

_log_level_name = os.getenv("LOG_LEVEL", "INFO").upper()
_log_level = getattr(logging, _log_level_name, logging.INFO)

log_path = Path(__file__).parent.parent / "backend.log"
logging.basicConfig(
    level=_log_level,
    format='[%(asctime)s] %(levelname)s %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_path, encoding="utf-8")
    ]
)

# Suppress noisy per-request access logs from uvicorn for high-frequency endpoints
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from sqlalchemy import select as sa_select, text

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


import traceback
from fastapi.responses import JSONResponse
from fastapi.exception_handlers import RequestValidationError
from fastapi.exceptions import RequestValidationError as FastAPIRequestValidationError

DEBUG = os.getenv("DEBUG", "false").lower() in ("1", "true", "yes", "on", "dev", "development")

app = FastAPI(
    title="Distributed Verification Platform",
    description="Backend service for web-based test automation and queue management.",
    version="0.1.0",
    lifespan=lifespan,
)

# ── Global exception handler for full tracebacks in development ──
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception: %s", exc, exc_info=True)
    if DEBUG:
        tb = traceback.format_exc()
        return JSONResponse(status_code=500, content={"detail": str(exc), "traceback": tb})
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})

# ── CORS – allow development origins and require explicit origins in production ──
cors_origins_env = os.getenv("CORS_ORIGINS", "").strip()
if cors_origins_env:
    allowed_origins = [origin.strip() for origin in cors_origins_env.split(",") if origin.strip()]
    allow_credentials = "*" not in allowed_origins
    if not allow_credentials:
        logger.warning(
            "CORS_ORIGINS contains '*' — credentials will NOT be sent. "
            "Set explicit origins for production."
        )
else:
    allowed_origins = ["*"]
    allow_credentials = False
    logger.warning(
        "CORS_ORIGINS is not set; allowing all origins for local development. "
        "Set explicit origins in production."
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestSizeLimitMiddleware)


@app.get("/api/health")
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

