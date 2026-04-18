import asyncio
import json
import logging
import queue
import threading
import hashlib
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timezone
import os
import sys
import subprocess
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal
from app.models import Client, LogEntry, Run, SetupConfiguration, SetupStep
from app.services.notifications import NotificationService

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[2]
TEST_ROOT = BASE_DIR / "tests"
REPORTS_DIR = BASE_DIR.parent / "reports"  # Project root/reports

# Maximum time (seconds) a single pytest process is allowed to run
PROCESS_TIMEOUT = int(os.getenv("PYTEST_TIMEOUT", "3600"))  # 1 hour default

# Track active subprocess handles per run_id for cancellation support
# Maps run_id -> {file_tag: Popen}
_active_runs: dict[int, dict[str, subprocess.Popen]] = {}
# Track explicitly cancelled runs so capture_test_run can skip finalization
_cancelled_runs: set[int] = set()


def cancel_run(run_id: int) -> int:
    """Kill all subprocesses for a run. Returns the number of processes killed."""
    _cancelled_runs.add(run_id)
    procs = _active_runs.pop(run_id, {})
    killed = 0
    for proc in procs.values():
        if proc.poll() is None:
            proc.kill()
            killed += 1
    return killed


def cancel_run_file(run_id: int, file_tag: str) -> str:
    """Kill the subprocess for a specific file in a run.
    Returns: 'killed', 'already_finished', or 'not_found'.
    """
    run_procs = _active_runs.get(run_id, {})
    proc = run_procs.get(file_tag)
    if proc is None:
        return "not_found"
    if proc.poll() is not None:
        return "already_finished"
    proc.kill()
    run_procs.pop(file_tag, None)
    return "killed"


def get_active_files(run_id: int) -> list[str]:
    """Return list of file tags still running for a given run."""
    return [
        tag for tag, proc in _active_runs.get(run_id, {}).items()
        if proc.poll() is None
    ]


def _read_stream(pipe, level: str, q: queue.Queue, tag: str = ""):
    """Read a pipe line by line and put (level, line, tag) tuples on the queue."""
    try:
        for raw_line in iter(pipe.readline, b""):
            line = raw_line.decode("utf-8", errors="replace").rstrip()
            if line:
                q.put((level, line, tag))
    finally:
        pipe.close()


def _group_tests_by_file(selected_tests: list[str]) -> dict[str, list[str]]:
    """Group test nodeids by their file path."""
    groups: dict[str, list[str]] = defaultdict(list)
    for nodeid in selected_tests:
        file_path = nodeid.split("::")[0] if "::" in nodeid else nodeid
        groups[file_path].append(nodeid)
    return dict(groups)


def _safe_file_key(file_path: str) -> str:
    """Create a filesystem-safe key from a test file path."""
    return file_path.replace("/", "__").replace("\\", "__").replace(".py", "")


def _start_pytest_process(args: list[str], cwd: str, env: dict, line_queue: queue.Queue, tag: str, junit_path: Path | None = None):
    """Start a pytest subprocess and reader threads. Returns (proc, stdout_thread, stderr_thread).
    If junit_path is provided, adds --junitxml flag so results are captured during this run."""
    if junit_path:
        junit_path.parent.mkdir(parents=True, exist_ok=True)
        args = args + [f"--junitxml={junit_path}"]
    proc = subprocess.Popen(
        args,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    stdout_thread = threading.Thread(target=_read_stream, args=(proc.stdout, "INFO", line_queue, tag), daemon=True)
    stderr_thread = threading.Thread(target=_read_stream, args=(proc.stderr, "ERROR", line_queue, tag), daemon=True)
    stdout_thread.start()
    stderr_thread.start()
    return proc, stdout_thread, stderr_thread


# ── Setup Configuration Execution ──────────────────────────────────────────────

async def execute_setup_steps(run_id: int, config_id: int, db: AsyncSession) -> bool:
    """Execute setup configuration steps before a test run.

    Returns True if all steps passed (or were skipped), False if the run should be aborted.
    """
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    config = await db.get(SetupConfiguration, config_id, options=[selectinload(SetupConfiguration.steps)])
    if not config:
        async with AsyncSessionLocal() as log_session:
            log_session.add(LogEntry(
                run_id=run_id, level="ERROR", source="setup",
                message=f"Setup configuration #{config_id} not found — skipping setup",
            ))
            await log_session.commit()
        return True  # Don't block the run

    run = await db.get(Run, run_id)
    if run:
        run.setup_status = "running"
        await db.commit()

    async with AsyncSessionLocal() as log_session:
        log_session.add(LogEntry(
            run_id=run_id, level="INFO", source="setup",
            message=f"▶ Starting setup: {config.name} ({len(config.steps)} step(s))",
        ))
        await log_session.commit()

    cwd = str(BASE_DIR)
    all_passed = True

    for step in sorted(config.steps, key=lambda s: s.order):
        step_env = {**os.environ}
        if step.env_vars:
            step_env.update(step.env_vars)

        async with AsyncSessionLocal() as log_session:
            log_session.add(LogEntry(
                run_id=run_id, level="INFO", source="setup",
                message=f"  ⏳ Step {step.order + 1}: {step.name} — {step.command}",
            ))
            await log_session.commit()

        try:
            proc = await asyncio.create_subprocess_shell(
                step.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=step_env,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=step.timeout)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.communicate()
                async with AsyncSessionLocal() as log_session:
                    log_session.add(LogEntry(
                        run_id=run_id, level="ERROR", source="setup",
                        message=f"  ✗ Step {step.order + 1}: {step.name} — TIMEOUT after {step.timeout}s",
                    ))
                    await log_session.commit()
                if step.on_failure == "fail":
                    all_passed = False
                    break
                continue

            # Log stdout/stderr
            async with AsyncSessionLocal() as log_session:
                if stdout and stdout.strip():
                    for line in stdout.decode(errors="replace").strip().splitlines():
                        log_session.add(LogEntry(
                            run_id=run_id, level="INFO", source="setup",
                            message=f"    | {line}",
                        ))
                if stderr and stderr.strip():
                    for line in stderr.decode(errors="replace").strip().splitlines():
                        log_session.add(LogEntry(
                            run_id=run_id, level="ERROR", source="setup",
                            message=f"    | {line}",
                        ))
                await log_session.commit()

            if proc.returncode != 0:
                async with AsyncSessionLocal() as log_session:
                    log_session.add(LogEntry(
                        run_id=run_id, level="FAIL", source="setup",
                        message=f"  ✗ Step {step.order + 1}: {step.name} — FAILED (exit code {proc.returncode})",
                    ))
                    await log_session.commit()
                if step.on_failure == "fail":
                    all_passed = False
                    break
                elif step.on_failure == "skip":
                    continue
                # on_failure == "continue" — keep going
            else:
                async with AsyncSessionLocal() as log_session:
                    log_session.add(LogEntry(
                        run_id=run_id, level="PASS", source="setup",
                        message=f"  ✓ Step {step.order + 1}: {step.name} — PASSED",
                    ))
                    await log_session.commit()

        except Exception as e:
            async with AsyncSessionLocal() as log_session:
                log_session.add(LogEntry(
                    run_id=run_id, level="ERROR", source="setup",
                    message=f"  ✗ Step {step.order + 1}: {step.name} — ERROR: {e}",
                ))
                await log_session.commit()
            if step.on_failure == "fail":
                all_passed = False
                break

    # Update setup status
    run = await db.get(Run, run_id)
    if run:
        run.setup_status = "passed" if all_passed else "failed"
        await db.commit()

    async with AsyncSessionLocal() as log_session:
        status_icon = "✓" if all_passed else "✗"
        log_session.add(LogEntry(
            run_id=run_id, level="PASS" if all_passed else "FAIL", source="setup",
            message=f"{status_icon} Setup {'completed successfully' if all_passed else 'FAILED'}: {config.name}",
        ))
        await log_session.commit()

    return all_passed


# ── Teardown Configuration Execution ──────────────────────────────────────────

async def execute_teardown_steps(run_id: int, config_id: int, db: AsyncSession) -> bool:
    """Execute teardown configuration steps after a test run.

    Returns True if all steps passed (or were skipped), False if any step failed.
    Teardown always runs regardless of test outcome.
    """
    from sqlalchemy.orm import selectinload
    from app.models import TeardownConfiguration

    config = await db.get(TeardownConfiguration, config_id, options=[selectinload(TeardownConfiguration.steps)])
    if not config:
        async with AsyncSessionLocal() as log_session:
            log_session.add(LogEntry(
                run_id=run_id, level="ERROR", source="teardown",
                message=f"Teardown configuration #{config_id} not found — skipping teardown",
            ))
            await log_session.commit()
        return True

    run = await db.get(Run, run_id)
    if run:
        run.teardown_status = "running"
        await db.commit()

    async with AsyncSessionLocal() as log_session:
        log_session.add(LogEntry(
            run_id=run_id, level="INFO", source="teardown",
            message=f"▶ Starting teardown: {config.name} ({len(config.steps)} step(s))",
        ))
        await log_session.commit()

    cwd = str(BASE_DIR)
    all_passed = True

    for step in sorted(config.steps, key=lambda s: s.order):
        step_env = {**os.environ}
        if step.env_vars:
            step_env.update(step.env_vars)

        async with AsyncSessionLocal() as log_session:
            log_session.add(LogEntry(
                run_id=run_id, level="INFO", source="teardown",
                message=f"  ⏳ Step {step.order + 1}: {step.name} — {step.command}",
            ))
            await log_session.commit()

        try:
            proc = await asyncio.create_subprocess_shell(
                step.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=step_env,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=step.timeout)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.communicate()
                async with AsyncSessionLocal() as log_session:
                    log_session.add(LogEntry(
                        run_id=run_id, level="ERROR", source="teardown",
                        message=f"  ✗ Step {step.order + 1}: {step.name} — TIMEOUT after {step.timeout}s",
                    ))
                    await log_session.commit()
                if step.on_failure == "fail":
                    all_passed = False
                    break
                continue

            async with AsyncSessionLocal() as log_session:
                if stdout and stdout.strip():
                    for line in stdout.decode(errors="replace").strip().splitlines():
                        log_session.add(LogEntry(
                            run_id=run_id, level="INFO", source="teardown",
                            message=f"    | {line}",
                        ))
                if stderr and stderr.strip():
                    for line in stderr.decode(errors="replace").strip().splitlines():
                        log_session.add(LogEntry(
                            run_id=run_id, level="ERROR", source="teardown",
                            message=f"    | {line}",
                        ))
                await log_session.commit()

            if proc.returncode != 0:
                async with AsyncSessionLocal() as log_session:
                    log_session.add(LogEntry(
                        run_id=run_id, level="FAIL", source="teardown",
                        message=f"  ✗ Step {step.order + 1}: {step.name} — FAILED (exit code {proc.returncode})",
                    ))
                    await log_session.commit()
                if step.on_failure == "fail":
                    all_passed = False
                    break
                elif step.on_failure == "skip":
                    continue
            else:
                async with AsyncSessionLocal() as log_session:
                    log_session.add(LogEntry(
                        run_id=run_id, level="PASS", source="teardown",
                        message=f"  ✓ Step {step.order + 1}: {step.name} — PASSED",
                    ))
                    await log_session.commit()

        except Exception as e:
            async with AsyncSessionLocal() as log_session:
                log_session.add(LogEntry(
                    run_id=run_id, level="ERROR", source="teardown",
                    message=f"  ✗ Step {step.order + 1}: {step.name} — ERROR: {e}",
                ))
                await log_session.commit()
            if step.on_failure == "fail":
                all_passed = False
                break

    run = await db.get(Run, run_id)
    if run:
        run.teardown_status = "passed" if all_passed else "failed"
        await db.commit()

    async with AsyncSessionLocal() as log_session:
        status_icon = "✓" if all_passed else "✗"
        log_session.add(LogEntry(
            run_id=run_id, level="PASS" if all_passed else "FAIL", source="teardown",
            message=f"{status_icon} Teardown {'completed successfully' if all_passed else 'FAILED'}: {config.name}",
        ))
        await log_session.commit()

    return all_passed


async def capture_test_run(run_id: int, selected_tests: list[str], db: AsyncSession, notification_service: NotificationService | None = None) -> None:
    run_statement = await db.get(Run, run_id)
    if run_statement is None:
        return

    if run_statement.started_at is None:
        run_statement.started_at = datetime.now(timezone.utc)
        run_statement.status = "running"
        await db.commit()

    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    cwd = str(BASE_DIR)

    # Prepare report directories
    run_dir = REPORTS_DIR / str(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    per_file_dir = run_dir / "files"
    per_file_dir.mkdir(exist_ok=True)
    tests_dir = run_dir / "tests"
    tests_dir.mkdir(exist_ok=True)

    # Shared queue for all processes
    line_queue: queue.Queue = queue.Queue()

    # Group tests by file and launch one pytest process per file (parallel)
    file_groups = _group_tests_by_file(selected_tests) if selected_tests else {}

    # Validate that test files actually exist before launching pytest
    missing_files = []
    for file_path in list(file_groups.keys()):
        full_path = Path(cwd) / file_path
        if not full_path.exists():
            missing_files.extend(file_groups.pop(file_path))
    if missing_files:
        async with AsyncSessionLocal() as log_session:
            for mf in missing_files:
                log_session.add(LogEntry(
                    run_id=run_id, client_id=run_statement.client_id,
                    level="WARN", source=mf,
                    message=f"Skipped {mf} — file no longer exists",
                ))
            await log_session.commit()

    # Each process gets its own JUnit XML output path
    processes: list[tuple[subprocess.Popen, threading.Thread, threading.Thread, str, Path | None]] = []

    if not selected_tests:
        junit_path = per_file_dir / "all" / "junit.xml"
        args = [sys.executable, "-m", "pytest", "-v", "-s", "--tb=short", str(TEST_ROOT)]
        proc, t1, t2 = _start_pytest_process(args, cwd, env, line_queue, "all", junit_path)
        processes.append((proc, t1, t2, "all", junit_path))
    elif len(file_groups) == 1:
        file_path = list(file_groups.keys())[0]
        tests = file_groups[file_path]
        file_key = _safe_file_key(file_path)
        junit_path = per_file_dir / file_key / "junit.xml"
        args = [sys.executable, "-m", "pytest", "-v", "-s", "--tb=short", *tests]
        proc, t1, t2 = _start_pytest_process(args, cwd, env, line_queue, file_path, junit_path)
        processes.append((proc, t1, t2, file_path, junit_path))
    else:
        for file_path, tests in file_groups.items():
            file_key = _safe_file_key(file_path)
            junit_path = per_file_dir / file_key / "junit.xml"
            args = [sys.executable, "-m", "pytest", "-v", "-s", "--tb=short", *tests]
            proc, t1, t2 = _start_pytest_process(args, cwd, env, line_queue, file_path, junit_path)
            processes.append((proc, t1, t2, file_path, junit_path))

    # Build a set of test nodeids for tagging log lines to specific tests
    test_nodeids = set(selected_tests) if selected_tests else set()
    # Build a reverse index from short function name → full nodeid for failure section matching
    _func_to_nodeid: dict[str, str] = {}
    for nid in test_nodeids:
        parts = nid.split("::")
        if len(parts) >= 2:
            _func_to_nodeid[parts[-1]] = nid
    current_test_per_group: dict[str, str | None] = {tag: None for _, _, _, tag, _ in processes}
    # Track whether we're inside a FAILURES/ERRORS section (between === headers)
    _in_failure_section: dict[str, bool] = {tag: False for _, _, _, tag, _ in processes}

    # Register processes for cancellation support
    _active_runs[run_id] = {tag: proc for proc, _, _, tag, _ in processes}

    # Regex to detect pytest failure/error section headers like "_____ test_name _____"
    import re
    _section_header_re = re.compile(r"^_+ (.+?) _+$")

    def _identify_test(line: str, group_tag: str) -> str | None:
        # Direct nodeid match
        for nid in test_nodeids:
            if nid in line:
                return nid
        # Check for pytest failure section header: "_____ test_func _____"
        m = _section_header_re.match(line.strip())
        if m:
            header_name = m.group(1)
            # Try matching against known test function names
            if header_name in _func_to_nodeid:
                _in_failure_section[group_tag] = True
                return _func_to_nodeid[header_name]
            # Try partial match (class::method format in header)
            for nid in test_nodeids:
                if header_name in nid:
                    _in_failure_section[group_tag] = True
                    return nid
        return None

    # Track which file-processes have already had per-file reports generated
    completed_files: set[str] = set()
    # Track start time for timeout enforcement
    run_start_time = asyncio.get_event_loop().time()

    # Poll the shared queue and write to DB in real-time
    async with AsyncSessionLocal() as log_session:
        while True:
            lines_batch: list[tuple[str, str, str]] = []
            try:
                while True:
                    lines_batch.append(line_queue.get_nowait())
            except queue.Empty:
                pass

            for base_level, line, group_tag in lines_batch:
                log_level = base_level
                if "PASSED" in line:
                    log_level = "PASS"
                elif "FAILED" in line or "ERROR" in line:
                    log_level = "FAIL"
                elif line.startswith("E ") or "AssertionError" in line:
                    log_level = "FAIL"

                mentioned_test = _identify_test(line, group_tag)
                if mentioned_test:
                    current_test_per_group[group_tag] = mentioned_test
                    source = mentioned_test
                elif current_test_per_group.get(group_tag) and not (
                    line.startswith("===")
                    or (line.startswith("---") and " passed" in line)
                ):
                    # Keep attributing to the current test for:
                    #  - traceback lines, E lines, assertion lines
                    #  - lines in FAILURES/ERRORS sections
                    # Only reset on "===" separators or final summary lines like "--- 2 passed ---"
                    source = current_test_per_group[group_tag]
                else:
                    source = "session"
                    if line.startswith("==="):
                        # Check if entering or leaving a failures section
                        if "FAILURES" in line or "ERRORS" in line:
                            _in_failure_section[group_tag] = True
                        else:
                            _in_failure_section[group_tag] = False
                        current_test_per_group[group_tag] = None

                entry = LogEntry(
                    run_id=run_id,
                    client_id=run_statement.client_id,
                    level=log_level,
                    source=source,
                    message=line,
                )
                log_session.add(entry)

            if lines_batch:
                await log_session.commit()

            # Generate per-file reports incrementally as each process completes
            for proc, pt1, pt2, tag, file_junit in processes:
                if tag not in completed_files and proc.poll() is not None:
                    completed_files.add(tag)
                    pt1.join(timeout=2)
                    pt2.join(timeout=2)
                    # Generate per-file per-test reports from this file's JUnit XML
                    if file_junit and file_junit.exists():
                        try:
                            _split_per_test_reports(
                                file_junit, tests_dir, run_id
                            )
                            # Also generate a per-file summary JSON
                            _generate_file_summary(
                                file_junit,
                                file_junit.parent,
                                run_id,
                                tag,
                            )
                        except Exception as e:
                            logger.warning("Per-file report for %s failed: %s", tag, e)

            # Check if ALL processes finished and queue is drained
            all_done = all(proc.poll() is not None for proc, _, _, _, _ in processes)
            if all_done and line_queue.empty() and not lines_batch:
                break

            # Enforce timeout: kill any processes running too long
            elapsed = asyncio.get_event_loop().time() - run_start_time
            if elapsed > PROCESS_TIMEOUT:
                for proc, _, _, tag, _ in processes:
                    if proc.poll() is None:
                        proc.kill()
                        logger.warning("Process for %s in run %d killed (timeout %ds)", tag, run_id, PROCESS_TIMEOUT)
                break

            await asyncio.sleep(0.3)

    # Join remaining threads
    for _, t1, t2, tag, _ in processes:
        if tag not in completed_files:
            t1.join(timeout=2)
            t2.join(timeout=2)

    # Drain any lines the reader threads produced after the main loop exited
    remaining: list[tuple[str, str, str]] = []
    try:
        while True:
            remaining.append(line_queue.get_nowait())
    except queue.Empty:
        pass
    if remaining:
        async with AsyncSessionLocal() as drain_session:
            for base_level, line, group_tag in remaining:
                log_level = base_level
                if "PASSED" in line:
                    log_level = "PASS"
                elif "FAILED" in line or "ERROR" in line:
                    log_level = "FAIL"
                drain_session.add(LogEntry(
                    run_id=run_id,
                    client_id=run_statement.client_id,
                    level=log_level,
                    source="session",
                    message=line,
                ))
            await drain_session.commit()

    # Unregister from active runs
    _active_runs.pop(run_id, None)

    # Detect if cancelled via cancel_run() or negative exit code (Unix)
    cancelled = run_id in _cancelled_runs or any(
        proc.returncode is not None and proc.returncode < 0
        for proc, _, _, _, _ in processes
    )
    _cancelled_runs.discard(run_id)

    # Determine overall status
    any_failed = any(proc.returncode != 0 for proc, _, _, _, _ in processes)

    # Refresh run from DB to pick up any status change by the cancel endpoint
    await db.refresh(run_statement)

    if cancelled:
        run_statement.status = "cancelled"
    elif run_statement.status != "cancelled":
        run_statement.status = "failed" if any_failed else "completed"
    run_statement.finished_at = datetime.now(timezone.utc)
    # Commit status BEFORE finalization so the UI sees completion immediately
    await db.commit()

    # Run report finalization after committing status (tests are NOT re-executed here)
    if not cancelled:
        run_display = run_statement.run_name or f"#{run_id}"
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, _finalize_reports, run_id, selected_tests, run_dir, run_display
        )

    if notification_service:
        # Explicitly load the client to avoid SQLAlchemy lazy-load in async context
        client = await db.get(Client, run_statement.client_id)
        if client:
            await notification_service.notify_run_completion(client, run_statement)


def _looks_like_python(arg: str) -> bool:
    """Check if an argument looks like a python executable path."""
    if arg == sys.executable:
        return True
    base = os.path.basename(arg)
    # Handle cases where shlex strips backslashes on Windows
    if not base or base == arg:
        # Try extracting basename manually for mangled paths
        for sep in ("/", "\\"):
            if sep in arg:
                base = arg.rsplit(sep, 1)[-1]
                break
        # If still the full string, check if it ends with a python-like name
        if base == arg and "python" in arg.lower():
            return True
    return base.lower().startswith("python")


def _is_pytest_command(args: list[str]) -> bool:
    """Check if the command list is a pytest invocation."""
    # Normalise: collect the meaningful tokens, skipping python/executable and -m
    for a in args:
        if a in ("pytest", "-m") or "pytest" in a:
            continue
        if _looks_like_python(a):
            continue
        break
    # After normalisation the first real binary is pytest
    base = args[0] if args else ""
    is_exe = _looks_like_python(base)
    return base == "pytest" or (
        len(args) >= 3 and is_exe and args[1] == "-m" and args[2] == "pytest"
    )


def _extract_test_targets_from_args(args: list[str]) -> list[str]:
    """Extract test file/nodeid targets from pytest CLI args (skip flags)."""
    targets: list[str] = []
    skip_next = False
    for a in args:
        if skip_next:
            skip_next = False
            continue
        if _looks_like_python(a):
            continue
        if a in ("-m", "pytest"):
            continue
        # Skip flags that take a value
        if a in ("-k", "-m", "-p", "--rootdir", "--override-ini",
                 "--co", "-c", "--tb", "--junitxml", "--cov",
                 "--cov-report", "--alluredir", "-n", "--dist"):
            skip_next = True
            continue
        if a.startswith("-"):
            # flag like -v, -s, --tb=short, --junitxml=...
            if "=" not in a:
                continue
            else:
                continue  # --flag=value
        # Positional argument = test target
        targets.append(a)
    return targets


async def capture_cli_run(run_id: int, command: str, db: AsyncSession, notification_service=None) -> None:
    """Execute a CLI command and capture output as log entries.
    If the command is a pytest invocation, also generates full reports
    (JUnit XML, JSON, HTML, Coverage, Allure)."""
    import shlex

    run = await db.get(Run, run_id)
    if run is None:
        return

    if run.started_at is None:
        run.started_at = datetime.now(timezone.utc)
        run.status = "running"
        await db.commit()

    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    cwd = str(BASE_DIR)


    args = shlex.split(command)

    # If command starts with 'pytest', prepend python -m and ensure '-v' for verbose output
    if args and args[0] == "pytest":
        # Add '-v' if not present for granular progress
        if '-v' not in args:
            args.append('-v')
        # Add '--tb=short' for concise tracebacks on failures (industry standard)
        if not any(a.startswith('--tb') for a in args):
            args.append('--tb=short')
        args = [sys.executable, "-m"] + args

    is_pytest = _is_pytest_command(args)

    # Prepare report directories and JUnit path for pytest commands
    run_dir = REPORTS_DIR / str(run_id)
    junit_path: Path | None = None
    if is_pytest:
        run_dir.mkdir(parents=True, exist_ok=True)
        per_file_dir = run_dir / "files"
        per_file_dir.mkdir(exist_ok=True)
        tests_dir = run_dir / "tests"
        tests_dir.mkdir(exist_ok=True)

        # Determine file key from the command targets
        targets = _extract_test_targets_from_args(args)
        file_key = _safe_file_key(targets[0]) if targets else "cli"
        junit_path = per_file_dir / file_key / "junit.xml"

    line_queue: queue.Queue = queue.Queue()
    proc, t1, t2 = _start_pytest_process(args, cwd, env, line_queue, "cli", junit_path)

    # Register for cancellation support
    _active_runs[run_id] = {"cli": proc}

    run_start_time = asyncio.get_event_loop().time()

    # Regex to detect pytest test nodeids from verbose output
    # Matches lines like: tests/foo.py::test_bar PASSED
    import re
    _nodeid_re = re.compile(r"^(\S+\.py::\S+)\s+(PASSED|FAILED|ERROR|SKIPPED)")
    _section_header_re_cli = re.compile(r"^_+ (.+?) _+$")
    current_test: str | None = None
    discovered_nodeids: list[str] = []  # Track all test nodeids for progress reporting
    # Build reverse index from function name → nodeid for failure section matching
    _cli_func_to_nodeid: dict[str, str] = {}

    def _detect_source(line: str) -> str:
        """Detect the test nodeid from a pytest output line."""
        nonlocal current_test
        m = _nodeid_re.match(line)
        if m:
            current_test = m.group(1)
            if current_test not in discovered_nodeids:
                discovered_nodeids.append(current_test)
                # Update function→nodeid index
                parts = current_test.split("::")
                if len(parts) >= 2:
                    _cli_func_to_nodeid[parts[-1]] = current_test
            return current_test
        # Check for failure section header: "_____ test_func _____"
        sm = _section_header_re_cli.match(line.strip())
        if sm:
            header_name = sm.group(1)
            if header_name in _cli_func_to_nodeid:
                current_test = _cli_func_to_nodeid[header_name]
                return current_test
            # Partial match
            for nid in discovered_nodeids:
                if header_name in nid:
                    current_test = nid
                    return current_test
        # Keep attributing to current test unless we hit a section separator
        if current_test and not (
            line.startswith("===")
            or (line.startswith("---") and " passed" in line)
        ):
            return current_test
        if line.startswith("==="):
            current_test = None
        return "cli"

    async with AsyncSessionLocal() as log_session:
        while True:
            lines_batch: list[tuple[str, str, str]] = []
            try:
                while True:
                    lines_batch.append(line_queue.get_nowait())
            except queue.Empty:
                pass

            for base_level, line, _ in lines_batch:
                log_level = base_level
                if "PASSED" in line:
                    log_level = "PASS"
                elif "FAILED" in line or "ERROR" in line:
                    log_level = "FAIL"

                source = _detect_source(line) if is_pytest else "cli"

                entry = LogEntry(
                    run_id=run_id,
                    client_id=run.client_id,
                    level=log_level,
                    source=source,
                    message=line,
                )
                log_session.add(entry)

            if lines_batch:
                await log_session.commit()

            # Update run.selected_tests with newly discovered nodeids for real-time progress
            if is_pytest and discovered_nodeids and len(discovered_nodeids) != len(run.selected_tests or []):
                run.selected_tests = list(discovered_nodeids)
                await db.commit()

            if proc.poll() is not None and line_queue.empty() and not lines_batch:
                break

            # Enforce timeout
            elapsed = asyncio.get_event_loop().time() - run_start_time
            if elapsed > PROCESS_TIMEOUT:
                if proc.poll() is None:
                    proc.kill()
                    logger.warning("CLI process for run %d killed (timeout %ds)", run_id, PROCESS_TIMEOUT)
                break

            await asyncio.sleep(0.3)

    t1.join(timeout=2)
    t2.join(timeout=2)

    # Drain any lines the reader threads produced after the main loop exited
    cli_remaining: list[tuple[str, str, str]] = []
    try:
        while True:
            cli_remaining.append(line_queue.get_nowait())
    except queue.Empty:
        pass
    if cli_remaining:
        async with AsyncSessionLocal() as drain_session:
            for base_level, line, _ in cli_remaining:
                log_level = base_level
                if "PASSED" in line:
                    log_level = "PASS"
                elif "FAILED" in line or "ERROR" in line:
                    log_level = "FAIL"
                source = _detect_source(line) if is_pytest else "cli"
                drain_session.add(LogEntry(
                    run_id=run_id,
                    client_id=run.client_id,
                    level=log_level,
                    source=source,
                    message=line,
                ))
            await drain_session.commit()

    _active_runs.pop(run_id, None)

    # Final update of selected_tests with all discovered nodeids
    if is_pytest and discovered_nodeids:
        run.selected_tests = list(discovered_nodeids)

    # Commit status BEFORE finalization so the UI sees completion immediately
    cancelled = proc.returncode is not None and proc.returncode < 0
    if cancelled:
        run.status = "cancelled"
    else:
        run.status = "failed" if proc.returncode != 0 else "completed"
    run.finished_at = datetime.now(timezone.utc)
    await db.commit()

    # Generate reports for pytest commands after committing status (tests are NOT re-executed)
    if is_pytest and not cancelled:
        # Generate per-file summary from the JUnit XML
        if junit_path and junit_path.exists():
            try:
                tests_dir = run_dir / "tests"
                _split_per_test_reports(junit_path, tests_dir, run_id)
                _generate_file_summary(junit_path, junit_path.parent, run_id, "cli")
            except Exception as e:
                logger.warning("Per-file report for CLI run %d failed: %s", run_id, e)

        # Extract selected_tests from command for finalization
        targets = _extract_test_targets_from_args(args)
        selected_tests_for_report = targets if targets else []

        # Run full report finalization (merge, JSON, HTML — no test re-execution)
        run_display = run.run_name or f"#{run_id}"
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, _finalize_reports, run_id, selected_tests_for_report, run_dir, run_display
        )

    # Trigger async report generation if run completed successfully
    if run.status == "completed":
        from app.services.report_generator import ReportGenerator
        asyncio.create_task(ReportGenerator.generate_all_reports(run_id))

    if notification_service:
        # Explicitly load the client to avoid SQLAlchemy lazy-load in async context
        client = await db.get(Client, run.client_id)
        if client:
            await notification_service.notify_run_completion(client, run)


def _generate_file_summary(junit_path: Path, output_dir: Path, run_id: int, file_tag: str) -> None:
    """Generate a summary JSON for a single test file from its JUnit XML."""
    tree_xml = ET.parse(str(junit_path))
    root = tree_xml.getroot()

    cases = []
    for suite in root.iter("testsuite"):
        for tc in suite.findall("testcase"):
            status = "passed"
            message = ""
            failure = tc.find("failure")
            error = tc.find("error")
            skipped_el = tc.find("skipped")
            if failure is not None:
                status = "failed"
                message = failure.get("message", "")
            elif error is not None:
                status = "error"
                message = error.get("message", "")
            elif skipped_el is not None:
                status = "skipped"
                message = skipped_el.get("message", "")
            cases.append({
                "name": tc.get("name", ""),
                "classname": tc.get("classname", ""),
                "time": float(tc.get("time", 0)),
                "status": status,
                "message": message,
            })

    total = len(cases)
    passed = sum(1 for c in cases if c["status"] == "passed")
    failed = sum(1 for c in cases if c["status"] == "failed")
    errors = sum(1 for c in cases if c["status"] == "error")
    skipped = sum(1 for c in cases if c["status"] == "skipped")
    total_time = sum(c["time"] for c in cases)

    summary = {
        "run_id": run_id,
        "file": file_tag,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "skipped": skipped,
            "total_time": round(total_time, 3),
            "pass_rate": round(passed / total * 100, 1) if total > 0 else 0,
        },
        "tests": cases,
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )


def _finalize_reports(run_id: int, selected_tests: list[str], run_dir: Path, run_display: str = "") -> None:
    """Merge per-file JUnit XMLs into run-level reports without re-executing tests.

    Steps:
    1. Merge per-file JUnit XMLs into one run-level junit.xml
    2. Derive JSON report from the merged JUnit
    3. Split per-test reports (fills any gaps not already covered)
    4. Generate HTML report from merged data
    """
    run_display = run_display or f"#{run_id}"
    per_file_dir = run_dir / "files"
    tests_dir = run_dir / "tests"
    tests_dir.mkdir(exist_ok=True)

    # ── 1. Merge per-file JUnit XMLs ──
    junit_path = run_dir / "junit.xml"
    merged_root = ET.Element("testsuites")
    per_file_junits = list(per_file_dir.rglob("junit.xml"))

    for fj in per_file_junits:
        try:
            tree = ET.parse(str(fj))
            file_root = tree.getroot()
            # JUnit XML can be <testsuites> or <testsuite>
            if file_root.tag == "testsuites":
                for suite in file_root.findall("testsuite"):
                    merged_root.append(suite)
            elif file_root.tag == "testsuite":
                merged_root.append(file_root)
        except Exception as e:
            logger.error("Failed to merge %s: %s", fj, e)

    ET.ElementTree(merged_root).write(str(junit_path), encoding="unicode")

    # ── 2. Derive JSON report from merged JUnit (no re-run) ──
    json_report_path = run_dir / "report.json"
    if junit_path.exists():
        try:
            _json_from_junit(junit_path, json_report_path, run_id)
        except Exception as e:
            logger.error("JSON report derivation failed for run %d: %s", run_id, e)

    # ── 3. Generate per-test data from merged JUnit (fills any gaps) ──
    if junit_path.exists():
        try:
            _split_per_test_reports(junit_path, tests_dir, run_id)
        except Exception as e:
            logger.error("Per-test split failed for run %d: %s", run_id, e)

    # ── 4. Generate HTML report ──
    allure_dir = run_dir / "allure-results"
    try:
        if junit_path.exists():
            _generate_html_report_from_data(run_id, run_dir, junit_path, allure_dir, run_display)
    except Exception as e:
        logger.error("HTML report failed for run %d: %s", run_id, e)


def _json_from_junit(junit_path: Path, json_path: Path, run_id: int) -> None:
    """Parse JUnit XML into a JSON report."""
    tree_xml = ET.parse(str(junit_path))
    root = tree_xml.getroot()
    suites = []
    for suite in root.iter("testsuite"):
        cases = []
        for tc in suite.findall("testcase"):
            case = {
                "name": tc.get("name", ""),
                "classname": tc.get("classname", ""),
                "file": tc.get("file", tc.get("classname", "").replace(".", "/") + ".py"),
                "time": float(tc.get("time", 0)),
                "status": "passed",
            }
            failure = tc.find("failure")
            error = tc.find("error")
            skipped = tc.find("skipped")
            if failure is not None:
                case["status"] = "failed"
                case["message"] = failure.get("message", "")
                case["details"] = (failure.text or "")[:2000]
            elif error is not None:
                case["status"] = "error"
                case["message"] = error.get("message", "")
                case["details"] = (error.text or "")[:2000]
            elif skipped is not None:
                case["status"] = "skipped"
                case["message"] = skipped.get("message", "")
            cases.append(case)
        suites.append({
            "name": suite.get("name", ""),
            "tests": int(suite.get("tests", 0)),
            "errors": int(suite.get("errors", 0)),
            "failures": int(suite.get("failures", 0)),
            "skipped": int(suite.get("skipped", 0)),
            "time": float(suite.get("time", 0)),
            "testcases": cases,
        })
    report = {
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "suites": suites,
        "summary": {
            "total": sum(s["tests"] for s in suites),
            "passed": sum(1 for s in suites for c in s["testcases"] if c["status"] == "passed"),
            "failed": sum(1 for s in suites for c in s["testcases"] if c["status"] == "failed"),
            "errors": sum(1 for s in suites for c in s["testcases"] if c["status"] == "error"),
            "skipped": sum(1 for s in suites for c in s["testcases"] if c["status"] == "skipped"),
            "total_time": sum(s["time"] for s in suites),
        },
    }
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")


def _split_per_test_reports(junit_path: Path, tests_dir: Path, run_id: int) -> None:
    """Split JUnit XML into per-test-case JSON files under tests/<safe_name>/."""
    tree_xml = ET.parse(str(junit_path))
    root = tree_xml.getroot()

    for suite in root.iter("testsuite"):
        for tc in suite.findall("testcase"):
            classname = tc.get("classname", "")
            name = tc.get("name", "")
            nodeid = f"{classname.replace('.', '/')}::{name}" if classname else name
            # Create a safe directory name from the nodeid
            safe_name = hashlib.md5(nodeid.encode()).hexdigest()[:12]
            test_dir = tests_dir / safe_name
            test_dir.mkdir(exist_ok=True)

            status = "passed"
            message = ""
            details = ""
            failure = tc.find("failure")
            error = tc.find("error")
            skipped = tc.find("skipped")
            if failure is not None:
                status = "failed"
                message = failure.get("message", "")
                details = failure.text or ""
            elif error is not None:
                status = "error"
                message = error.get("message", "")
                details = error.text or ""
            elif skipped is not None:
                status = "skipped"
                message = skipped.get("message", "")

            system_out = tc.find("system-out")
            system_err = tc.find("system-err")

            test_data = {
                "run_id": run_id,
                "nodeid": nodeid,
                "classname": classname,
                "name": name,
                "file": classname.replace(".", "/").rsplit("/", 1)[0] + ".py" if "." in classname else classname,
                "time": float(tc.get("time", 0)),
                "status": status,
                "message": message,
                "details": details[:2000],
                "stdout": (system_out.text or "")[:5000] if system_out is not None else "",
                "stderr": (system_err.text or "")[:5000] if system_err is not None else "",
            }

            # Write per-test JSON
            (test_dir / "result.json").write_text(
                json.dumps(test_data, indent=2), encoding="utf-8"
            )

            # Write per-test JUnit XML snippet
            ts = ET.Element("testsuite", name=classname, tests="1",
                             failures="1" if status == "failed" else "0",
                             errors="1" if status == "error" else "0",
                             skipped="1" if status == "skipped" else "0",
                             time=tc.get("time", "0"))
            ts.append(tc)
            ET.ElementTree(ts).write(str(test_dir / "junit.xml"), encoding="unicode")

    # Also write a lookup index: nodeid -> directory hash
    index = {}
    for suite in root.iter("testsuite"):
        for tc in suite.findall("testcase"):
            classname = tc.get("classname", "")
            name = tc.get("name", "")
            nodeid = f"{classname.replace('.', '/')}::{name}" if classname else name
            safe_name = hashlib.md5(nodeid.encode()).hexdigest()[:12]
            index[nodeid] = safe_name
    (tests_dir / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")


def _generate_html_report_from_data(run_id: int, run_dir: Path, junit_path: Path, allure_dir: Path, run_display: str = "") -> None:
    """Generate a standalone HTML report from JUnit XML data."""
    if not junit_path.exists():
        return
    run_display = run_display or f"#{run_id}"

    import html as html_mod

    tree_xml = ET.parse(str(junit_path))
    root = tree_xml.getroot()

    total = passed = failed = errors = skipped = 0
    total_time = 0.0
    rows = ""

    for suite in root.iter("testsuite"):
        for tc in suite.findall("testcase"):
            total += 1
            name = tc.get("name", "")
            classname = tc.get("classname", "")
            time_val = float(tc.get("time", 0))
            total_time += time_val
            status = "passed"
            msg = ""

            failure_el = tc.find("failure")
            error_el = tc.find("error")
            skipped_el = tc.find("skipped")
            if failure_el is not None:
                status = "failed"
                failed += 1
                msg = failure_el.get("message", "")
            elif error_el is not None:
                status = "error"
                errors += 1
                msg = error_el.get("message", "")
            elif skipped_el is not None:
                status = "skipped"
                skipped += 1
                msg = skipped_el.get("message", "")
            else:
                passed += 1

            icon = {"passed": "\u2705", "failed": "\u274C", "error": "\u26A0\uFE0F", "skipped": "\u23ED\uFE0F"}.get(status, "\u2753")
            cls = {"passed": "pass", "failed": "fail", "error": "error", "skipped": "skip"}.get(status, "")
            safe_msg = html_mod.escape(msg)[:200] if msg else ""
            rows += f'<tr class="{cls}"><td>{icon} {html_mod.escape(classname)}</td><td>{html_mod.escape(name)}</td><td class="status">{status.upper()}</td><td>{time_val:.3f}s</td><td class="msg">{safe_msg}</td></tr>\n'

    pass_rate = round(passed / total * 100, 1) if total > 0 else 0

    allure_note = ""
    if allure_dir.exists() and any(allure_dir.iterdir()):
        allure_note = '<div class="allure-note">Allure results available in <code>allure-results/</code>. Run <code>allure serve</code> to view.</div>'

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>DVP Test Report - {run_display}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
:root{{--bg:#0f0f1a;--bg-card:#1e1e2e;--border:#363653;--text:#e2e0f0;--text-muted:#9892b0;--text-label:#6e6888;--accent:#7c6ff7;--bg-th:#232336;--row-fail:rgba(247,108,108,0.05);--row-error:rgba(247,168,76,0.05);--code-bg:#232336;--green:#50d890;--red:#f76c6c;--orange:#f7a84c;--yellow:#f7c948;--blue:#56b6f7}}
:root.light{{--bg:#f5f5fa;--bg-card:#ffffff;--border:#d8d8e8;--text:#1e1e2e;--text-muted:#6e6888;--text-label:#9892b0;--accent:#5b52cc;--bg-th:#eeeef5;--row-fail:rgba(247,108,108,0.08);--row-error:rgba(247,168,76,0.08);--code-bg:#eeeef5;--green:#1a9a5a;--red:#d04040;--orange:#c87830;--yellow:#b09020;--blue:#2878c8}}
body{{font-family:'Segoe UI',system-ui,sans-serif;background:var(--bg);color:var(--text);padding:32px}}
.header{{text-align:center;margin-bottom:32px}}
.header h1{{font-size:24px;color:var(--accent);margin-bottom:8px}}
.header p{{color:var(--text-muted);font-size:13px}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-bottom:32px}}
.card{{background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:16px;text-align:center}}
.card .val{{font-size:28px;font-weight:700;font-family:'Cascadia Code',monospace}}
.card .lbl{{font-size:11px;color:var(--text-label);text-transform:uppercase;margin-top:4px}}
.pass .val{{color:var(--green)}} .fail .val{{color:var(--red)}} .error .val{{color:var(--orange)}} .skip .val{{color:var(--yellow)}} .rate .val{{color:var(--accent)}} .time .val{{color:var(--blue)}}
table{{width:100%;border-collapse:collapse;background:var(--bg-card);border:1px solid var(--border);border-radius:10px;overflow:hidden}}
th{{background:var(--bg-th);font-size:11px;text-transform:uppercase;color:var(--text-label);padding:12px 14px;text-align:left}}
td{{padding:10px 14px;font-size:12px;border-top:1px solid var(--border);font-family:'Cascadia Code',monospace;color:var(--text)}}
tr.fail td{{background:var(--row-fail)}} tr.error td{{background:var(--row-error)}} tr.skip td{{opacity:0.6}}
.status{{font-weight:600}} .msg{{color:var(--text-muted);font-size:11px;max-width:300px;overflow:hidden;text-overflow:ellipsis}}
.allure-note{{background:var(--bg-card);border:1px solid var(--border);border-radius:8px;padding:12px 16px;margin-bottom:24px;font-size:12px;color:var(--text-muted)}}
.allure-note code{{color:var(--accent);background:var(--code-bg);padding:2px 6px;border-radius:4px}}
</style>
<script>
(function(){{var p=new URLSearchParams(window.location.search).get('theme');if(p==='light')document.documentElement.classList.add('light');}})();
</script></head><body>
<div class="header"><h1>DVP Test Report</h1><p>{run_display} &mdash; Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}</p></div>
{allure_note}
<div class="cards">
<div class="card"><div class="val">{total}</div><div class="lbl">Total Tests</div></div>
<div class="card pass"><div class="val">{passed}</div><div class="lbl">Passed</div></div>
<div class="card fail"><div class="val">{failed}</div><div class="lbl">Failed</div></div>
<div class="card error"><div class="val">{errors}</div><div class="lbl">Errors</div></div>
<div class="card skip"><div class="val">{skipped}</div><div class="lbl">Skipped</div></div>
<div class="card rate"><div class="val">{pass_rate}%</div><div class="lbl">Pass Rate</div></div>
<div class="card time"><div class="val">{total_time:.1f}s</div><div class="lbl">Duration</div></div>
</div>
<table><thead><tr><th>Class</th><th>Test</th><th>Status</th><th>Time</th><th>Message</th></tr></thead>
<tbody>{rows}</tbody></table>
</body></html>"""
    (run_dir / "report.html").write_text(html, encoding="utf-8")
