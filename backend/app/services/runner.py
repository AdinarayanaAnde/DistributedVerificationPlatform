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
from app.models import LogEntry, Run
from app.services.notifications import NotificationService

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[2]
TEST_ROOT = BASE_DIR / "tests"
REPORTS_DIR = BASE_DIR / "reports"

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
    current_test_per_group: dict[str, str | None] = {tag: None for _, _, _, tag, _ in processes}

    # Register processes for cancellation support
    _active_runs[run_id] = {tag: proc for proc, _, _, tag, _ in processes}

    def _identify_test(line: str) -> str | None:
        for nid in test_nodeids:
            if nid in line:
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

                mentioned_test = _identify_test(line)
                if mentioned_test:
                    current_test_per_group[group_tag] = mentioned_test
                    source = mentioned_test
                elif current_test_per_group.get(group_tag) and not (
                    line.startswith("===") or line.startswith("---")
                    or "passed" in line or "failed" in line or "error" in line
                ):
                    source = current_test_per_group[group_tag]
                else:
                    source = "session"
                    if line.startswith("===") or line.startswith("---"):
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

    # Skip expensive report finalization on cancel (avoids re-running tests for coverage/allure)
    if not cancelled:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, _finalize_reports, run_id, selected_tests, run_dir
        )

    # Refresh run from DB to pick up any status change by the cancel endpoint
    await db.refresh(run_statement)

    if cancelled:
        run_statement.status = "cancelled"
    elif run_statement.status != "cancelled":
        run_statement.status = "failed" if any_failed else "completed"
    run_statement.finished_at = datetime.now(timezone.utc)
    await db.commit()

    if notification_service:
        await notification_service.notify_run_completion(run_statement.client, run_statement)


def _is_pytest_command(args: list[str]) -> bool:
    """Check if the command list is a pytest invocation."""
    for a in args:
        if a in ("pytest", "-m") or "pytest" in a:
            continue
        if a == sys.executable:
            continue
        break
    # After normalisation the first real binary is pytest
    base = args[0] if args else ""
    return base == "pytest" or (
        len(args) >= 3 and args[0] == sys.executable and args[1] == "-m" and args[2] == "pytest"
    )


def _extract_test_targets_from_args(args: list[str]) -> list[str]:
    """Extract test file/nodeid targets from pytest CLI args (skip flags)."""
    targets: list[str] = []
    skip_next = False
    for a in args:
        if skip_next:
            skip_next = False
            continue
        if a in (sys.executable, "-m", "pytest"):
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

    # If command starts with 'pytest', prepend python -m
    if args and args[0] == "pytest":
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

                entry = LogEntry(
                    run_id=run_id,
                    client_id=run.client_id,
                    level=log_level,
                    source="cli",
                    message=line,
                )
                log_session.add(entry)

            if lines_batch:
                await log_session.commit()

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

    _active_runs.pop(run_id, None)

    # Generate reports for pytest commands
    if is_pytest:
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
        selected_tests = targets if targets else []

        # Run full report finalization (merge, JSON, coverage, allure, HTML)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, _finalize_reports, run_id, selected_tests, run_dir
        )

    cancelled = proc.returncode is not None and proc.returncode < 0
    if cancelled:
        run.status = "cancelled"
    else:
        run.status = "failed" if proc.returncode != 0 else "completed"
    run.finished_at = datetime.now(timezone.utc)
    await db.commit()

    if notification_service:
        await notification_service.notify_run_completion(run.client, run)


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


def _finalize_reports(run_id: int, selected_tests: list[str], run_dir: Path) -> None:
    """Merge per-file JUnit XMLs into run-level reports. NO re-execution of tests.

    This is called after all pytest processes have finished. Per-file JUnit XMLs
    were already generated during the test run, so we:
    1. Merge per-file JUnit XMLs into one run-level junit.xml
    2. Derive JSON report from the merged JUnit (no re-run)
    3. Run coverage ONCE, scoped to only the tested files
    4. Split per-test reports (for any files not already processed)
    5. Generate HTML report from merged data
    """
    per_file_dir = run_dir / "files"
    tests_dir = run_dir / "tests"
    tests_dir.mkdir(exist_ok=True)

    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    cwd = str(BASE_DIR)

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

    # ── 3. Coverage — scoped to only the test files that were selected ──
    test_args = selected_tests if selected_tests else [str(TEST_ROOT)]
    # Extract the actual source files being tested for --cov targets
    tested_file_paths = set()
    if selected_tests:
        for nodeid in selected_tests:
            fpath = nodeid.split("::")[0] if "::" in nodeid else nodeid
            tested_file_paths.add(fpath)
    cov_sources = list(tested_file_paths) if tested_file_paths else ["tests"]

    try:
        cov_dir = run_dir / "coverage"
        cov_dir.mkdir(exist_ok=True)
        cov_json = cov_dir / "coverage.json"
        cov_args = [sys.executable, "-m", "pytest", "-q", "--tb=no"]
        for src in cov_sources:
            cov_args.append(f"--cov={src}")
        cov_args.extend([
            f"--cov-report=json:{cov_json}",
            f"--cov-report=html:{cov_dir / 'htmlcov'}",
            *test_args,
        ])
        subprocess.run(cov_args, cwd=cwd, env=env, capture_output=True, timeout=600)
    except Exception as e:
        logger.error("Coverage report failed for run %d: %s", run_id, e)

    # ── 4. Allure - only if allure-pytest plugin is available ──
    allure_dir = run_dir / "allure-results"
    try:
        # Check if allure-pytest is importable before running
        check = subprocess.run(
            [sys.executable, "-c", "import allure"],
            capture_output=True, timeout=10
        )
        if check.returncode == 0:
            allure_dir.mkdir(exist_ok=True)
            allure_args = [
                sys.executable, "-m", "pytest", "--tb=short", "-q",
                f"--alluredir={allure_dir}", *test_args,
            ]
            subprocess.run(allure_args, cwd=cwd, env=env, capture_output=True, timeout=600)
    except Exception as e:
        logger.error("Allure report failed for run %d: %s", run_id, e)

    # ── 5. Generate per-test data from merged JUnit (fills any gaps) ──
    if junit_path.exists():
        try:
            _split_per_test_reports(junit_path, tests_dir, run_id)
        except Exception as e:
            logger.error("Per-test split failed for run %d: %s", run_id, e)

    # ── 6. Generate HTML report ──
    try:
        if junit_path.exists():
            _generate_html_report_from_data(run_id, run_dir, junit_path, allure_dir)
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


def _generate_html_report_from_data(run_id: int, run_dir: Path, junit_path: Path, allure_dir: Path) -> None:
    """Generate a standalone HTML report from JUnit XML data."""
    if not junit_path.exists():
        return

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
<html><head><meta charset="utf-8"><title>DVP Test Report - Run #{run_id}</title>
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
<div class="header"><h1>DVP Test Report</h1><p>Run #{run_id} &mdash; Generated {datetime.now(timezone.utc).isoformat()}</p></div>
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
