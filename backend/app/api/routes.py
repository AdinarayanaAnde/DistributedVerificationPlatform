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

from fastapi import APIRouter, Depends, HTTPException, status, WebSocket, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import authenticate_client, create_access_token, get_current_client, get_password_hash
from app.db import AsyncSessionLocal, get_db
from app.models import Client, LogEntry, QueueEntry, Resource, ResourceLock, Run
from app.schemas import (
    ClientCreate,
    ClientOut,
    LogEntryOut,
    QueueEntryOut,
    ResourceOut,
    RunCreate,
    RunOut,
    TestItem,
    TestSuite,
)
from app.services.notifications import NotificationService
from app.services.queue import ResourceQueueManager
from app.services.runner import TEST_ROOT, REPORTS_DIR, capture_test_run, cancel_run, cancel_run_file, get_active_files

logger = logging.getLogger(__name__)

router = APIRouter()
security = HTTPBearer()

# ── Admin API key (simple shared secret for admin endpoints) ──
import os
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")


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
async def purge_old_data(retention_days: int = 7, db: AsyncSession = Depends(get_db), _admin=Depends(verify_admin)):
    """Delete completed/failed runs older than retention_days and all related data."""
    if retention_days < 1:
        raise HTTPException(status_code=400, detail="retention_days must be >= 1")
    from app.services.purge import purge_old_runs
    result = await purge_old_runs(db, retention_days=retention_days)
    return result


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
            await capture_test_run(run.id, run.selected_tests, session, notification_service)
        except Exception as e:
            # Mark run as failed if runner crashes
            run = await session.get(Run, run_id)
            if run and run.status not in ("completed", "failed", "cancelled"):
                run.status = "failed"
                await session.commit()
            import traceback
            traceback.print_exc()
        finally:
            # Release the resource lock (run-specific to avoid releasing a different run's lock
            # if the cancel endpoint already released ours and the next run acquired a new one)
            run = await session.get(Run, run_id)
            if run and run.resource_id:
                resource = await session.get(Resource, run.resource_id)
                if resource:
                    next_run_id = await ResourceQueueManager.release_resource(session, resource, run_id=run_id)
                    if next_run_id:
                        asyncio.create_task(schedule_run_task(next_run_id, notification_service))


@router.get("/clients", response_model=List[ClientOut])
async def list_clients(db: AsyncSession = Depends(get_db)) -> List[ClientOut]:
    result = await db.execute(select(Client).order_by(Client.created_at.desc()))
    return result.scalars().all()


@router.post("/clients/register", response_model=ClientOut)
async def register_client(payload: ClientCreate, db: AsyncSession = Depends(get_db)) -> ClientOut:
    # Return existing client if name already registered (case-insensitive)
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
    # Return the raw secret once so the client can store it; it's hashed in DB
    response = ClientOut.model_validate(client)
    response.client_key = client.client_key  # already set
    return response


@router.get("/tests/discover", response_model=List[TestItem])
async def discover_tests() -> List[TestItem]:
    tests: List[TestItem] = []
    backend_dir = Path(__file__).resolve().parents[2]
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
    return tests


@router.post("/resources", response_model=ResourceOut)
async def create_resource(name: str, description: str | None = None, db: AsyncSession = Depends(get_db)) -> ResourceOut:
    resource = Resource(name=name, description=description)
    db.add(resource)
    await db.commit()
    await db.refresh(resource)
    return resource


@router.get("/resources", response_model=List[ResourceOut])
async def list_resources(db: AsyncSession = Depends(get_db)) -> List[ResourceOut]:
    result = await db.execute(select(Resource))
    return result.scalars().all()


@router.post("/runs", response_model=RunOut, status_code=status.HTTP_201_CREATED)
async def create_run(payload: RunCreate, db: AsyncSession = Depends(get_db), request: Request = None) -> RunOut:
    notification_service = getattr(request.app.state, 'notification_service', None) if request else None

    statement = select(Client).where(Client.client_key == payload.client_key)
    result = await db.execute(statement)
    client = result.scalars().first()
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    run = Run(client_id=client.id, selected_tests=payload.selected_tests or [], status="pending")
    db.add(run)
    await db.commit()
    await db.refresh(run)

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
    return run


@router.get("/runs", response_model=List[RunOut])
async def list_runs(db: AsyncSession = Depends(get_db)) -> List[RunOut]:
    result = await db.execute(select(Run).order_by(Run.created_at.desc()))
    return result.scalars().all()


@router.get("/runs/{run_id}", response_model=RunOut)
async def get_run(run_id: int, db: AsyncSession = Depends(get_db)) -> RunOut:
    run = await db.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return run


@router.post("/runs/{run_id}/cancel")
async def cancel_run_endpoint(run_id: int, db: AsyncSession = Depends(get_db), request: Request = None):
    """Cancel / kill a running or queued job."""
    run = await db.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

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
async def cancel_run_file_endpoint(run_id: int, file_path: str, db: AsyncSession = Depends(get_db)):
    """Cancel a specific test file within a running job."""
    run = await db.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
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
async def get_run_active_files(run_id: int, db: AsyncSession = Depends(get_db)):
    """Return list of test file tags still running for a given run."""
    run = await db.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
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
async def get_run_logs(run_id: int, db: AsyncSession = Depends(get_db)) -> List[LogEntryOut]:
    result = await db.execute(select(LogEntry).where(LogEntry.run_id == run_id).order_by(LogEntry.timestamp))
    logs = result.scalars().all()
    return logs


@router.websocket("/runs/{run_id}/logs/ws")
async def websocket_logs(run_id: int, websocket: WebSocket):
    await websocket.accept()
    last_id = 0
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
async def list_reports(run_id: int) -> dict:
    """List available reports for a run."""
    run_dir = REPORTS_DIR / str(run_id)
    reports = {}
    if run_dir.exists():
        if (run_dir / "junit.xml").exists():
            reports["junit_xml"] = True
        if (run_dir / "report.html").exists():
            reports["html"] = True
        if (run_dir / "report.json").exists():
            reports["json"] = True
        if (run_dir / "coverage" / "coverage.json").exists():
            reports["coverage"] = True
        if (run_dir / "allure-results").exists() and any((run_dir / "allure-results").iterdir()):
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
    return {"run_id": run_id, "available": reports}


@router.get("/runs/{run_id}/reports/{report_type}")
async def get_report(run_id: int, report_type: str):
    """Download a specific report."""
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
async def get_test_report(run_id: int, nodeid: str):
    """Get per-test-case report data. Returns JSON, JUnit, coverage for a single test."""
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

    return result


@router.get("/runs/{run_id}/reports/files/{file_key}")
async def get_file_report_by_key(run_id: int, file_key: str):
    """Fetch a pre-generated per-file report by its safe key (e.g. tests__smoke__test_smoke)."""
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
    result["file_key"] = file_key
    return result


@router.get("/runs/{run_id}/reports/file/{file_path:path}")
async def get_file_report(run_id: int, file_path: str):
    """Report for all tests in a given file. Uses pre-generated per-file data when available."""
    run_dir = REPORTS_DIR / str(run_id)

    # Try pre-generated per-file report first
    file_key = file_path.replace("/", "__").replace("\\", "__").replace(".py", "")
    file_dir = run_dir / "files" / file_key
    summary_path = file_dir / "summary.json"
    if summary_path.exists():
        data = json.loads(summary_path.read_text(encoding="utf-8"))
        data["run_id"] = run_id
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
async def get_suite_report(run_id: int, suite_id: str):
    """Aggregate report for a test suite. Dynamically aggregated from per-test data."""
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
async def get_metrics(db: AsyncSession = Depends(get_db)) -> dict:
    """Get system metrics for dashboard."""
    from datetime import datetime, timedelta

    # Use SQL COUNT for efficiency instead of loading all rows
    total_runs = (await db.execute(select(func.count(Run.id)))).scalar_one()
    completed_runs = (await db.execute(select(func.count(Run.id)).where(Run.status == "completed"))).scalar_one()
    failed_runs = (await db.execute(select(func.count(Run.id)).where(Run.status == "failed"))).scalar_one()
    running_runs = (await db.execute(select(func.count(Run.id)).where(Run.status == "running"))).scalar_one()
    pending_runs = (await db.execute(select(func.count(Run.id)).where(Run.status == "pending"))).scalar_one()
    cancelled_runs = (await db.execute(select(func.count(Run.id)).where(Run.status == "cancelled"))).scalar_one()
    queued_runs = (await db.execute(select(func.count(Run.id)).where(Run.status == "queued"))).scalar_one()

    # Success rate (only count completed vs failed; exclude cancelled/pending/queued/running)
    decisive_runs = completed_runs + failed_runs
    success_rate = (completed_runs / decisive_runs * 100) if decisive_runs > 0 else 0

    # Recent runs (last 24 hours) - count only
    one_day_ago = datetime.now(timezone.utc) - timedelta(days=1)
    recent_runs = (await db.execute(
        select(func.count(Run.id)).where(Run.created_at >= one_day_ago)
    )).scalar_one()

    # Client activity (case-insensitive grouping)
    client_stats_result = await db.execute(
        select(func.min(Client.name), func.count(Run.id))
        .join(Run)
        .group_by(func.lower(Client.name))
    )
    client_stats = [{"name": row[0], "runs": row[1]} for row in client_stats_result]

    # Resource utilization
    resource_stats_result = await db.execute(
        select(Resource.name, func.count(Run.id)).join(Run, isouter=True).group_by(Resource.id)
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
        "client_stats": client_stats,
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
    })

    if smoke_tests:
        suites.append({
            "id": "smoke",
            "name": "Smoke Tests",
            "description": "Quick sanity checks to verify basic functionality is working",
            "tests": smoke_tests,
            "tags": ["fast", "ci"],
        })

    if unit_tests:
        suites.append({
            "id": "unit",
            "name": "Unit Tests",
            "description": "Isolated unit tests for individual functions and modules",
            "tests": unit_tests,
            "tags": ["fast", "isolated"],
        })

    if integration_tests:
        suites.append({
            "id": "integration",
            "name": "Integration Tests",
            "description": "Tests that verify multiple components working together",
            "tests": integration_tests,
            "tags": ["slow", "api"],
        })

    if quick_tests:
        suites.append({
            "id": "quick",
            "name": "Quick Validation",
            "description": "Fast-running tests for rapid feedback during development",
            "tests": quick_tests,
            "tags": ["fast", "dev"],
        })

    if security_tests:
        suites.append({
            "id": "security",
            "name": "Security Tests",
            "description": "Tests focused on security validations and vulnerability checks",
            "tests": security_tests,
            "tags": ["security", "ci"],
        })

    if data_tests:
        suites.append({
            "id": "data",
            "name": "Data Tests",
            "description": "Tests for data processing, validation, and integrity",
            "tests": data_tests,
            "tags": ["data"],
        })

    if math_tests or string_tests:
        suites.append({
            "id": "core-ops",
            "name": "Core Operations",
            "description": "Math and string operation tests covering core utility functions",
            "tests": math_tests + string_tests,
            "tags": ["fast", "core"],
        })

    if dummy_tests:
        suites.append({
            "id": "dummy",
            "name": "Sample / Dummy Tests",
            "description": "Example tests used for demonstration and template purposes",
            "tests": dummy_tests,
            "tags": ["sample"],
        })

    return suites


@router.get("/test-suites", response_model=list[TestSuite])
async def get_test_suites():
    """Return predefined test suites built from discovered tests."""
    return _build_test_suites()


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
        selected_tests=[command],
        status="pending",
        note=f"CLI: {command}",
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
            import traceback
            traceback.print_exc()
        finally:
            # Release the resource lock (mirrors schedule_run_task finally block)
            run = await session.get(Run, run_id)
            if run and run.resource_id:
                resource = await session.get(Resource, run.resource_id)
                if resource:
                    next_run_id = await ResourceQueueManager.release_resource(session, resource, run_id=run_id)
                    if next_run_id:
                        asyncio.create_task(schedule_run_task(next_run_id, notification_service))
