"""Server-side report generation from test results and logs."""

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal
from app.models import ReportData, LogEntry, Run

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[2]
REPORTS_DIR = BASE_DIR.parent / "reports"


class ReportGenerator:
    """Async server-side report generation from test results."""

    @staticmethod
    async def generate_all_reports(run_id: int) -> dict:
        """Generate all report types for a completed run."""
        try:
            async with AsyncSessionLocal() as session:
                run = await session.get(Run, run_id)
                if not run or run.status != "completed":
                    logger.warning(f"Run {run_id} not in completed state for report generation")
                    return {"status": "error", "reason": "Run not completed"}

                # Collect logs
                result = await session.execute(
                    select(LogEntry).where(LogEntry.run_id == run_id).order_by(LogEntry.timestamp)
                )
                logs = result.scalars().all()

                # Read JUnit XML if available
                junit_data = await ReportGenerator._read_junit_xml(run_id)

                # Generate reports in parallel
                html_report = await ReportGenerator.generate_html_report(run_id, run, logs, junit_data)
                json_report = await ReportGenerator.generate_json_report(run_id, run, logs, junit_data)
                coverage_report = await ReportGenerator.generate_coverage_report(run_id)
                allure_report = await ReportGenerator.generate_allure_report(run_id)

                # Store all reports in database
                reports_to_store = [
                    ("html", html_report),
                    ("json", json_report),
                ]

                if coverage_report:
                    reports_to_store.append(("coverage", coverage_report))
                if allure_report:
                    reports_to_store.append(("allure", allure_report))

                for report_type, content in reports_to_store:
                    if content is None:
                        continue

                    # Check if report already exists
                    existing = await session.execute(
                        select(ReportData).where(
                            (ReportData.run_id == run_id) & (ReportData.report_type == report_type)
                        )
                    )
                    existing_report = existing.scalars().first()

                    if existing_report:
                        existing_report.content = content
                        existing_report.content_size = len(content)
                        existing_report.generated_at = datetime.now(timezone.utc)
                    else:
                        report = ReportData(
                            run_id=run_id,
                            report_type=report_type,
                            content=content,
                            content_size=len(content),
                        )
                        session.add(report)

                await session.commit()
                logger.info(f"Generated {len(reports_to_store)} reports for run {run_id}")
                return {"status": "success", "reports_generated": len(reports_to_store)}

        except Exception as e:
            logger.error(f"Failed to generate reports for run {run_id}: {e}")
            return {"status": "error", "reason": str(e)}

    @staticmethod
    async def _read_junit_xml(run_id: int) -> dict:
        """Parse JUnit XML results if available."""
        run_dir = REPORTS_DIR / str(run_id)

        junit_file = run_dir / "junit.xml"
        if not junit_file.exists():
            junit_file = run_dir / "all" / "junit.xml"
        if not junit_file.exists():
            # Fallback: merge per-file JUnit XMLs from files/ subdirectory
            files_dir = run_dir / "files"
            if files_dir.exists():
                per_file_junits = list(files_dir.rglob("junit.xml"))
                if per_file_junits:
                    merged_root = ET.Element("testsuites")
                    for fj in per_file_junits:
                        try:
                            tree = ET.parse(str(fj))
                            file_root = tree.getroot()
                            if file_root.tag == "testsuites":
                                for suite in file_root.findall("testsuite"):
                                    merged_root.append(suite)
                            elif file_root.tag == "testsuite":
                                merged_root.append(file_root)
                        except Exception:
                            pass
                    # Write merged file so future calls are fast
                    junit_file = run_dir / "junit.xml"
                    run_dir.mkdir(parents=True, exist_ok=True)
                    ET.ElementTree(merged_root).write(str(junit_file), encoding="unicode")
                    logger.info(f"Merged {len(per_file_junits)} per-file JUnit XMLs for run {run_id}")
        if not junit_file.exists():
            logger.warning(f"No JUnit XML found for run {run_id}")
            return {"tests": [], "stats": {"total": 0, "passed": 0, "failed": 0, "errors": 0}}

        try:
            tree = ET.parse(str(junit_file))
            root = tree.getroot()

            # Extract test cases and compute stats by iterating all testcases
            # (handles both <testsuite> and <testsuites> root elements)
            tests = []
            total = 0
            passed = 0
            failures = 0
            errors = 0

            for testcase in root.iter("testcase"):
                total += 1
                test_info = {
                    "classname": testcase.get("classname", ""),
                    "name": testcase.get("name", ""),
                    "time": float(testcase.get("time", 0)),
                    "status": "passed",
                    "message": "",
                }

                # Check for failures
                failure = testcase.find("failure")
                if failure is not None:
                    test_info["status"] = "failed"
                    test_info["message"] = failure.get("message", "") or failure.text or ""
                    failures += 1
                # Check for errors
                elif testcase.find("error") is not None:
                    error = testcase.find("error")
                    test_info["status"] = "error"
                    test_info["message"] = error.get("message", "") or error.text or ""
                    errors += 1
                else:
                    passed += 1

                tests.append(test_info)

            return {
                "tests": tests,
                "stats": {"total": total, "passed": passed, "failed": failures, "errors": errors},
            }

        except Exception as e:
            logger.error(f"Failed to parse JUnit XML for run {run_id}: {e}")
            return {"tests": [], "stats": {"total": 0, "passed": 0, "failed": 0, "errors": 0}}

    @staticmethod
    async def generate_html_report(run_id: int, run: Run, logs: list, junit_data: dict) -> str:
        """Generate HTML report from test results and logs."""
        import html as html_mod
        run_display = run.run_name or f"#{run_id}"

        stats = junit_data.get("stats", {})
        tests = junit_data.get("tests", [])

        total = stats.get("total", 0)
        passed = stats.get("passed", 0)
        failed = stats.get("failed", 0)
        errors = stats.get("errors", 0)
        total_time = sum(t.get("time", 0) for t in tests)
        pass_rate = round(passed / total * 100, 1) if total > 0 else 0

        # Generate test rows
        rows = ""
        for test in tests:
            status = test["status"]
            icon = {"passed": "\u2705", "failed": "\u274C", "error": "\u26A0\uFE0F", "skipped": "\u23ED\uFE0F"}.get(status, "\u2753")
            cls = {"passed": "pass", "failed": "fail", "error": "error", "skipped": "skip"}.get(status, "")
            safe_msg = html_mod.escape(test.get("message", ""))[:200]
            rows += f'<tr class="{cls}"><td>{icon} {html_mod.escape(test["classname"])}</td><td>{html_mod.escape(test["name"])}</td><td class="status">{status.upper()}</td><td>{test["time"]:.3f}s</td><td class="msg">{safe_msg}</td></tr>\n'

        # Generate log entries
        log_rows = ""
        for log in logs[-30:]:
            safe_msg = html_mod.escape(log.message[:200])
            log_rows += f'<div class="log-entry log-{log.level}">[{log.level}] {html_mod.escape(log.source)}: {safe_msg}</div>\n'

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
.logs{{margin-top:32px}}
.logs h2{{font-size:16px;margin-bottom:12px;color:var(--accent)}}
.log-entry{{padding:8px 12px;margin:4px 0;border-radius:6px;font-family:'Cascadia Code',monospace;font-size:11px;background:var(--bg-card);border:1px solid var(--border);color:var(--text-muted)}}
.log-PASS{{color:var(--green);border-color:var(--green)}}
.log-FAIL{{color:var(--red);border-color:var(--red)}}
.log-ERROR{{color:var(--orange);border-color:var(--orange)}}
</style>
<script>
(function(){{var p=new URLSearchParams(window.location.search).get('theme');if(p==='light')document.documentElement.classList.add('light');}})();
</script></head><body>
<div class="header"><h1>DVP Test Report</h1><p>{run_display} &mdash; Status: <strong>{run.status}</strong> &mdash; Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}</p></div>
<div class="cards">
<div class="card"><div class="val">{total}</div><div class="lbl">Total Tests</div></div>
<div class="card pass"><div class="val">{passed}</div><div class="lbl">Passed</div></div>
<div class="card fail"><div class="val">{failed}</div><div class="lbl">Failed</div></div>
<div class="card error"><div class="val">{errors}</div><div class="lbl">Errors</div></div>
<div class="card rate"><div class="val">{pass_rate}%</div><div class="lbl">Pass Rate</div></div>
<div class="card time"><div class="val">{total_time:.1f}s</div><div class="lbl">Duration</div></div>
</div>
<table><thead><tr><th>Class</th><th>Test</th><th>Status</th><th>Time</th><th>Message</th></tr></thead>
<tbody>{rows}</tbody></table>
<div class="logs">
<h2>Recent Logs</h2>
{log_rows}
</div>
</body></html>"""

        return html

    @staticmethod
    async def generate_json_report(run_id: int, run: Run, logs: list, junit_data: dict) -> str:
        """Generate JSON report with complete data."""
        report = {
            "run_id": run_id,
            "run_name": run.run_name,
            "status": run.status,
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "statistics": junit_data.get("stats", {}),
            "tests": junit_data.get("tests", []),
            "logs": [
                {
                    "timestamp": log.timestamp.isoformat(),
                    "level": log.level,
                    "source": log.source,
                    "message": log.message,
                }
                for log in logs
            ],
        }

        return json.dumps(report, indent=2)

    @staticmethod
    async def generate_coverage_report(run_id: int) -> str:
        """Generate or read coverage report from disk."""
        run_dir = REPORTS_DIR / str(run_id)
        coverage_file = run_dir / "coverage" / "coverage.json"

        if coverage_file.exists():
            try:
                return coverage_file.read_text()
            except Exception as e:
                logger.warning(f"Failed to read coverage report for run {run_id}: {e}")
                return None

        return None

    @staticmethod
    async def generate_allure_report(run_id: int) -> str:
        """Generate or read Allure report results."""
        run_dir = REPORTS_DIR / str(run_id)
        allure_index = run_dir / "allure-report" / "index.html"

        if allure_index.exists():
            try:
                return allure_index.read_text()
            except Exception as e:
                logger.warning(f"Failed to read Allure report for run {run_id}: {e}")
                return None

        return None
