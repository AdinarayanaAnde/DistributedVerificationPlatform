#!/usr/bin/env python3
"""DVP CLI — command-line interface for the Distributed Verification Platform."""

import json
import os
import sys
import time

import click
import httpx
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box

console = Console()
err_console = Console(stderr=True)

DEFAULT_BASE = "http://localhost:8000"


def _base_url() -> str:
    return os.getenv("DVP_URL", DEFAULT_BASE).rstrip("/")


def _client() -> httpx.Client:
    return httpx.Client(base_url=_base_url() + "/api", timeout=30, verify=False)


def _root_client() -> httpx.Client:
    return httpx.Client(base_url=_base_url(), timeout=30, verify=False)


def _admin_headers() -> dict:
    key = os.getenv("ADMIN_API_KEY", "")
    return {"x-admin-key": key} if key else {}


def _abort(msg: str):
    err_console.print(f"[red]Error:[/red] {msg}")
    raise SystemExit(1)


# ── Root Group ──────────────────────────────────────────────────────────────


@click.group()
@click.option("--url", envvar="DVP_URL", default=DEFAULT_BASE, help="API base URL")
@click.pass_context
def cli(ctx, url):
    """DVP — Distributed Verification Platform CLI."""
    ctx.ensure_object(dict)
    os.environ["DVP_URL"] = url


# ── Health ──────────────────────────────────────────────────────────────────


@cli.command()
def health():
    """Check server health."""
    with _root_client() as c:
        r = c.get("/health")
    if r.status_code == 200:
        data = r.json()
        console.print(f"[green]✓[/green] Server healthy — status: {data.get('status', 'ok')}")
    else:
        _abort(f"Server returned {r.status_code}")


# ── Clients ─────────────────────────────────────────────────────────────────


@cli.group()
def clients():
    """Manage clients."""


@clients.command("register")
@click.argument("name")
@click.option("--email", default=None, help="Notification email")
@click.option("--webhook", default=None, help="Webhook URL")
def client_register(name, email, webhook):
    """Register a new client."""
    payload = {"name": name}
    if email:
        payload["email"] = email
    if webhook:
        payload["webhook_url"] = webhook
    with _client() as c:
        r = c.post("/clients/register", json=payload)
    if r.status_code == 200:
        data = r.json()
        table = Table(title="Client Registered", box=box.ROUNDED)
        table.add_column("Field", style="cyan")
        table.add_column("Value")
        table.add_row("ID", str(data["id"]))
        table.add_row("Name", data["name"])
        table.add_row("Client Key", data["client_key"])
        if data.get("email"):
            table.add_row("Email", data["email"])
        console.print(table)
    else:
        _abort(r.text)


@clients.command("list")
def client_list():
    """List registered clients."""
    with _client() as c:
        r = c.get("/clients")
    if r.status_code != 200:
        _abort(r.text)
    data = r.json()
    if not data:
        console.print("[dim]No clients registered.[/dim]")
        return
    table = Table(title="Clients", box=box.ROUNDED)
    table.add_column("ID", style="cyan", justify="right")
    table.add_column("Name", style="bold")
    table.add_column("Key")
    table.add_column("Email")
    table.add_column("Created")
    for cl in data:
        table.add_row(
            str(cl["id"]),
            cl["name"],
            cl["client_key"][:12] + "…",
            cl.get("email") or "—",
            cl["created_at"][:19],
        )
    console.print(table)


# ── Resources ───────────────────────────────────────────────────────────────


@cli.group()
def resources():
    """Manage resources."""


@resources.command("create")
@click.argument("name")
@click.option("--desc", default=None, help="Description")
def resource_create(name, desc):
    """Create a resource."""
    payload = {"name": name}
    if desc:
        payload["description"] = desc
    with _client() as c:
        r = c.post("/resources", json=payload)
    if r.status_code == 200:
        data = r.json()
        console.print(f"[green]✓[/green] Resource created: [bold]{data['name']}[/bold] (id={data['id']})")
    else:
        _abort(r.text)


@resources.command("list")
def resource_list():
    """List resources."""
    with _client() as c:
        r = c.get("/resources")
    if r.status_code != 200:
        _abort(r.text)
    data = r.json()
    if not data:
        console.print("[dim]No resources.[/dim]")
        return
    table = Table(title="Resources", box=box.ROUNDED)
    table.add_column("ID", style="cyan", justify="right")
    table.add_column("Name", style="bold")
    table.add_column("Description")
    table.add_column("Active")
    for res in data:
        table.add_row(
            str(res["id"]),
            res["name"],
            res.get("description") or "—",
            "✓" if res["active"] else "✗",
        )
    console.print(table)


# ── Tests & Suites ──────────────────────────────────────────────────────────


@cli.group()
def tests():
    """Discover tests and suites."""


@tests.command("discover")
@click.option("--filter", "pattern", default=None, help="Filter tests by substring")
def test_discover(pattern):
    """List all discoverable tests."""
    with _client() as c:
        r = c.get("/tests/discover")
    if r.status_code != 200:
        _abort(r.text)
    items = r.json()
    if pattern:
        items = [t for t in items if pattern.lower() in t["nodeid"].lower()]
    table = Table(title=f"Tests ({len(items)})", box=box.ROUNDED)
    table.add_column("#", style="dim", justify="right")
    table.add_column("Node ID", style="bold")
    table.add_column("Path")
    table.add_column("Function")
    for i, t in enumerate(items, 1):
        table.add_row(str(i), t["nodeid"], t["path"], t["function"])
    console.print(table)


@tests.command("suites")
def test_suites():
    """List available test suites."""
    with _client() as c:
        r = c.get("/test-suites")
    if r.status_code != 200:
        _abort(r.text)
    suites = r.json()
    table = Table(title="Test Suites", box=box.ROUNDED)
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="bold")
    table.add_column("Description")
    table.add_column("Tests", justify="right")
    table.add_column("Tags")
    for s in suites:
        table.add_row(
            s["id"],
            s["name"],
            s["description"],
            str(len(s["tests"])),
            ", ".join(s.get("tags", [])) or "—",
        )
    console.print(table)


# ── Runs ────────────────────────────────────────────────────────────────────


@cli.group()
def runs():
    """Manage test runs."""


@runs.command("create")
@click.option("--client-key", required=True, help="Client key from registration")
@click.option("--suite", default=None, help="Suite ID (e.g. smoke, unit, all)")
@click.option("--tests", "test_list", default=None, help="Comma-separated test nodeids")
@click.option("--resource", default=None, help="Resource name to lock")
@click.option("--wait", "wait_flag", is_flag=True, help="Wait for run to finish")
def run_create(client_key, suite, test_list, resource, wait_flag):
    """Create a new test run."""
    selected = []
    if suite:
        with _client() as c:
            r = c.get("/test-suites")
        if r.status_code != 200:
            _abort(f"Failed to fetch suites: {r.text}")
        suites = {s["id"]: s["tests"] for s in r.json()}
        if suite not in suites:
            _abort(f"Unknown suite '{suite}'. Available: {', '.join(suites)}")
        selected = suites[suite]
    elif test_list:
        selected = [t.strip() for t in test_list.split(",")]
    else:
        _abort("Provide --suite or --tests")

    payload = {"client_key": client_key, "selected_tests": selected}
    if resource:
        payload["resource_name"] = resource

    with _client() as c:
        r = c.post("/runs", json=payload)
    if r.status_code != 200:
        _abort(r.text)
    data = r.json()
    run_id = data["id"]
    console.print(f"[green]✓[/green] Run [bold]#{run_id}[/bold] created — status: {data['status']}")

    if wait_flag:
        _wait_for_run(run_id)


def _wait_for_run(run_id: int):
    """Poll until a run reaches a terminal state."""
    console.print(f"[dim]Waiting for run #{run_id} to complete…[/dim]")
    terminal_states = {"completed", "failed", "cancelled"}
    with _client() as c:
        while True:
            r = c.get(f"/runs/{run_id}")
            if r.status_code != 200:
                _abort(r.text)
            data = r.json()
            status = data["status"]
            if status in terminal_states:
                color = "green" if status == "completed" else "red"
                console.print(f"[{color}]Run #{run_id} → {status}[/{color}]")
                _print_run_summary(run_id, c)
                return
            time.sleep(2)


def _print_run_summary(run_id: int, c: httpx.Client):
    """Print a brief report summary after a run finishes."""
    r = c.get(f"/runs/{run_id}/reports")
    if r.status_code != 200:
        return
    data = r.json()
    available = data.get("available", [])
    if available:
        console.print(f"  Reports available: {', '.join(available)}")


@runs.command("list")
@click.option("--limit", default=20, help="Number of recent runs")
def run_list(limit):
    """List recent runs."""
    with _client() as c:
        r = c.get("/runs")
    if r.status_code != 200:
        _abort(r.text)
    data = r.json()[:limit]
    if not data:
        console.print("[dim]No runs found.[/dim]")
        return
    table = Table(title=f"Recent Runs (last {limit})", box=box.ROUNDED)
    table.add_column("ID", style="cyan", justify="right")
    table.add_column("Status", justify="center")
    table.add_column("Tests", justify="right")
    table.add_column("Created")
    table.add_column("Finished")
    for run in data:
        status = run["status"]
        color = {"completed": "green", "failed": "red", "running": "yellow",
                 "queued": "blue", "cancelled": "dim"}.get(status, "white")
        table.add_row(
            str(run["id"]),
            f"[{color}]{status}[/{color}]",
            str(len(run.get("selected_tests", []))),
            run["created_at"][:19],
            (run.get("finished_at") or "—")[:19],
        )
    console.print(table)


@runs.command("show")
@click.argument("run_id", type=int)
def run_show(run_id):
    """Show details for a specific run."""
    with _client() as c:
        r = c.get(f"/runs/{run_id}")
    if r.status_code == 404:
        _abort(f"Run #{run_id} not found")
    if r.status_code != 200:
        _abort(r.text)
    data = r.json()
    status = data["status"]
    color = {"completed": "green", "failed": "red", "running": "yellow",
             "queued": "blue", "cancelled": "dim"}.get(status, "white")
    table = Table(title=f"Run #{run_id}", box=box.ROUNDED)
    table.add_column("Field", style="cyan")
    table.add_column("Value")
    table.add_row("Status", f"[{color}]{status}[/{color}]")
    table.add_row("Client ID", str(data["client_id"]))
    table.add_row("Resource ID", str(data.get("resource_id") or "—"))
    table.add_row("Tests", str(len(data["selected_tests"])))
    table.add_row("Note", data.get("note") or "—")
    table.add_row("Created", data["created_at"][:19])
    table.add_row("Started", (data.get("started_at") or "—")[:19])
    table.add_row("Finished", (data.get("finished_at") or "—")[:19])
    console.print(table)

    # Show test list
    if data["selected_tests"]:
        test_table = Table(title="Selected Tests", box=box.SIMPLE)
        test_table.add_column("#", style="dim", justify="right")
        test_table.add_column("Node ID")
        for i, t in enumerate(data["selected_tests"], 1):
            test_table.add_row(str(i), t)
        console.print(test_table)


@runs.command("logs")
@click.argument("run_id", type=int)
@click.option("--level", default=None, help="Filter by level (INFO, PASS, FAIL, ERROR)")
@click.option("--tail", default=None, type=int, help="Show last N entries")
def run_logs(run_id, level, tail):
    """Show logs for a run."""
    with _client() as c:
        r = c.get(f"/runs/{run_id}/logs")
    if r.status_code == 404:
        _abort(f"Run #{run_id} not found")
    if r.status_code != 200:
        _abort(r.text)
    logs = r.json()
    if level:
        logs = [l for l in logs if l["level"].upper() == level.upper()]
    if tail:
        logs = logs[-tail:]
    if not logs:
        console.print("[dim]No log entries.[/dim]")
        return
    for entry in logs:
        lvl = entry["level"]
        color = {"PASS": "green", "FAIL": "red", "ERROR": "red",
                 "INFO": "blue", "WARNING": "yellow"}.get(lvl, "white")
        ts = entry["timestamp"][:19]
        src = entry.get("source", "")
        msg = entry["message"]
        console.print(f"[dim]{ts}[/dim] [{color}]{lvl:7s}[/{color}] [dim]{src}[/dim] {msg}")


@runs.command("cancel")
@click.argument("run_id", type=int)
def run_cancel(run_id):
    """Cancel a running test run."""
    with _client() as c:
        r = c.post(f"/runs/{run_id}/cancel")
    if r.status_code == 200:
        console.print(f"[yellow]✓[/yellow] Run #{run_id} cancelled.")
    else:
        _abort(r.text)


# ── Reports ─────────────────────────────────────────────────────────────────


@cli.group()
def reports():
    """View and download test reports."""


@reports.command("list")
@click.argument("run_id", type=int)
def report_list(run_id):
    """List available reports for a run."""
    with _client() as c:
        r = c.get(f"/runs/{run_id}/reports")
    if r.status_code == 404:
        _abort(f"Run #{run_id} not found or no reports")
    if r.status_code != 200:
        _abort(r.text)
    data = r.json()
    available = data.get("available", [])
    per_file = data.get("per_file", [])
    per_test = data.get("per_test", [])

    table = Table(title=f"Reports for Run #{run_id}", box=box.ROUNDED)
    table.add_column("Type", style="cyan")
    table.add_column("Available", justify="center")
    for rtype in ["junit_xml", "html", "json", "coverage", "allure"]:
        avail = "✓" if rtype in available else "—"
        color = "green" if rtype in available else "dim"
        table.add_row(rtype, f"[{color}]{avail}[/{color}]")
    console.print(table)

    if per_file:
        console.print(f"\n[bold]Per-file reports:[/bold] {len(per_file)} files")
        for f in per_file[:15]:
            console.print(f"  • {f}")
        if len(per_file) > 15:
            console.print(f"  [dim]… and {len(per_file) - 15} more[/dim]")

    if per_test:
        console.print(f"\n[bold]Per-test reports:[/bold] {len(per_test)} tests")


@reports.command("summary")
@click.argument("run_id", type=int)
def report_summary(run_id):
    """Show test result summary (from JSON report)."""
    with _client() as c:
        r = c.get(f"/runs/{run_id}/reports/json")
    if r.status_code == 404:
        _abort(f"No JSON report for run #{run_id}")
    if r.status_code != 200:
        _abort(r.text)
    data = r.json()
    summary = data.get("summary", {})

    # Summary panel
    passed = summary.get("passed", 0)
    failed = summary.get("failed", 0)
    errors = summary.get("error", 0)
    skipped = summary.get("skipped", 0)
    total = summary.get("total", passed + failed + errors + skipped)
    duration = summary.get("duration", 0)

    color = "green" if failed == 0 and errors == 0 else "red"
    panel_text = Text()
    panel_text.append(f"Total: {total}  ", style="bold")
    panel_text.append(f"Passed: {passed}  ", style="green")
    panel_text.append(f"Failed: {failed}  ", style="red" if failed else "dim")
    panel_text.append(f"Errors: {errors}  ", style="red" if errors else "dim")
    panel_text.append(f"Skipped: {skipped}  ", style="yellow" if skipped else "dim")
    panel_text.append(f"Duration: {duration:.2f}s", style="dim")
    console.print(Panel(panel_text, title=f"Run #{run_id} Summary", border_style=color))

    # Per-suite breakdown
    suites = data.get("suites", [])
    if suites:
        table = Table(title="Test Suites", box=box.ROUNDED)
        table.add_column("Suite", style="bold")
        table.add_column("Tests", justify="right")
        table.add_column("Pass", style="green", justify="right")
        table.add_column("Fail", style="red", justify="right")
        table.add_column("Error", justify="right")
        table.add_column("Time", justify="right")
        for s in suites:
            table.add_row(
                s.get("name", "?"),
                str(s.get("tests", 0)),
                str(s.get("passed", 0)),
                str(s.get("failed", 0)),
                str(s.get("errors", 0)),
                f"{s.get('time', 0):.2f}s",
            )
        console.print(table)

    # Failed tests detail
    testcases = data.get("testcases", [])
    failures = [tc for tc in testcases if tc.get("status") in ("FAILED", "ERROR")]
    if failures:
        console.print(f"\n[red bold]Failed/Error Tests ({len(failures)}):[/red bold]")
        for tc in failures:
            console.print(f"  [red]✗[/red] {tc.get('classname', '')}.{tc.get('name', '')}")
            msg = tc.get("message", "")
            if msg:
                console.print(f"    [dim]{msg[:200]}[/dim]")


@reports.command("junit")
@click.argument("run_id", type=int)
@click.option("-o", "--output", default=None, help="Save to file")
def report_junit(run_id, output):
    """Download JUnit XML report."""
    with _client() as c:
        r = c.get(f"/runs/{run_id}/reports/junit_xml")
    if r.status_code == 404:
        _abort(f"No JUnit XML report for run #{run_id}")
    if r.status_code != 200:
        _abort(r.text)
    if output:
        with open(output, "w", encoding="utf-8") as f:
            f.write(r.text)
        console.print(f"[green]✓[/green] Saved to {output}")
    else:
        console.print(r.text)


@reports.command("html")
@click.argument("run_id", type=int)
@click.option("-o", "--output", default=None, help="Save to file (default: report_{run_id}.html)")
def report_html(run_id, output):
    """Download HTML report."""
    with _client() as c:
        r = c.get(f"/runs/{run_id}/reports/html")
    if r.status_code == 404:
        _abort(f"No HTML report for run #{run_id}")
    if r.status_code != 200:
        _abort(r.text)
    dest = output or f"report_{run_id}.html"
    with open(dest, "w", encoding="utf-8") as f:
        f.write(r.text)
    console.print(f"[green]✓[/green] Saved to {dest}")


@reports.command("json")
@click.argument("run_id", type=int)
@click.option("-o", "--output", default=None, help="Save to file")
@click.option("--pretty", is_flag=True, help="Pretty-print JSON")
def report_json(run_id, output, pretty):
    """Download JSON report."""
    with _client() as c:
        r = c.get(f"/runs/{run_id}/reports/json")
    if r.status_code == 404:
        _abort(f"No JSON report for run #{run_id}")
    if r.status_code != 200:
        _abort(r.text)
    text = json.dumps(r.json(), indent=2) if pretty else r.text
    if output:
        with open(output, "w", encoding="utf-8") as f:
            f.write(text)
        console.print(f"[green]✓[/green] Saved to {output}")
    else:
        console.print(text)


@reports.command("file")
@click.argument("run_id", type=int)
@click.argument("file_path")
def report_file(run_id, file_path):
    """Show report for a specific test file."""
    with _client() as c:
        r = c.get(f"/runs/{run_id}/reports/file/{file_path}")
    if r.status_code == 404:
        _abort(f"No report for file '{file_path}' in run #{run_id}")
    if r.status_code != 200:
        _abort(r.text)
    data = r.json()
    summary = data.get("summary", data)

    passed = summary.get("passed", 0)
    failed = summary.get("failed", 0)
    errors = summary.get("errors", summary.get("error", 0))
    total = summary.get("total", passed + failed + errors)

    color = "green" if failed == 0 and errors == 0 else "red"
    console.print(Panel(
        f"[bold]{file_path}[/bold]\n"
        f"Total: {total}  [green]Pass: {passed}[/green]  "
        f"[red]Fail: {failed}[/red]  Error: {errors}",
        title=f"Run #{run_id} — File Report",
        border_style=color,
    ))

    # Per-test results if available
    test_results = summary.get("tests", data.get("tests", []))
    if test_results:
        table = Table(box=box.SIMPLE)
        table.add_column("Status", justify="center")
        table.add_column("Test")
        table.add_column("Time", justify="right")
        table.add_column("Message")
        for t in test_results:
            st = t.get("status", "?")
            sc = "green" if st == "PASSED" else "red" if st in ("FAILED", "ERROR") else "yellow"
            table.add_row(
                f"[{sc}]{st}[/{sc}]",
                t.get("name", t.get("nodeid", "?")),
                f"{t.get('time', 0):.3f}s" if t.get("time") else "—",
                (t.get("message") or "")[:80],
            )
        console.print(table)


@reports.command("test")
@click.argument("run_id", type=int)
@click.argument("nodeid")
def report_test(run_id, nodeid):
    """Show report for a specific test case."""
    with _client() as c:
        r = c.get(f"/runs/{run_id}/reports/test/{nodeid}")
    if r.status_code == 404:
        _abort(f"No report for test '{nodeid}' in run #{run_id}")
    if r.status_code != 200:
        _abort(r.text)
    data = r.json()
    result = data.get("result", data)

    status = result.get("status", "?")
    color = "green" if status == "PASSED" else "red" if status in ("FAILED", "ERROR") else "yellow"

    table = Table(title=f"Test Report", box=box.ROUNDED)
    table.add_column("Field", style="cyan")
    table.add_column("Value")
    table.add_row("Node ID", result.get("nodeid", nodeid))
    table.add_row("Status", f"[{color}]{status}[/{color}]")
    table.add_row("Duration", f"{result.get('time', result.get('duration', 0)):.3f}s")

    if result.get("message"):
        table.add_row("Message", result["message"][:200])
    if result.get("stdout"):
        table.add_row("Stdout", result["stdout"][:300])
    if result.get("stderr"):
        table.add_row("Stderr", result["stderr"][:300])
    console.print(table)


# ── Metrics / Dashboard ─────────────────────────────────────────────────────


@cli.command()
def dashboard():
    """Show platform dashboard metrics."""
    with _client() as c:
        r = c.get("/metrics")
    if r.status_code != 200:
        _abort(r.text)
    m = r.json()

    # Overview
    total = m.get("total_runs", 0)
    panel = Text()
    panel.append(f"Total: {total}  ", style="bold")
    panel.append(f"Completed: {m.get('completed_runs', 0)}  ", style="green")
    panel.append(f"Failed: {m.get('failed_runs', 0)}  ", style="red")
    panel.append(f"Running: {m.get('running_runs', 0)}  ", style="yellow")
    panel.append(f"Pending: {m.get('pending_runs', 0)}  ", style="blue")
    panel.append(f"Success Rate: {m.get('success_rate', 0):.1f}%", style="bold")
    console.print(Panel(panel, title="DVP Dashboard", border_style="cyan"))

    # Client activity
    client_stats = m.get("client_stats", [])
    if client_stats:
        table = Table(title="Client Activity", box=box.ROUNDED)
        table.add_column("Client", style="bold")
        table.add_column("Runs", justify="right")
        for cs in client_stats:
            table.add_row(cs["name"], str(cs["runs"]))
        console.print(table)

    # Resource utilization
    resource_stats = m.get("resource_stats", [])
    if resource_stats:
        table = Table(title="Resource Utilization", box=box.ROUNDED)
        table.add_column("Resource", style="bold")
        table.add_column("Runs", justify="right")
        for rs in resource_stats:
            table.add_row(rs["name"], str(rs["runs"]))
        console.print(table)


# ── Admin ───────────────────────────────────────────────────────────────────


@cli.group()
def admin():
    """Admin operations (requires ADMIN_API_KEY env var)."""


@admin.command("cleanup")
def admin_cleanup():
    """Clean up stale locks and stuck runs."""
    with _client() as c:
        r = c.post("/admin/cleanup", headers=_admin_headers())
    if r.status_code == 200:
        data = r.json()
        console.print(f"[green]✓[/green] Cleanup: {data}")
    elif r.status_code == 403:
        _abort("Access denied. Set ADMIN_API_KEY env var.")
    else:
        _abort(r.text)


@admin.command("purge")
@click.option("--days", default=7, help="Retention period in days")
def admin_purge(days):
    """Purge runs older than N days."""
    with _client() as c:
        r = c.post(f"/admin/purge?retention_days={days}", headers=_admin_headers())
    if r.status_code == 200:
        data = r.json()
        console.print(f"[green]✓[/green] Purge: {data}")
    elif r.status_code == 403:
        _abort("Access denied. Set ADMIN_API_KEY env var.")
    else:
        _abort(r.text)


# ── Entry Point ─────────────────────────────────────────────────────────────


if __name__ == "__main__":
    cli()
