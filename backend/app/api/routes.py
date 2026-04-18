import asyncio
import collections
import json
import logging
import secrets
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status, WebSocket, Request, UploadFile, File, Query
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import authenticate_client, create_access_token, get_current_client, get_password_hash
from app.db import AsyncSessionLocal, get_db
from app.models import Client, LogEntry, QueueEntry, Resource, ResourceLock, Run, ReportData, CustomSuite, RunSuiteLink, SetupConfiguration, SetupStep, TeardownConfiguration, TeardownStep
from app.schemas import (
    ClientCreate,
    ClientOut,
    CustomSuiteCreate,
    CustomSuiteOut,
    CustomSuiteUpdate,
    LogEntryOut,
    QueueEntryOut,
    ResourceOut,
    ResourceCreate,
    RunCreate,
    RunOut,
    SetupConfigCreate,
    SetupConfigOut,
    SetupConfigUpdate,
    SetupStepCreate,
    TeardownConfigCreate,
    TeardownConfigOut,
    TeardownConfigUpdate,
    TeardownStepCreate,
    TestItem,
    TestSuite,
)
from app.services.notifications import NotificationService
from app.services.queue import ResourceQueueManager
from app.services.runner import TEST_ROOT, REPORTS_DIR, capture_test_run, cancel_run, cancel_run_file, get_active_files, execute_setup_steps, execute_teardown_steps

logger = logging.getLogger(__name__)

router = APIRouter()
security = HTTPBearer()


async def generate_run_name(db: AsyncSession, client_id: int) -> str:
    """Generate a human-readable run name: RUN-YYYYMMDD-NNN (per-client daily sequence)."""
    today = datetime.now(timezone.utc)
    prefix = f"RUN-{today.strftime('%Y%m%d')}-"
    result = await db.execute(
        select(func.count(Run.id)).where(
            Run.client_id == client_id,
            Run.run_name.like(f"{prefix}%"),
        )
    )
    seq = (result.scalar_one() or 0) + 1
    return f"{prefix}{seq:03d}"

# ── Admin API key (simple shared secret for admin endpoints) ──
import os
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")


async def _verify_run_owner(run_id: int, client_key: str | None, db: AsyncSession) -> Run:
    """Fetch a run and verify the requesting client owns it. Returns the Run or raises 404/403."""
    client = await _resolve_client(client_key, db)
    run = await db.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.client_id != client.id:
        raise HTTPException(status_code=403, detail="Access denied: run belongs to another client")
    return run


async def _resolve_client(client_key: str | None, db: AsyncSession) -> Client:
    """Resolve a client_key to a Client object. Raises 401 if missing or invalid."""
    if not client_key:
        raise HTTPException(status_code=401, detail="client_key is required")
    client = (await db.execute(select(Client).where(Client.client_key == client_key))).scalars().first()
    if not client:
        raise HTTPException(status_code=401, detail="Invalid client_key")
    return client


async def verify_admin(request: Request):
    """Dependency that checks for a valid admin API key."""
    if not ADMIN_API_KEY:
        # No key configured — allow (dev mode)
        return
    auth = request.headers.get("x-admin-key", "")
    if not secrets.compare_digest(auth, ADMIN_API_KEY):
        raise HTTPException(status_code=403, detail="Invalid or missing admin key")


# ── Simple in-memory rate limiter for login ──
_login_attempts: dict[str, list[float]] = collections.defaultdict(list)
LOGIN_RATE_LIMIT = 5        # max attempts
LOGIN_RATE_WINDOW = 60      # per N seconds

# Simple TTL cache for test discovery (avoids re-scanning disk on every request)
_test_cache: dict = {"nodeids": [], "timestamp": 0}
_TEST_CACHE_TTL = 10  # seconds


@router.post("/admin/cleanup")
async def cleanup_stale(db: AsyncSession = Depends(get_db), _admin=Depends(verify_admin)):
    """Release stale resource locks, mark stuck runs as failed, purge old data."""
    # Release unreleased locks
    result = await db.execute(select(ResourceLock).where(ResourceLock.released_at.is_(None)))
    locks = result.scalars().all()
    for lock in locks:
        lock.released_at = func.now()

    # Mark stuck runs as failed
    result2 = await db.execute(select(Run).where(Run.status.in_(["running", "queued", "pending"])))
    stuck = result2.scalars().all()
    for r in stuck:
        r.status = "failed"

    # Delete all released locks (they're historical cruft that blocks unique constraints)
    from sqlalchemy import delete
    del_locks = await db.execute(delete(ResourceLock).where(ResourceLock.released_at.is_not(None)))

    # Delete stale queue entries for failed/completed runs
    del_queue = await db.execute(
        delete(QueueEntry).where(
            QueueEntry.run_id.in_(
                select(Run.id).where(Run.status.in_(["failed", "completed"]))
            )
        )
    )

    await db.commit()
    return {
        "released_locks": len(locks),
        "failed_runs": len(stuck),
        "deleted_locks": del_locks.rowcount,
        "deleted_queue_entries": del_queue.rowcount,
    }


@router.post("/admin/purge")
async def purge_old_data(retention_days: int = 7, max_reports: int = 50, db: AsyncSession = Depends(get_db), _admin=Depends(verify_admin)):
    """Delete completed/failed runs older than retention_days and prune excess reports beyond max_reports."""
    if retention_days < 1:
        raise HTTPException(status_code=400, detail="retention_days must be >= 1")
    if max_reports < 1:
        raise HTTPException(status_code=400, detail="max_reports must be >= 1")
    from app.services.purge import purge_old_runs, prune_excess_reports
    time_result = await purge_old_runs(db, retention_days=retention_days)
    count_result = await prune_excess_reports(db, max_count=max_reports)
    return {**time_result, **count_result}


@router.post("/auth/login")
async def login(client_key: str, password: str):
    # Rate limiting: block if too many attempts for this client_key
    now = time.time()
    attempts = _login_attempts[client_key]
    # Trim old entries outside the window
    _login_attempts[client_key] = [t for t in attempts if now - t < LOGIN_RATE_WINDOW]
    if len(_login_attempts[client_key]) >= LOGIN_RATE_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Try again later.",
        )
    _login_attempts[client_key].append(now)

    client = await authenticate_client(client_key, password)
    if not client:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect client_key or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Clear attempts on success
    _login_attempts.pop(client_key, None)
    access_token = create_access_token(data={"sub": client.client_key})
    return {"access_token": access_token, "token_type": "bearer"}


def make_secret_key() -> str:
    return secrets.token_hex(24)


async def schedule_run_task(run_id: int, notification_service: NotificationService | None = None) -> None:
    async with AsyncSessionLocal() as session:
        run = await session.get(Run, run_id)
        if run is None:
            return

        try:
            # Execute setup steps if a setup configuration is attached
            if run.setup_config_id:
                setup_ok = await execute_setup_steps(run.id, run.setup_config_id, session)
                if not setup_ok:
                    run = await session.get(Run, run_id)
                    if run and run.status not in ("completed", "failed", "cancelled"):
                        run.status = "failed"
                        run.finished_at = datetime.now(timezone.utc)
                        await session.commit()
                    return
            else:
                # No setup config — mark as skipped
                run = await session.get(Run, run_id)
                if run:
                    run.setup_status = "skipped"
                    await session.commit()

            await capture_test_run(run.id, run.selected_tests, session, notification_service)

            # Execute teardown steps after tests complete (regardless of test outcome)
            run = await session.get(Run, run_id)
            if run and run.teardown_config_id:
                await execute_teardown_steps(run.id, run.teardown_config_id, session)
            elif run:
                run.teardown_status = "skipped"
                await session.commit()
        except Exception as e:
            # Mark run as failed if runner crashes
            run = await session.get(Run, run_id)
            if run and run.status not in ("completed", "failed", "cancelled"):
                run.status = "failed"
                await session.commit()
            logger.error("Run %d failed unexpectedly", run_id, exc_info=True)
        finally:
            run = await session.get(Run, run_id)
            if run and run.resource_id:
                resource = await session.get(Resource, run.resource_id)
                if resource:
                    next_run_id = await ResourceQueueManager.release_resource(session, resource, run_id=run_id)
                    if next_run_id:
                        asyncio.create_task(schedule_run_task(next_run_id, notification_service))

            # Prune excess reports to stay within count limit
            try:
                from app.services.purge import prune_excess_reports
                await prune_excess_reports(session)
            except Exception:
                pass  # Don't let pruning failure affect the run


@router.get("/clients", response_model=List[ClientOut])
async def list_clients(db: AsyncSession = Depends(get_db)) -> List[ClientOut]:
    result = await db.execute(select(Client).order_by(Client.created_at.desc()))
    return result.scalars().all()


@router.post("/clients/register", response_model=ClientOut)
async def register_client(payload: ClientCreate, db: AsyncSession = Depends(get_db)) -> ClientOut:
    existing = (await db.execute(
        select(Client).where(func.lower(Client.name) == payload.name.strip().lower())
    )).scalars().first()
    if existing:
        response = ClientOut.model_validate(existing)
        response.client_key = existing.client_key
        return response

    raw_secret = make_secret_key()
    client = Client(
        name=payload.name.strip(),
        client_key=make_secret_key(),
        secret=get_password_hash(raw_secret),
        email=payload.email,
        webhook_url=payload.webhook_url
    )
    db.add(client)
    await db.commit()
    await db.refresh(client)
    response = ClientOut.model_validate(client)
    response.client_key = client.client_key
    logger.debug("New client registered: %s", client.name)
    return response


@router.get("/tests/discover", response_model=List[TestItem])
async def discover_tests(client_key: str | None = None, db: AsyncSession = Depends(get_db)) -> List[TestItem]:
    tests: List[TestItem] = []
    backend_dir = Path(__file__).resolve().parents[2]

    # 1. Discover server-side tests (always available)
    for path in Path(TEST_ROOT).glob("**/test_*.py"):
        text = path.read_text(encoding="utf-8")
        rel_path = path.relative_to(backend_dir)
        posix_path = rel_path.as_posix()
        for nodeid in _discover_nodeids_from_file(text, posix_path):
            func_name = nodeid.rsplit("::", 1)[-1]
            tests.append(
                TestItem(
                    nodeid=nodeid,
                    path=str(rel_path),
                    function=func_name,
                )
            )

    # 2. Discover uploaded tests (client-scoped, only if client_key provided)
    if client_key:
        uploads_dir = backend_dir / "data" / "uploads" / client_key
        if uploads_dir.exists():
            for upload_folder in uploads_dir.iterdir():
                if not upload_folder.is_dir():
                    continue
                for path in upload_folder.rglob("test_*.py"):
                    try:
                        text = path.read_text(encoding="utf-8")
                        rel_path = path.relative_to(backend_dir)
                        posix_path = rel_path.as_posix()
                        for nodeid in _discover_nodeids_from_file(text, posix_path):
                            func_name = nodeid.rsplit("::", 1)[-1]
                            tests.append(
                                TestItem(
                                    nodeid=nodeid,
                                    path=str(rel_path),
                                    function=func_name,
                                )
                            )
                    except Exception:
                        continue  # skip unreadable files

    return tests


@router.post("/resources", response_model=ResourceOut)
async def create_resource(payload: ResourceCreate, db: AsyncSession = Depends(get_db)) -> ResourceOut:
    # Enforce uniqueness of resource name
    existing = await db.execute(select(Resource).where(Resource.name == payload.name))
    if existing.scalars().first():
        raise HTTPException(status_code=409, detail=f"Resource with name '{payload.name}' already exists.")
    try:
        resource = Resource(name=payload.name, description=payload.description)
        db.add(resource)
        await db.commit()
        await db.refresh(resource)
        return resource
    except Exception as e:
        logger.error("Error creating resource: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/resources", response_model=List[ResourceOut])
async def list_resources(db: AsyncSession = Depends(get_db)) -> List[ResourceOut]:
    result = await db.execute(select(Resource))
    return result.scalars().all()


@router.post("/runs", response_model=RunOut, status_code=status.HTTP_201_CREATED)
async def create_run(payload: RunCreate, db: AsyncSession = Depends(get_db), request: Request = None) -> RunOut:
    notification_service = getattr(request.app.state, 'notification_service', None) if request else None

    try:
        statement = select(Client).where(Client.client_key == payload.client_key)
        result = await db.execute(statement)
        client = result.scalars().first()
        if not client:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

        # Filter out stale tests whose files no longer exist on disk
        selected_tests = payload.selected_tests or []
        if selected_tests:
            backend_dir = Path(__file__).resolve().parents[2]
            selected_tests = [
                nid for nid in selected_tests
                if (backend_dir / (nid.split("::")[0] if "::" in nid else nid)).exists()
            ]

        run = Run(client_id=client.id, selected_tests=selected_tests, status="pending",
                  setup_config_id=payload.setup_config_id,
                  teardown_config_id=payload.teardown_config_id,
                  run_name=await generate_run_name(db, client.id))
        db.add(run)
        await db.commit()
        await db.refresh(run)

        # Track which suites were used for this run (for history and analytics)
        if payload.suite_ids:
            for sid in payload.suite_ids:
                db.add(RunSuiteLink(run_id=run.id, suite_id=sid))
            await db.commit()

        if payload.resource_name:
            resource = await ResourceQueueManager.find_or_create_resource(db, payload.resource_name)
            acquired = await ResourceQueueManager.acquire_lock(db, run, resource)
            if not acquired:
                await ResourceQueueManager.enqueue_run(db, run, resource)
            else:
                asyncio.create_task(schedule_run_task(run.id, notification_service))
        else:
            run.status = "running"
            db.add(run)
            await db.commit()
            asyncio.create_task(schedule_run_task(run.id, notification_service))

        await db.refresh(run)
        logger.info("Run created: id=%d name=%s client=%s", run.id, run.run_name, client.name)
        return run
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error creating run: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/runs", response_model=List[RunOut])
async def list_runs(client_key: str, db: AsyncSession = Depends(get_db)) -> List[RunOut]:
    client = await _resolve_client(client_key, db)
    query = select(Run).where(Run.client_id == client.id).order_by(Run.created_at.desc())
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/runs/{run_id}", response_model=RunOut)
async def get_run(run_id: int, client_key: str, db: AsyncSession = Depends(get_db)) -> RunOut:
    return await _verify_run_owner(run_id, client_key, db)


@router.post("/runs/{run_id}/cancel")
async def cancel_run_endpoint(run_id: int, client_key: str, db: AsyncSession = Depends(get_db), request: Request = None):
    """Cancel / kill a running or queued job."""
    run = await _verify_run_owner(run_id, client_key, db)

    if run.status not in ("running", "queued", "pending"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Run is already {run.status}",
        )

    killed = cancel_run(run_id)

    # Always clean up queue entries for this run (safe no-op if none exist)
    from sqlalchemy import delete as sa_delete
    await db.execute(
        sa_delete(QueueEntry).where(QueueEntry.run_id == run_id)
    )

    run.status = "cancelled"
    run.finished_at = datetime.now(timezone.utc)
    await db.commit()

    # Release the resource lock immediately so next queued run can proceed
    if run.resource_id:
        resource = await db.get(Resource, run.resource_id)
        if resource:
            notification_service = getattr(request.app.state, 'notification_service', None) if request else None
            next_run_id = await ResourceQueueManager.release_resource(db, resource, run_id=run_id)
            if next_run_id:
                asyncio.create_task(schedule_run_task(next_run_id, notification_service))

    await db.refresh(run)

    return {
        "id": run.id,
        "status": run.status,
        "processes_killed": killed,
    }


@router.post("/runs/{run_id}/cancel/{file_path:path}")
async def cancel_run_file_endpoint(run_id: int, file_path: str, client_key: str, db: AsyncSession = Depends(get_db)):
    """Cancel a specific test file within a running job."""
    run = await _verify_run_owner(run_id, client_key, db)
    if run.status != "running":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Run is {run.status}, not running",
        )

    result = cancel_run_file(run_id, file_path)
    if result == "not_found":
        # Maybe the tag uses a different format — try matching by suffix
        active = get_active_files(run_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No process for '{file_path}'. Active files: {active}",
        )
    if result == "already_finished":
        return {"run_id": run_id, "file": file_path, "cancelled": False, "detail": "already finished"}

    return {"run_id": run_id, "file": file_path, "cancelled": True}


@router.get("/runs/{run_id}/active-files")
async def get_run_active_files(run_id: int, client_key: str, db: AsyncSession = Depends(get_db)):
    """Return list of test file tags still running for a given run."""
    await _verify_run_owner(run_id, client_key, db)
    return {"run_id": run_id, "active_files": get_active_files(run_id)}


@router.get("/resources/{resource_name}/queue", response_model=List[QueueEntryOut])
async def get_resource_queue(resource_name: str, db: AsyncSession = Depends(get_db)) -> List[QueueEntryOut]:
    statement = select(Resource).where(Resource.name == resource_name)
    resource_result = await db.execute(statement)
    resource = resource_result.scalars().first()
    if not resource:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
    queue_result = await db.execute(select(QueueEntry).where(QueueEntry.resource_id == resource.id).order_by(QueueEntry.position))
    return queue_result.scalars().all()


@router.get("/runs/{run_id}/logs", response_model=List[LogEntryOut])
async def get_run_logs(run_id: int, client_key: str, db: AsyncSession = Depends(get_db)) -> List[LogEntryOut]:
    await _verify_run_owner(run_id, client_key, db)
    result = await db.execute(select(LogEntry).where(LogEntry.run_id == run_id).order_by(LogEntry.timestamp))
    logs = result.scalars().all()
    return logs


@router.websocket("/runs/{run_id}/logs/ws")
async def websocket_logs(run_id: int, websocket: WebSocket):
    # Verify ownership via query param before accepting
    client_key = websocket.query_params.get("client_key")
    if not client_key:
        await websocket.close(code=4001)
        return
    async with AsyncSessionLocal() as session:
        try:
            await _verify_run_owner(run_id, client_key, session)
        except HTTPException:
            await websocket.close(code=4003)
            return
    await websocket.accept()
    last_id = 0
    ping_counter = 0
    try:
        while True:
            async with AsyncSessionLocal() as session:
                # Only fetch logs newer than the last one sent
                result = await session.execute(
                    select(LogEntry)
                    .where(LogEntry.run_id == run_id, LogEntry.id > last_id)
                    .order_by(LogEntry.id)
                )
                new_logs = result.scalars().all()
                if new_logs:
                    last_id = new_logs[-1].id
                    log_data = [
                        {
                            "timestamp": log.timestamp.isoformat(),
                            "level": log.level,
                            "source": log.source,
                            "message": log.message,
                        }
                        for log in new_logs
                    ]
                    await websocket.send_json(log_data)

                # Check if run is finished to stop polling
                run = await session.get(Run, run_id)
                if run and run.status in ("completed", "failed", "cancelled"):
                    # Send one final batch then close
                    await asyncio.sleep(0.5)
                    result = await session.execute(
                        select(LogEntry)
                        .where(LogEntry.run_id == run_id, LogEntry.id > last_id)
                        .order_by(LogEntry.id)
                    )
                    final_logs = result.scalars().all()
                    if final_logs:
                        await websocket.send_json([
                            {
                                "timestamp": log.timestamp.isoformat(),
                                "level": log.level,
                                "source": log.source,
                                "message": log.message,
                            }
                            for log in final_logs
                        ])
                    # Send run-complete signal so the client knows to stop
                    await websocket.send_json([{
                        "timestamp": run.finished_at.isoformat() if run.finished_at else "",
                        "level": "__DONE__",
                        "source": "",
                        "message": run.status,
                    }])
                    break

            # Send periodic ping every ~30s (30 iterations × 1s) to keep connection alive
            ping_counter += 1
            if ping_counter >= 30:
                try:
                    await websocket.send_json([])  # empty batch as keepalive
                    ping_counter = 0
                except Exception:
                    break

            await asyncio.sleep(1)
    except Exception as e:
        logger.warning("WebSocket error for run %d: %s", run_id, e)
    finally:
        try:
            await websocket.close(code=1000)
        except Exception:
            pass


@router.get("/runs/{run_id}/reports")
async def list_reports(run_id: int, client_key: str, db: AsyncSession = Depends(get_db)) -> dict:
    """List available reports for a run (from database and disk)."""
    run = await _verify_run_owner(run_id, client_key, db)
    reports = {}
    
    # Check database for server-generated reports
    result = await db.execute(
        select(ReportData).where(ReportData.run_id == run_id)
    )
    db_reports = result.scalars().all()
    for report in db_reports:
        reports[report.report_type] = True
    
    # Fall back to disk storage (legacy support)
    run_dir = REPORTS_DIR / str(run_id)
    if run_dir.exists():
        if (run_dir / "junit.xml").exists():
            reports["junit_xml"] = True
        if (run_dir / "report.html").exists() and "html" not in reports:
            reports["html"] = True
        if (run_dir / "report.json").exists() and "json" not in reports:
            reports["json"] = True
        if (run_dir / "coverage" / "coverage.json").exists() and "coverage" not in reports:
            reports["coverage"] = True
        if (run_dir / "allure-results").exists() and any((run_dir / "allure-results").iterdir()) and "allure" not in reports:
            reports["allure"] = True
        if (run_dir / "tests" / "index.json").exists():
            reports["per_test"] = True
        # Per-file reports
        files_dir = run_dir / "files"
        if files_dir.exists():
            file_reports = []
            for fdir in sorted(files_dir.iterdir()):
                if fdir.is_dir():
                    info = {"key": fdir.name}
                    if (fdir / "junit.xml").exists():
                        info["junit_xml"] = True
                    if (fdir / "summary.json").exists():
                        info["summary"] = True
                    file_reports.append(info)
            if file_reports:
                reports["per_file"] = file_reports
    return {"run_id": run_id, "run_name": run.run_name, "available": reports}


@router.get("/runs/{run_id}/reports/download-all")
async def download_all_reports(run_id: int, client_key: str, db: AsyncSession = Depends(get_db)):
    """Download all reports for a run as a ZIP archive."""
    import zipfile
    import io
    run = await _verify_run_owner(run_id, client_key, db)
    run_dir = REPORTS_DIR / str(run_id)
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail="No reports for this run")

    buf = io.BytesIO()
    reports_root = REPORTS_DIR.resolve(strict=False)
    run_label = run.run_name or f"run_{run_id}"
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in run_dir.rglob("*"):
            if f.is_file():
                if reports_root not in f.resolve(strict=False).parents:
                    continue
                arcname = f"{run_label}/{f.relative_to(run_dir)}"
                zf.write(f, arcname)
    buf.seek(0)
    dl_name = f"{run.run_name or f'run_{run_id}'}_reports.zip"
    from starlette.responses import StreamingResponse
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{dl_name}"'},
    )


@router.get("/runs/{run_id}/reports/{report_type}/download")
async def download_single_report(run_id: int, report_type: str, client_key: str, db: AsyncSession = Depends(get_db)):
    """Download a single report file as an attachment. Optionally verifies client ownership."""
    run = await _verify_run_owner(run_id, client_key, db)
    run_dir = REPORTS_DIR / str(run_id)
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail="No reports for this run")

    file_map = {
        "junit_xml": ("junit.xml", "application/xml"),
        "html": ("report.html", "text/html"),
        "json": ("report.json", "application/json"),
        "coverage": ("coverage/coverage.json", "application/json"),
    }
    if report_type not in file_map:
        raise HTTPException(status_code=400, detail=f"Unknown report type: {report_type}")

    filename, media_type = file_map[report_type]
    file_path = (run_dir / filename).resolve(strict=False)
    if REPORTS_DIR.resolve(strict=False) not in file_path.parents:
        raise HTTPException(status_code=400, detail="Invalid path")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"{report_type} report not found")

    dl_name = f"{run.run_name or f'run_{run_id}'}_{filename.replace('/', '_')}"
    return FileResponse(str(file_path), media_type=media_type, filename=dl_name,
                        headers={"Content-Disposition": f'attachment; filename="{dl_name}"'})


@router.get("/runs/{run_id}/reports/{report_type}")
async def get_report(run_id: int, report_type: str, client_key: str, db: AsyncSession = Depends(get_db)):
    """Download a specific report (server-generated from database or legacy disk storage)."""
    await _verify_run_owner(run_id, client_key, db)
    # First, try to fetch report from database (server-generated)
    if report_type in ("html", "json", "coverage", "allure"):
        result = await db.execute(
            select(ReportData).where(
                (ReportData.run_id == run_id) & (ReportData.report_type == report_type)
            )
        )
        report_data = result.scalars().first()
        if report_data:
            if report_type == "html":
                return HTMLResponse(content=report_data.content)
            elif report_type == "json":
                return json.loads(report_data.content)
            elif report_type == "coverage":
                return json.loads(report_data.content)
            elif report_type == "allure":
                return json.loads(report_data.content)

    # Fallback to disk storage (legacy support)
    run_dir = REPORTS_DIR / str(run_id)
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail="No reports for this run")

    file_map = {
        "junit_xml": ("junit.xml", "application/xml"),
        "html": ("report.html", "text/html"),
        "json": ("report.json", "application/json"),
        "coverage": ("coverage/coverage.json", "application/json"),
    }

    if report_type == "allure":
        allure_dir = run_dir / "allure-results"
        if not allure_dir.exists():
            raise HTTPException(status_code=404, detail="Allure results not available")
        # Return allure results as JSON listing
        results = []
        for f in allure_dir.iterdir():
            if f.suffix == ".json":
                try:
                    results.append(json.loads(f.read_text(encoding="utf-8")))
                except Exception:
                    pass
        return {"run_id": run_id, "allure_results": results}

    if report_type not in file_map:
        raise HTTPException(status_code=400, detail=f"Unknown report type: {report_type}")

    filename, media_type = file_map[report_type]
    file_path = run_dir / filename
    # Prevent path traversal — verify resolved path is inside the reports dir
    try:
        file_path = file_path.resolve(strict=False)
        run_dir_resolved = run_dir.resolve(strict=False)
        if run_dir_resolved not in file_path.parents and file_path != run_dir_resolved:
            raise HTTPException(status_code=400, detail="Invalid path")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid path")

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"{report_type} report not available")

    if report_type == "html":
        return HTMLResponse(content=file_path.read_text(encoding="utf-8"))
    elif report_type == "json":
        return json.loads(file_path.read_text(encoding="utf-8"))
    else:
        return FileResponse(str(file_path), media_type=media_type, filename=filename)


@router.get("/runs/{run_id}/reports/test/{nodeid:path}")
async def get_test_report(run_id: int, nodeid: str, client_key: str, db: AsyncSession = Depends(get_db)):
    """Get per-test-case report data. Returns JSON, JUnit, coverage for a single test."""
    run = await _verify_run_owner(run_id, client_key, db)
    import hashlib
    run_dir = REPORTS_DIR / str(run_id)
    tests_dir = run_dir / "tests"
    index_path = tests_dir / "index.json"

    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Per-test reports not available for this run")

    index = json.loads(index_path.read_text(encoding="utf-8"))

    # Try direct match, or match with common variations
    safe_name = index.get(nodeid)
    if not safe_name:
        # Try matching by test function name
        for key, val in index.items():
            if key.endswith(f"::{nodeid.split('::')[-1]}") if "::" in nodeid else key.endswith(f"::{nodeid}"):
                safe_name = val
                break
    if not safe_name:
        raise HTTPException(status_code=404, detail=f"Test '{nodeid}' not found in reports")

    test_dir = tests_dir / safe_name
    if not test_dir.exists():
        raise HTTPException(status_code=404, detail="Test report directory missing")

    result = {}
    result_json = test_dir / "result.json"
    if result_json.exists():
        result["result"] = json.loads(result_json.read_text(encoding="utf-8"))

    junit_xml = test_dir / "junit.xml"
    if junit_xml.exists():
        result["junit_xml"] = junit_xml.read_text(encoding="utf-8")

    result["run_id"] = run_id
    result["run_name"] = run.run_name
    return result


@router.get("/runs/{run_id}/reports/files/{file_key}")
async def get_file_report_by_key(run_id: int, file_key: str, client_key: str, db: AsyncSession = Depends(get_db)):
    """Fetch a pre-generated per-file report by its safe key (e.g. tests__smoke__test_smoke)."""
    run = await _verify_run_owner(run_id, client_key, db)
    file_dir = REPORTS_DIR / str(run_id) / "files" / file_key
    if not file_dir.exists():
        raise HTTPException(status_code=404, detail=f"No per-file report for key '{file_key}'")

    result: dict = {}
    summary_path = file_dir / "summary.json"
    if summary_path.exists():
        result = json.loads(summary_path.read_text(encoding="utf-8"))

    junit_path = file_dir / "junit.xml"
    if junit_path.exists():
        result["junit_xml"] = junit_path.read_text(encoding="utf-8")

    if not result:
        raise HTTPException(status_code=404, detail="Per-file report data missing")

    result["run_id"] = run_id
    result["run_name"] = run.run_name
    result["file_key"] = file_key
    return result


@router.get("/runs/{run_id}/reports/file/{file_path:path}")
async def get_file_report(run_id: int, file_path: str, client_key: str, db: AsyncSession = Depends(get_db)):
    """Report for all tests in a given file. Uses pre-generated per-file data when available."""
    run = await _verify_run_owner(run_id, client_key, db)
    run_dir = REPORTS_DIR / str(run_id)

    # Try pre-generated per-file report first
    file_key = file_path.replace("/", "__").replace("\\", "__").replace(".py", "")
    file_dir = run_dir / "files" / file_key
    summary_path = file_dir / "summary.json"
    if summary_path.exists():
        data = json.loads(summary_path.read_text(encoding="utf-8"))
        data["run_id"] = run_id
        data["run_name"] = run.run_name
        # Attach JUnit XML if available
        junit_path = file_dir / "junit.xml"
        if junit_path.exists():
            data["junit_xml"] = junit_path.read_text(encoding="utf-8")
        return data

    # Fallback: dynamically aggregate from per-test data
    tests_dir = run_dir / "tests"
    index_path = tests_dir / "index.json"

    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Per-test reports not available")

    index = json.loads(index_path.read_text(encoding="utf-8"))

    file_tests = []
    for nodeid, safe_name in index.items():
        test_file = nodeid.split("::")[0].replace(".", "/")
        if not test_file.endswith(".py"):
            test_file += ".py"
        if test_file == file_path or test_file.endswith(file_path) or file_path in test_file:
            result_path = tests_dir / safe_name / "result.json"
            if result_path.exists():
                file_tests.append(json.loads(result_path.read_text(encoding="utf-8")))

    if not file_tests:
        raise HTTPException(status_code=404, detail=f"No test results found for file '{file_path}'")

    total = len(file_tests)
    passed = sum(1 for t in file_tests if t["status"] == "passed")
    failed = sum(1 for t in file_tests if t["status"] == "failed")
    errored = sum(1 for t in file_tests if t["status"] == "error")
    skippd = sum(1 for t in file_tests if t["status"] == "skipped")
    total_time = sum(t["time"] for t in file_tests)

    return {
        "file": file_path,
        "run_id": run_id,
        "run_name": run.run_name,
        "summary": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "errors": errored,
            "skipped": skippd,
            "total_time": round(total_time, 3),
            "pass_rate": round(passed / total * 100, 1) if total > 0 else 0,
        },
        "tests": file_tests,
    }


@router.get("/runs/{run_id}/reports/suite/{suite_id}")
async def get_suite_report(run_id: int, suite_id: str, client_key: str, db: AsyncSession = Depends(get_db)):
    """Aggregate report for a test suite. Dynamically aggregated from per-test data."""
    run = await _verify_run_owner(run_id, client_key, db)
    # Build the suite definition
    suites = _build_test_suites()
    suite = next((s for s in suites if s["id"] == suite_id), None)
    if not suite:
        raise HTTPException(status_code=404, detail=f"Suite '{suite_id}' not found")

    run_dir = REPORTS_DIR / str(run_id)
    tests_dir = run_dir / "tests"
    index_path = tests_dir / "index.json"

    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Per-test reports not available")

    index = json.loads(index_path.read_text(encoding="utf-8"))

    # Collect results for all tests in the suite
    suite_tests = []
    for test_nodeid in suite["tests"]:
        # Try matching against the index (index uses classname-based nodeids)
        func_name = test_nodeid.split("::")[-1] if "::" in test_nodeid else test_nodeid
        for idx_nodeid, safe_name in index.items():
            if idx_nodeid.endswith(f"::{func_name}"):
                result_path = tests_dir / safe_name / "result.json"
                if result_path.exists():
                    suite_tests.append(json.loads(result_path.read_text(encoding="utf-8")))
                break

    total = len(suite_tests)
    passed = sum(1 for t in suite_tests if t["status"] == "passed")
    failed = sum(1 for t in suite_tests if t["status"] == "failed")
    errored = sum(1 for t in suite_tests if t["status"] == "error")
    skippd = sum(1 for t in suite_tests if t["status"] == "skipped")
    total_time = sum(t["time"] for t in suite_tests)

    return {
        "suite_id": suite_id,
        "suite_name": suite["name"],
        "run_id": run_id,
        "run_name": run.run_name,
        "summary": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "errors": errored,
            "skipped": skippd,
            "total_time": round(total_time, 3),
            "pass_rate": round(passed / total * 100, 1) if total > 0 else 0,
        },
        "tests": suite_tests,
    }


@router.get("/metrics")
async def get_metrics(client_key: str, db: AsyncSession = Depends(get_db)) -> dict:
    """Get metrics for the requesting client's runs only."""
    from datetime import datetime, timedelta
    client = await _resolve_client(client_key, db)

    # Use SQL COUNT for efficiency instead of loading all rows
    total_runs = (await db.execute(select(func.count(Run.id)).where(Run.client_id == client.id))).scalar_one()
    completed_runs = (await db.execute(select(func.count(Run.id)).where(Run.client_id == client.id, Run.status == "completed"))).scalar_one()
    failed_runs = (await db.execute(select(func.count(Run.id)).where(Run.client_id == client.id, Run.status == "failed"))).scalar_one()
    running_runs = (await db.execute(select(func.count(Run.id)).where(Run.client_id == client.id, Run.status == "running"))).scalar_one()
    pending_runs = (await db.execute(select(func.count(Run.id)).where(Run.client_id == client.id, Run.status == "pending"))).scalar_one()
    cancelled_runs = (await db.execute(select(func.count(Run.id)).where(Run.client_id == client.id, Run.status == "cancelled"))).scalar_one()
    queued_runs = (await db.execute(select(func.count(Run.id)).where(Run.client_id == client.id, Run.status == "queued"))).scalar_one()

    # Success rate (only count completed vs failed; exclude cancelled/pending/queued/running)
    decisive_runs = completed_runs + failed_runs
    success_rate = (completed_runs / decisive_runs * 100) if decisive_runs > 0 else 0

    # Recent runs (last 24 hours) - count only
    one_day_ago = datetime.now(timezone.utc) - timedelta(days=1)
    recent_runs = (await db.execute(
        select(func.count(Run.id)).where(Run.client_id == client.id, Run.created_at >= one_day_ago)
    )).scalar_one()

    # Resource utilization (only this client's runs)
    resource_stats_result = await db.execute(
        select(Resource.name, func.count(Run.id))
        .join(Run, isouter=True)
        .where(Run.client_id == client.id)
        .group_by(Resource.id)
    )
    resource_stats = [{"name": row[0], "runs": row[1] or 0} for row in resource_stats_result]

    return {
        "total_runs": total_runs,
        "completed_runs": completed_runs,
        "failed_runs": failed_runs,
        "running_runs": running_runs,
        "pending_runs": pending_runs,
        "cancelled_runs": cancelled_runs,
        "queued_runs": queued_runs,
        "success_rate": round(success_rate, 2),
        "recent_runs": recent_runs,
        "resource_stats": resource_stats
    }


# ── Test Suites ──

def _discover_nodeids_from_file(text: str, posix_path: str) -> list[str]:
    """Parse a test file and return properly qualified nodeids (class-aware)."""
    nodeids: list[str] = []
    current_class: str | None = None
    for line in text.splitlines():
        class_match = re.match(r"^class\s+(Test[A-Za-z0-9_]+)", line)
        if class_match:
            current_class = class_match.group(1)
            continue
        if line and not line[0].isspace() and not line.startswith("#"):
            if not line.startswith("class "):
                current_class = None
        func_match = re.match(r"^(\s+)?def\s+(test_[A-Za-z0-9_]+)", line)
        if func_match:
            indent = func_match.group(1) or ""
            func_name = func_match.group(2)
            if indent and current_class:
                nodeids.append(f"{posix_path}::{current_class}::{func_name}")
            else:
                nodeids.append(f"{posix_path}::{func_name}")
                current_class = None
    return nodeids


# ── Marker-based test discovery ──
_MARKER_RE = re.compile(r"@pytest\.mark\.(\w+)")


def _discover_markers_from_files() -> dict[str, list[str]]:
    """Scan test files for @pytest.mark.xxx decorators and map marker→nodeids."""
    backend_dir = Path(__file__).resolve().parents[2]
    marker_map: dict[str, list[str]] = collections.defaultdict(list)
    builtin_markers = {"parametrize", "skip", "skipif", "xfail", "usefixtures", "filterwarnings", "timeout"}

    for path in Path(TEST_ROOT).glob("**/test_*.py"):
        text = path.read_text(encoding="utf-8")
        rel_path = path.relative_to(backend_dir)
        posix_path = rel_path.as_posix()
        current_class: str | None = None
        pending_markers: list[str] = []

        for line in text.splitlines():
            stripped = line.strip()
            # Track class scope
            class_match = re.match(r"^class\s+(Test[A-Za-z0-9_]+)", line)
            if class_match:
                current_class = class_match.group(1)
                pending_markers.clear()
                continue
            if line and not line[0].isspace() and not line.startswith("#") and not line.startswith("class ") and not stripped.startswith("@"):
                current_class = None

            # Collect markers above a function
            marker_match = _MARKER_RE.search(stripped)
            if marker_match:
                marker_name = marker_match.group(1).lower()
                if marker_name not in builtin_markers:
                    pending_markers.append(marker_name)
                continue

            # When we hit a test function, assign collected markers
            func_match = re.match(r"^(\s+)?def\s+(test_[A-Za-z0-9_]+)", line)
            if func_match:
                indent = func_match.group(1) or ""
                func_name = func_match.group(2)
                if indent and current_class:
                    nodeid = f"{posix_path}::{current_class}::{func_name}"
                else:
                    nodeid = f"{posix_path}::{func_name}"
                for marker in pending_markers:
                    marker_map[marker].append(nodeid)
                pending_markers.clear()
            elif not stripped.startswith("@") and not stripped.startswith("#") and stripped:
                pending_markers.clear()

    return dict(marker_map)


def _get_all_test_nodeids() -> list[str]:
    """Collect all test nodeids from the test root with TTL caching."""
    import time
    now = time.time()
    if _test_cache["nodeids"] and (now - _test_cache["timestamp"]) < _TEST_CACHE_TTL:
        return _test_cache["nodeids"]

    backend_dir = Path(__file__).resolve().parents[2]
    nodeids = []
    for path in Path(TEST_ROOT).glob("**/test_*.py"):
        text = path.read_text(encoding="utf-8")
        rel_path = path.relative_to(backend_dir)
        nodeids.extend(_discover_nodeids_from_file(text, rel_path.as_posix()))

    _test_cache["nodeids"] = nodeids
    _test_cache["timestamp"] = now
    return nodeids


def _build_test_suites() -> list[dict]:
    """Build predefined test suites based on discovered tests."""
    all_tests = _get_all_test_nodeids()

    unit_tests = [t for t in all_tests if "/unit/" in t]
    integration_tests = [t for t in all_tests if "/integration/" in t]
    smoke_tests = [t for t in all_tests if "/smoke/" in t]
    quick_tests = [t for t in all_tests if "_quick" in t]
    security_tests = [t for t in all_tests if "security" in t.lower()]
    data_tests = [t for t in all_tests if "data" in t.lower()]
    math_tests = [t for t in all_tests if "math" in t.lower()]
    string_tests = [t for t in all_tests if "string" in t.lower()]
    dummy_tests = [t for t in all_tests if "dummy" in t.lower()]

    suites = []

    suites.append({
        "id": "all",
        "name": "All Tests",
        "description": "Run every discovered test in the project",
        "tests": all_tests,
        "tags": ["complete"],
        "source": "auto",
    })

    if smoke_tests:
        suites.append({
            "id": "smoke",
            "name": "Smoke Tests",
            "description": "Quick sanity checks to verify basic functionality is working",
            "tests": smoke_tests,
            "tags": ["fast", "ci"],
            "source": "auto",
        })

    if unit_tests:
        suites.append({
            "id": "unit",
            "name": "Unit Tests",
            "description": "Isolated unit tests for individual functions and modules",
            "tests": unit_tests,
            "tags": ["fast", "isolated"],
            "source": "auto",
        })

    if integration_tests:
        suites.append({
            "id": "integration",
            "name": "Integration Tests",
            "description": "Tests that verify multiple components working together",
            "tests": integration_tests,
            "tags": ["slow", "api"],
            "source": "auto",
        })

    if quick_tests:
        suites.append({
            "id": "quick",
            "name": "Quick Validation",
            "description": "Fast-running tests for rapid feedback during development",
            "tests": quick_tests,
            "tags": ["fast", "dev"],
            "source": "auto",
        })

    if security_tests:
        suites.append({
            "id": "security",
            "name": "Security Tests",
            "description": "Tests focused on security validations and vulnerability checks",
            "tests": security_tests,
            "tags": ["security", "ci"],
            "source": "auto",
        })

    if data_tests:
        suites.append({
            "id": "data",
            "name": "Data Tests",
            "description": "Tests for data processing, validation, and integrity",
            "tests": data_tests,
            "tags": ["data"],
            "source": "auto",
        })

    if math_tests or string_tests:
        suites.append({
            "id": "core-ops",
            "name": "Core Operations",
            "description": "Math and string operation tests covering core utility functions",
            "tests": math_tests + string_tests,
            "tags": ["fast", "core"],
            "source": "auto",
        })

    if dummy_tests:
        suites.append({
            "id": "dummy",
            "name": "Sample / Dummy Tests",
            "description": "Example tests used for demonstration and template purposes",
            "tests": dummy_tests,
            "tags": ["sample"],
            "source": "auto",
        })

    # ── Marker-based suites ──
    marker_map = _discover_markers_from_files()
    for marker_name, marker_tests in sorted(marker_map.items()):
        suites.append({
            "id": f"marker-{marker_name}",
            "name": f"@{marker_name}",
            "description": f"Tests decorated with @pytest.mark.{marker_name}",
            "tests": marker_tests,
            "tags": ["marker", marker_name],
            "source": "marker",
        })

    return suites


async def _get_suite_history(db: AsyncSession, suite_id: str, limit: int = 10) -> list[dict]:
    """Get recent run history for a suite from the run_suite_links table."""
    result = await db.execute(
        select(RunSuiteLink.run_id, Run.status, Run.created_at, Run.started_at, Run.finished_at, Run.run_name)
        .join(Run, Run.id == RunSuiteLink.run_id)
        .where(RunSuiteLink.suite_id == suite_id)
        .order_by(Run.created_at.desc())
        .limit(limit)
    )
    history = []
    for row in result.all():
        run_id, run_status, created_at, started_at, finished_at, run_name = row
        duration = None
        if started_at and finished_at:
            duration = (finished_at - started_at).total_seconds()
        history.append({
            "run_id": run_id,
            "run_name": run_name,
            "status": run_status,
            "created_at": created_at.isoformat() if created_at else None,
            "duration": round(duration, 2) if duration is not None else None,
        })
    return history


async def _get_estimated_duration(db: AsyncSession, suite_id: str) -> float | None:
    """Estimate suite duration from last 5 completed runs."""
    result = await db.execute(
        select(Run.started_at, Run.finished_at)
        .join(RunSuiteLink, RunSuiteLink.run_id == Run.id)
        .where(RunSuiteLink.suite_id == suite_id, Run.status.in_(["completed", "failed"]))
        .where(Run.started_at.is_not(None), Run.finished_at.is_not(None))
        .order_by(Run.created_at.desc())
        .limit(5)
    )
    durations = []
    for started_at, finished_at in result.all():
        durations.append((finished_at - started_at).total_seconds())
    return round(sum(durations) / len(durations), 1) if durations else None


@router.get("/test-suites", response_model=list[TestSuite])
async def get_test_suites(db: AsyncSession = Depends(get_db)):
    """Return all suites: auto-generated + marker-based + custom."""
    auto_suites = _build_test_suites()

    # Load custom suites from DB
    result = await db.execute(select(CustomSuite).order_by(CustomSuite.name))
    custom_suites = result.scalars().all()
    for cs in custom_suites:
        auto_suites.append({
            "id": f"custom-{cs.id}",
            "name": cs.name,
            "description": cs.description or "",
            "tests": cs.tests or [],
            "tags": cs.tags or [],
            "source": "custom",
        })

    # Append estimated_duration and last_run for all suites
    for suite in auto_suites:
        est = await _get_estimated_duration(db, suite["id"])
        suite["estimated_duration"] = est
        history = await _get_suite_history(db, suite["id"], limit=1)
        if history:
            h = history[0]
            suite["last_run"] = {"run_id": h["run_id"], "run_name": h["run_name"], "status": h["status"], "timestamp": h["created_at"]}
        else:
            suite["last_run"] = None

    return auto_suites


@router.get("/test-suites/{suite_id}/history")
async def get_suite_history(suite_id: str, db: AsyncSession = Depends(get_db)):
    """Return run history for a specific suite."""
    history = await _get_suite_history(db, suite_id, limit=20)
    return {"suite_id": suite_id, "runs": history}


# ── Custom Suite CRUD ──

@router.post("/custom-suites", response_model=CustomSuiteOut, status_code=status.HTTP_201_CREATED)
async def create_custom_suite(payload: CustomSuiteCreate, db: AsyncSession = Depends(get_db)):
    """Create a user-defined test suite."""
    suite = CustomSuite(
        name=payload.name,
        description=payload.description,
        tests=payload.tests,
        tags=payload.tags,
    )
    db.add(suite)
    await db.commit()
    await db.refresh(suite)
    return suite


@router.get("/custom-suites", response_model=list[CustomSuiteOut])
async def list_custom_suites(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(CustomSuite).order_by(CustomSuite.created_at.desc()))
    return result.scalars().all()


@router.put("/custom-suites/{suite_id}", response_model=CustomSuiteOut)
async def update_custom_suite(suite_id: int, payload: CustomSuiteUpdate, db: AsyncSession = Depends(get_db)):
    suite = await db.get(CustomSuite, suite_id)
    if not suite:
        raise HTTPException(status_code=404, detail="Custom suite not found")
    if payload.name is not None:
        suite.name = payload.name
    if payload.description is not None:
        suite.description = payload.description
    if payload.tests is not None:
        suite.tests = payload.tests
    if payload.tags is not None:
        suite.tags = payload.tags
    await db.commit()
    await db.refresh(suite)
    return suite


@router.delete("/custom-suites/{suite_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_custom_suite(suite_id: int, db: AsyncSession = Depends(get_db)):
    suite = await db.get(CustomSuite, suite_id)
    if not suite:
        raise HTTPException(status_code=404, detail="Custom suite not found")
    await db.delete(suite)
    await db.commit()


# ── Setup Configuration CRUD ──

@router.post("/setup-configurations", response_model=SetupConfigOut, status_code=status.HTTP_201_CREATED)
async def create_setup_config(payload: SetupConfigCreate, db: AsyncSession = Depends(get_db)):
    """Create a setup configuration with ordered steps."""
    config = SetupConfiguration(name=payload.name, description=payload.description)
    db.add(config)
    await db.flush()
    for i, step_data in enumerate(payload.steps):
        step = SetupStep(
            config_id=config.id,
            name=step_data.name,
            step_type=step_data.step_type,
            command=step_data.command,
            timeout=step_data.timeout,
            order=i,
            on_failure=step_data.on_failure,
            env_vars=step_data.env_vars,
        )
        db.add(step)
    await db.commit()
    await db.refresh(config, ["steps"])
    return config


@router.get("/setup-configurations", response_model=list[SetupConfigOut])
async def list_setup_configs(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(SetupConfiguration).order_by(SetupConfiguration.created_at.desc())
    )
    configs = result.scalars().unique().all()
    # Eagerly load steps
    for config in configs:
        await db.refresh(config, ["steps"])
    return configs


@router.get("/setup-configurations/{config_id}", response_model=SetupConfigOut)
async def get_setup_config(config_id: int, db: AsyncSession = Depends(get_db)):
    config = await db.get(SetupConfiguration, config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Setup configuration not found")
    await db.refresh(config, ["steps"])
    return config


@router.put("/setup-configurations/{config_id}", response_model=SetupConfigOut)
async def update_setup_config(config_id: int, payload: SetupConfigUpdate, db: AsyncSession = Depends(get_db)):
    config = await db.get(SetupConfiguration, config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Setup configuration not found")
    if payload.name is not None:
        config.name = payload.name
    if payload.description is not None:
        config.description = payload.description
    if payload.steps is not None:
        # Replace all steps
        await db.refresh(config, ["steps"])
        for old_step in config.steps:
            await db.delete(old_step)
        await db.flush()
        for i, step_data in enumerate(payload.steps):
            step = SetupStep(
                config_id=config.id,
                name=step_data.name,
                step_type=step_data.step_type,
                command=step_data.command,
                timeout=step_data.timeout,
                order=i,
                on_failure=step_data.on_failure,
                env_vars=step_data.env_vars,
            )
            db.add(step)
    await db.commit()
    await db.refresh(config, ["steps"])
    return config


@router.delete("/setup-configurations/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_setup_config(config_id: int, db: AsyncSession = Depends(get_db)):
    config = await db.get(SetupConfiguration, config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Setup configuration not found")
    await db.refresh(config, ["steps"])
    for step in config.steps:
        await db.delete(step)
    await db.delete(config)
    await db.commit()


# ── Pre-defined Setup Scripts ──

SETUP_SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "setup_scripts"


@router.get("/setup-scripts")
async def list_setup_scripts():
    """List pre-defined setup scripts available on the server."""
    if not SETUP_SCRIPTS_DIR.exists():
        return []
    scripts = []
    for f in sorted(SETUP_SCRIPTS_DIR.iterdir()):
        if f.suffix == ".py" and f.is_file():
            desc = ""
            try:
                content = f.read_text(encoding="utf-8")
                if content.startswith('"""'):
                    end = content.index('"""', 3)
                    desc = content[3:end].strip().split("\n")[0]
            except Exception:
                pass
            scripts.append({
                "name": f.stem,
                "filename": f.name,
                "description": desc,
            })
    return scripts


# ── Teardown Configuration CRUD ──

@router.post("/teardown-configurations", response_model=TeardownConfigOut, status_code=status.HTTP_201_CREATED)
async def create_teardown_config(payload: TeardownConfigCreate, db: AsyncSession = Depends(get_db)):
    """Create a teardown configuration with ordered steps."""
    config = TeardownConfiguration(name=payload.name, description=payload.description)
    db.add(config)
    await db.flush()
    for i, step_data in enumerate(payload.steps):
        step = TeardownStep(
            config_id=config.id,
            name=step_data.name,
            step_type=step_data.step_type,
            command=step_data.command,
            timeout=step_data.timeout,
            order=i,
            on_failure=step_data.on_failure,
            env_vars=step_data.env_vars,
        )
        db.add(step)
    await db.commit()
    await db.refresh(config, ["steps"])
    return config


@router.get("/teardown-configurations", response_model=list[TeardownConfigOut])
async def list_teardown_configs(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(TeardownConfiguration).order_by(TeardownConfiguration.created_at.desc())
    )
    configs = result.scalars().unique().all()
    for config in configs:
        await db.refresh(config, ["steps"])
    return configs


@router.get("/teardown-configurations/{config_id}", response_model=TeardownConfigOut)
async def get_teardown_config(config_id: int, db: AsyncSession = Depends(get_db)):
    config = await db.get(TeardownConfiguration, config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Teardown configuration not found")
    await db.refresh(config, ["steps"])
    return config


@router.put("/teardown-configurations/{config_id}", response_model=TeardownConfigOut)
async def update_teardown_config(config_id: int, payload: TeardownConfigUpdate, db: AsyncSession = Depends(get_db)):
    config = await db.get(TeardownConfiguration, config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Teardown configuration not found")
    if payload.name is not None:
        config.name = payload.name
    if payload.description is not None:
        config.description = payload.description
    if payload.steps is not None:
        await db.refresh(config, ["steps"])
        for old_step in config.steps:
            await db.delete(old_step)
        await db.flush()
        for i, step_data in enumerate(payload.steps):
            step = TeardownStep(
                config_id=config.id,
                name=step_data.name,
                step_type=step_data.step_type,
                command=step_data.command,
                timeout=step_data.timeout,
                order=i,
                on_failure=step_data.on_failure,
                env_vars=step_data.env_vars,
            )
            db.add(step)
    await db.commit()
    await db.refresh(config, ["steps"])
    return config


@router.delete("/teardown-configurations/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_teardown_config(config_id: int, db: AsyncSession = Depends(get_db)):
    config = await db.get(TeardownConfiguration, config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Teardown configuration not found")
    await db.refresh(config, ["steps"])
    for step in config.steps:
        await db.delete(step)
    await db.delete(config)
    await db.commit()


# ── Pre-defined Teardown Scripts ──

TEARDOWN_SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "teardown_scripts"


@router.get("/teardown-scripts")
async def list_teardown_scripts():
    """List pre-defined teardown scripts available on the server."""
    if not TEARDOWN_SCRIPTS_DIR.exists():
        return []
    scripts = []
    for f in sorted(TEARDOWN_SCRIPTS_DIR.iterdir()):
        if f.suffix == ".py" and f.is_file():
            desc = ""
            try:
                content = f.read_text(encoding="utf-8")
                if content.startswith('"""'):
                    end = content.index('"""', 3)
                    desc = content[3:end].strip().split("\n")[0]
            except Exception:
                pass
            scripts.append({
                "name": f.stem,
                "filename": f.name,
                "description": desc,
            })
    return scripts



# ── Test Upload ──

UPLOADS_DIR = Path(__file__).resolve().parents[2] / "data" / "uploads"
MAX_UPLOAD_SIZE = int(os.getenv("MAX_UPLOAD_SIZE_MB", "50")) * 1024 * 1024  # default 50 MB
UPLOAD_CLEANUP_MINUTES = int(os.getenv("UPLOAD_CLEANUP_MINUTES", "10"))


@router.post("/tests/upload")
async def upload_tests(
    client_key: str = Query(..., description="Client key for ownership"),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload a ZIP file of test files. Extracts to a per-client isolated directory."""
    import zipfile
    import io
    import shutil

    # Validate client
    client = (await db.execute(select(Client).where(Client.client_key == client_key))).scalars().first()
    if not client:
        raise HTTPException(status_code=401, detail="Invalid client key")

    # Validate file type
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip files are accepted")

    # Read with size limit
    contents = await file.read()
    if len(contents) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail=f"File too large. Maximum size: {MAX_UPLOAD_SIZE // (1024*1024)} MB")

    # Content-based dedup: same ZIP content → reuse existing upload
    import hashlib
    content_hash = hashlib.sha256(contents).hexdigest()[:12]
    client_uploads = UPLOADS_DIR / client.client_key
    if client_uploads.exists():
        for existing in client_uploads.iterdir():
            if existing.is_dir() and existing.name.endswith(f"_{content_hash}"):
                # Same content already uploaded — return existing
                backend_dir = Path(__file__).resolve().parents[2]
                test_files = []
                nodeids_list: list[str] = []
                for py_file in existing.rglob("test_*.py"):
                    rel_from_upload = py_file.relative_to(existing)
                    test_files.append(str(rel_from_upload))
                    try:
                        text = py_file.read_text(encoding="utf-8")
                        posix_path = py_file.relative_to(backend_dir).as_posix()
                        nodeids_list.extend(_discover_nodeids_from_file(text, posix_path))
                    except Exception:
                        pass
                return {
                    "upload_id": existing.name,
                    "client_key": client.client_key,
                    "files": test_files,
                    "nodeids": nodeids_list,
                    "total_files": len(test_files),
                    "total_tests": len(nodeids_list),
                    "path": str(existing.relative_to(UPLOADS_DIR.parent.parent)),
                    "cleanup_after_minutes": UPLOAD_CLEANUP_MINUTES,
                    "deduplicated": True,
                }

    # Short, human-readable upload ID: zip filename stem + 8-char hash suffix
    zip_stem = Path(file.filename).stem if file.filename else "upload"
    # Sanitize: keep alphanumeric, hyphens, underscores only
    safe_stem = "".join(c if c.isalnum() or c in "-_" else "_" for c in zip_stem)[:40]
    upload_id = f"{safe_stem}_{content_hash}"
    upload_dir = UPLOADS_DIR / client.client_key / upload_id

    # Validate and extract ZIP, flattening single-root archives
    try:
        with zipfile.ZipFile(io.BytesIO(contents)) as zf:
            # Security: check for path traversal in ZIP entries
            for info in zf.infolist():
                if info.filename.startswith("/") or ".." in info.filename:
                    raise HTTPException(status_code=400, detail="Invalid ZIP: path traversal detected")
                # Reject very large decompressed files (zip bomb protection)
                if info.file_size > MAX_UPLOAD_SIZE * 3:
                    raise HTTPException(status_code=400, detail="Invalid ZIP: decompressed file too large")

            # Detect single-root directory (e.g. ZIP contains my_tests/test_a.py, my_tests/test_b.py)
            entries = [n for n in zf.namelist() if not n.endswith("/")]
            top_dirs = set()
            for entry in entries:
                parts = entry.split("/")
                if len(parts) > 1:
                    top_dirs.add(parts[0])
                else:
                    top_dirs.clear()
                    break  # file at root level — no single-root wrapper

            upload_dir.mkdir(parents=True, exist_ok=True)

            if len(top_dirs) == 1:
                # Flatten: strip the single top-level wrapper directory
                wrapper = top_dirs.pop() + "/"
                for info in zf.infolist():
                    if info.filename.startswith(wrapper):
                        target_name = info.filename[len(wrapper):]
                        if not target_name:
                            continue  # skip the directory entry itself
                        target_path = upload_dir / target_name
                        if info.is_dir():
                            target_path.mkdir(parents=True, exist_ok=True)
                        else:
                            target_path.parent.mkdir(parents=True, exist_ok=True)
                            with zf.open(info) as src, open(target_path, "wb") as dst:
                                dst.write(src.read())
            else:
                zf.extractall(upload_dir)
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Invalid ZIP file")
    except HTTPException:
        raise
    except Exception as e:
        # Cleanup on failure
        if upload_dir.exists():
            shutil.rmtree(upload_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Failed to extract ZIP: {e}")

    # Discover test files and generate nodeids (relative to backend/ so pytest can find them)
    backend_dir = Path(__file__).resolve().parents[2]
    test_files = []
    nodeids = []
    for py_file in upload_dir.rglob("test_*.py"):
        rel_from_upload = py_file.relative_to(upload_dir)
        test_files.append(str(rel_from_upload))
        # Generate nodeids by parsing test functions, relative to backend/ (cwd for pytest)
        try:
            text = py_file.read_text(encoding="utf-8")
            rel_from_backend = py_file.relative_to(backend_dir)
            posix_path = rel_from_backend.as_posix()
            nodeids.extend(_discover_nodeids_from_file(text, posix_path))
        except Exception:
            pass

    return {
        "upload_id": upload_id,
        "client_key": client.client_key,
        "files": test_files,
        "nodeids": nodeids,
        "total_files": len(test_files),
        "total_tests": len(nodeids),
        "path": str(upload_dir.relative_to(UPLOADS_DIR.parent.parent)),
        "cleanup_after_minutes": UPLOAD_CLEANUP_MINUTES,
    }


@router.get("/tests/uploads")
async def list_uploads(
    client_key: str = Query(..., description="Client key for ownership"),
    db: AsyncSession = Depends(get_db),
):
    """List uploaded test folders belonging to a specific client."""
    client = (await db.execute(select(Client).where(Client.client_key == client_key))).scalars().first()
    if not client:
        raise HTTPException(status_code=401, detail="Invalid client key")

    client_dir = UPLOADS_DIR / client.client_key
    if not client_dir.exists():
        return []

    uploads = []
    for d in sorted(client_dir.iterdir(), reverse=True):
        if d.is_dir():
            test_files = list(d.rglob("*.py"))
            # Derive human-readable label from upload_id (format: {name}_{hash})
            parts = d.name.rsplit("_", 1)
            label = parts[0] if len(parts) == 2 else d.name
            uploads.append({
                "upload_id": d.name,
                "label": label,
                "files_count": len(test_files),
                "created_at": datetime.fromtimestamp(d.stat().st_ctime, tz=timezone.utc).isoformat(),
            })
    return uploads


@router.delete("/tests/uploads/{upload_id}")
async def delete_upload(
    upload_id: str,
    client_key: str = Query(..., description="Client key for ownership"),
    db: AsyncSession = Depends(get_db),
):
    """Delete an uploaded test folder. Only the owning client can delete."""
    import shutil

    client = (await db.execute(select(Client).where(Client.client_key == client_key))).scalars().first()
    if not client:
        raise HTTPException(status_code=401, detail="Invalid client key")

    # Security: validate upload_id belongs to this client
    upload_dir = (UPLOADS_DIR / client.client_key / upload_id).resolve(strict=False)
    client_dir = (UPLOADS_DIR / client.client_key).resolve(strict=False)
    if client_dir not in upload_dir.parents and upload_dir != client_dir:
        raise HTTPException(status_code=403, detail="Access denied")

    if not upload_dir.exists():
        raise HTTPException(status_code=404, detail="Upload not found")

    shutil.rmtree(upload_dir, ignore_errors=True)
    return {"deleted": upload_id}


# ── CLI Command Execution ──

ALLOWED_CLI_PREFIXES = ["pytest", "python -m pytest", "python -m unittest"]


def _validate_cli_command(command: str) -> bool:
    """Validate that a CLI command is safe to execute.

    Uses allowlist-only approach: the command must start with an allowed
    prefix and every argument must look like a test path / pytest flag.
    Shell meta-characters are rejected outright.
    """
    import shlex
    cmd = command.strip()
    # Reject any shell metacharacters (including newlines)
    if re.search(r'[;|&`$<>\n\r]', cmd):
        return False
    if not any(cmd.startswith(prefix) for prefix in ALLOWED_CLI_PREFIXES):
        return False
    # Parse into tokens and validate each one
    try:
        tokens = shlex.split(cmd)
    except ValueError:
        return False
    # Skip the command prefix tokens (e.g. "python", "-m", "pytest")
    skip = 0
    for prefix in ALLOWED_CLI_PREFIXES:
        n = len(shlex.split(prefix))
        if tokens[:n] == shlex.split(prefix):
            skip = n
            break
    for token in tokens[skip:]:
        # Allow pytest flags (start with -)
        if token.startswith("-"):
            continue
        # Allow test paths: must match test_*.py or contain :: or be a directory-like path
        if re.fullmatch(r'[\w./\\:*\-\[\]]+', token):
            continue
        return False
    return True


@router.post("/cli/execute")
async def execute_cli_command(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    request: Request = None,
):
    """Execute a CLI command (restricted to test-related commands)."""
    client_key = payload.get("client_key")
    command = payload.get("command", "").strip()
    resource_name = payload.get("resource_name")

    if not client_key:
        raise HTTPException(status_code=400, detail="client_key is required")
    if not command:
        raise HTTPException(status_code=400, detail="command is required")
    if not _validate_cli_command(command):
        raise HTTPException(
            status_code=400,
            detail="Only test commands are allowed (pytest, python -m pytest, python -m unittest). Shell operators are forbidden.",
        )

    statement = select(Client).where(Client.client_key == client_key)
    result = await db.execute(statement)
    client = result.scalars().first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    notification_service = getattr(request.app.state, 'notification_service', None) if request else None

    run = Run(
        client_id=client.id,
        selected_tests=[],
        status="pending",
        note=f"CLI: {command}",
        run_name=await generate_run_name(db, client.id),
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    if resource_name:
        resource = await ResourceQueueManager.find_or_create_resource(db, resource_name)
        acquired = await ResourceQueueManager.acquire_lock(db, run, resource)
        if not acquired:
            await ResourceQueueManager.enqueue_run(db, run, resource)
        else:
            asyncio.create_task(_schedule_cli_run(run.id, command, notification_service))
    else:
        run.status = "running"
        db.add(run)
        await db.commit()
        asyncio.create_task(_schedule_cli_run(run.id, command, notification_service))

    await db.refresh(run)
    return run


async def _schedule_cli_run(run_id: int, command: str, notification_service=None):
    """Execute a CLI command as a run."""
    from app.services.runner import capture_cli_run
    async with AsyncSessionLocal() as session:
        run = await session.get(Run, run_id)
        if run is None:
            return
        try:
            await capture_cli_run(run_id, command, session, notification_service)
        except Exception:
            run = await session.get(Run, run_id)
            if run and run.status not in ("completed", "failed", "cancelled"):
                run.status = "failed"
                await session.commit()
            logger.error("CLI run %d failed unexpectedly", run_id, exc_info=True)
        finally:
            run = await session.get(Run, run_id)
            if run and run.resource_id:
                resource = await session.get(Resource, run.resource_id)
                if resource:
                    next_run_id = await ResourceQueueManager.release_resource(session, resource, run_id=run_id)
                    if next_run_id:
                        asyncio.create_task(schedule_run_task(next_run_id, notification_service))
