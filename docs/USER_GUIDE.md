# DVP — User Guide

**Distributed Verification Platform**
Version 1.0 · Last updated: April 2026

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Getting Started](#2-getting-started)
   - 2.1 [Prerequisites](#21-prerequisites)
   - 2.2 [Installation](#22-installation)
   - 2.3 [First Launch](#23-first-launch)
3. [Client Registration](#3-client-registration)
4. [Test Discovery & Selection](#4-test-discovery--selection)
   - 4.1 [Test Explorer](#41-test-explorer)
   - 4.2 [Searching and Filtering](#42-searching-and-filtering)
   - 4.3 [Selecting Tests](#43-selecting-tests)
5. [Test Suites](#5-test-suites)
   - 5.1 [Auto-Generated Suites](#51-auto-generated-suites)
   - 5.2 [Marker-Based Suites](#52-marker-based-suites)
   - 5.3 [Custom Suites](#53-custom-suites)
6. [Running Tests](#6-running-tests)
   - 6.1 [Standard Execution](#61-standard-execution)
   - 6.2 [CLI Mode](#62-cli-mode)
   - 6.3 [Cancelling a Run](#63-cancelling-a-run)
7. [Setup & Teardown](#7-setup--teardown)
   - 7.1 [Setup Configurations](#71-setup-configurations)
   - 7.2 [Teardown Configurations](#72-teardown-configurations)
   - 7.3 [Step Types & Failure Policies](#73-step-types--failure-policies)
   - 7.4 [Pre-defined Scripts](#74-pre-defined-scripts)
8. [Real-Time Monitoring](#8-real-time-monitoring)
   - 8.1 [Dashboard Overview](#81-dashboard-overview)
   - 8.2 [Log Viewer](#82-log-viewer)
   - 8.3 [Run Selector](#83-run-selector)
9. [Reports](#9-reports)
   - 9.1 [Report Types](#91-report-types)
   - 9.2 [Viewing Reports](#92-viewing-reports)
   - 9.3 [Downloading Reports](#93-downloading-reports)
   - 9.4 [Per-Test & Per-File Reports](#94-per-test--per-file-reports)
10. [Test Upload](#10-test-upload)
11. [Resource Management](#11-resource-management)
12. [Metrics & Analytics](#12-metrics--analytics)
13. [CLI Tool](#13-cli-tool)
14. [Notifications](#14-notifications)
15. [Themes](#15-themes)
16. [Configuration Reference](#16-configuration-reference)
17. [Deployment](#17-deployment)
    - 17.1 [Docker Compose](#171-docker-compose)
    - 17.2 [Kubernetes](#172-kubernetes)
18. [Troubleshooting](#18-troubleshooting)
19. [FAQ](#19-faq)

---

## 1. Introduction

The **Distributed Verification Platform (DVP)** is a web-based test orchestration system designed for engineering teams that need centralized, scalable test execution with real-time visibility. DVP manages the full test lifecycle — from discovery through execution to reporting — with support for parallel execution, shared resource locking, environment setup/teardown, and multi-format report generation.

### Key Capabilities

| Capability | Description |
|------------|-------------|
| **Test Discovery** | Automatic detection of pytest test functions from the server's test directory and uploaded test files |
| **Parallel Execution** | File-level parallelism — each test file runs in its own pytest subprocess concurrently |
| **Real-Time Logs** | WebSocket-powered live log streaming with per-test and per-file filtering |
| **Setup & Teardown** | Configurable pre-test and post-test automation with ordered steps, timeouts, and failure policies |
| **Multi-Format Reports** | HTML, JSON, JUnit XML, per-test, per-file, per-suite, coverage, and Allure report generation |
| **Resource Locking** | Exclusive resource acquisition with automatic queuing for shared environments |
| **Test Suites** | Auto-generated, marker-based, and user-defined test suites with history tracking |
| **Notifications** | Email and webhook notifications on run completion |
| **CLI & API** | Full-featured command-line tool and REST API for automation and CI/CD integration |
| **Upload** | Upload test files as ZIP archives for remote execution |

---

## 2. Getting Started

### 2.1 Prerequisites

| Requirement | Version |
|-------------|---------|
| Python | 3.11+ |
| Node.js | 18+ (for frontend development) |
| Docker | 20+ (for containerized deployment) |
| Git | 2.30+ |

### 2.2 Installation

**Option A: Local Development**

```bash
# Clone the repository
git clone <repository-url>
cd DistributedVerificationPlatform

# Backend setup
cd backend
pip install -r requirements.txt

# Frontend setup
cd ../frontend
npm install
```

**Option B: Docker Compose**

```bash
docker compose up --build
```

The application will be available at:
- Frontend: `http://localhost:5173` (dev) or `http://localhost:80` (Docker)
- Backend API: `http://localhost:8000/api`

### 2.3 First Launch

1. Start the backend: `cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
2. Start the frontend: `cd frontend && npm run dev`
3. Open `http://localhost:5173` in your browser
4. The dashboard displays a welcome message — proceed to register a client

---

## 3. Client Registration

Before running tests, register a client identity. This associates your test runs, logs, and reports with a named client.

1. In the sidebar, enter a **Client Name** (e.g., `dev-team`, `ci-pipeline`)
2. Optionally enter a **Resource Name** if you need exclusive access to a shared test environment
3. Click **Register**
4. Your **Client Key** is displayed — this is your unique identifier for all operations
5. The key is stored in your browser session for convenience

> **Note**: Registering the same name again returns the existing client key. Client names are case-insensitive.

---

## 4. Test Discovery & Selection

### 4.1 Test Explorer

The **Tests** tab in the sidebar shows all discovered tests in a tree hierarchy:

```
tests/
├── integration/
│   └── test_api.py
│       ├── test_create_user
│       └── test_delete_user
├── unit/
│   └── test_models.py
│       ├── TestUserModel::test_create
│       └── TestUserModel::test_validate
└── test_smoke.py
    └── test_health_check
```

- **Folders** group tests by directory
- **Files** represent individual test modules
- **Tests** are the actual test functions/methods
- Status icons show results after a run: ✅ passed, ❌ failed, ⚠️ error, ⏳ running

### 4.2 Searching and Filtering

Use the search bar at the top of the test explorer to filter tests by name, path, or function name. The filter applies in real-time across the entire tree.

### 4.3 Selecting Tests

- **Click a checkbox** to select individual tests
- **Click a folder/file checkbox** to select all tests within it
- **Select All / Deselect All** buttons at the top for bulk operations
- The test count badge shows how many tests are currently selected

---

## 5. Test Suites

Suites are named collections of tests that can be selected as a group.

### 5.1 Auto-Generated Suites

DVP automatically generates suites based on your test directory structure and naming conventions:

| Suite | Discovery Rule |
|-------|---------------|
| **All Tests** | Every discovered test |
| **Smoke** | Tests in `smoke/` directory |
| **Unit** | Tests in `unit/` directory |
| **Integration** | Tests in `integration/` directory |
| **Quick** | Tests with `_quick` in filename |
| **Security** | Tests with `security` in filename |
| **Data** | Tests with `data` in filename |

### 5.2 Marker-Based Suites

Tests decorated with `@pytest.mark.<name>` are grouped into marker-based suites. For example:

```python
@pytest.mark.smoke
def test_login():
    ...
```

This test appears in both the auto-generated "Smoke" suite and a marker-based `@smoke` suite.

### 5.3 Custom Suites

Create your own test suites for recurring test scenarios:

1. Switch to the **Suites** tab in the sidebar
2. Select tests from the test explorer
3. Click **Create Suite from Selected**
4. Provide a name, description, and optional tags
5. The suite is saved and can be reused across runs

Custom suites track run history and estimated duration based on the last 5 completed runs.

---

## 6. Running Tests

### 6.1 Standard Execution

1. Select tests from the **Tests** tab or pick one or more suites from the **Suites** tab
2. (Optional) Select a **Setup Configuration** from the Setup tab
3. (Optional) Select a **Teardown Configuration** from the Teardown tab
4. Click **▶ Run** at the bottom of the sidebar
5. The dashboard switches to live monitoring mode

**Execution model**: Tests are grouped by file. Each file runs in a separate `pytest` subprocess, enabling file-level parallelism. A run with tests across 5 files launches 5 concurrent pytest processes.

### 6.2 CLI Mode

For advanced pytest commands:

1. Switch to the **CLI** tab in the sidebar
2. Enter a command (e.g., `pytest tests/ -k "smoke" --tb=short`)
3. Click **▶ Run**

Allowed commands: `pytest`, `python -m pytest`, `python -m unittest`. Shell operators and metacharacters are blocked for security.

### 6.3 Cancelling a Run

- Click the **✕ Cancel** button next to the run status badge in the dashboard
- Individual test files can be cancelled while others continue
- Cancelled runs release their resource lock and auto-start the next queued run

---

## 7. Setup & Teardown

### 7.1 Setup Configurations

Setup configurations define steps that execute **before** test runs — ideal for environment preparation, dependency checks, and database seeding.

1. Switch to the **Setup** tab in the sidebar
2. Click **+ New Configuration**
3. Enter a name and optional description
4. Add one or more steps, each with:
   - **Step name** — descriptive label
   - **Step type** — Command, Script, Health Check, or Environment
   - **Command** — the shell command or script to execute
   - **Timeout** — max seconds before the step is killed (default: 300)
   - **On Failure** — what happens if the step fails:
     - **Fail Run** — abort the entire test run
     - **Skip Tests** — skip to teardown
     - **Continue** — proceed to the next step
5. Click **Create Configuration**
6. Select the configuration (checkbox) to activate it for the next run

### 7.2 Teardown Configurations

Teardown configurations define steps that execute **after** test runs — used for cleanup, log archival, and environment reset. Teardown runs regardless of whether tests passed or failed.

The UI and workflow are identical to setup. The key difference:
- Default failure policy is **Continue** (best practice: teardown should always attempt all steps)
- Teardown executes after tests complete, even if tests failed or were cancelled

### 7.3 Step Types & Failure Policies

| Step Type | Purpose | Example |
|-----------|---------|---------|
| **Command** | Execute a shell command | `pip install -r requirements.txt` |
| **Script** | Run a Python script | `python setup_scripts/check_health.py` |
| **Health Check** | Verify a service is responding | `curl -f http://localhost:8000/api/health` |
| **Environment** | Set environment variables | `DATABASE_URL=sqlite:///test.db` |

| Failure Policy | Behavior |
|----------------|----------|
| **Fail Run** | Stop immediately, mark run as failed |
| **Skip Tests** | Skip remaining setup/tests, proceed to teardown |
| **Continue** | Log the failure, proceed to the next step |

### 7.4 Pre-defined Scripts

DVP includes ready-to-use scripts accessible as "Quick Templates":

**Setup Scripts** (`setup_scripts/`):
| Script | Purpose |
|--------|---------|
| `check_dependencies.py` | Verify required packages are installed |
| `check_health.py` | Confirm backend API is healthy |
| `clean_artifacts.py` | Remove stale test caches and temp files |
| `validate_database.py` | Verify database connectivity and schema |

**Teardown Scripts** (`teardown_scripts/`):
| Script | Purpose |
|--------|---------|
| `cleanup_temp_files.py` | Remove `__pycache__`, `.pytest_cache`, temp files |
| `archive_test_logs.py` | Archive reports to timestamped backup directory |
| `reset_test_database.py` | Clean up test-specific database files |
| `generate_summary.py` | Print pass/fail summary from latest report |

---

## 8. Real-Time Monitoring

### 8.1 Dashboard Overview

The dashboard is the main view showing:

- **Run Detail** — current run status, duration, file count, test count, start/finish times
- **Setup/Teardown Status** — clickable badges showing setup and teardown execution status
- **Test Summary Cards** — visual breakdown of passed, failed, errors, running, and not-started counts
- **Report Buttons** — quick access to all generated reports (after run completes)
- **Test Results Table** — detailed per-test results with status, duration, and log access
- **Metrics Panel** — system-wide statistics (total runs, success rate, active runs, client activity)

### 8.2 Log Viewer

Click on any test name in the results table, or on the setup/teardown badge, to open a filtered log tab:

- **Real-time streaming** via WebSocket connection
- **Color-coded log levels**: INFO (default), PASS (green), FAIL (red), ERROR (red)
- **Auto-scroll** follows the latest log entries
- **Multiple tabs** — open logs for different tests simultaneously
- **Close tabs** — click the × button on any log tab

### 8.3 Run Selector

The run selector dropdown in the dashboard header lets you browse historical runs:

- Runs are listed in reverse chronological order
- Selecting a historical run loads its logs, results, and reports
- Active runs continue streaming updates in real-time

---

## 9. Reports

### 9.1 Report Types

| Report | Description | Format |
|--------|-------------|--------|
| **HTML** | Styled, self-contained report with summary cards, test table, and recent logs | HTML |
| **JSON** | Complete structured data: run metadata, statistics, all test results, all logs | JSON |
| **JUnit XML** | Industry-standard XML format compatible with CI/CD tools (Jenkins, GitLab, etc.) | XML |
| **Coverage** | Code coverage data (requires `pytest-cov` plugin) | JSON |
| **Allure** | Rich interactive report (requires `allure-pytest` plugin) | HTML |
| **Per-Test** | Individual test result with isolated JUnit XML | JSON + XML |
| **Per-File** | Aggregated results for all tests in a single file | JSON + XML |
| **Per-Suite** | Dynamically aggregated results for a test suite | JSON |

### 9.2 Viewing Reports

After a run completes, report buttons appear in the dashboard:

1. Click **HTML Report** to view the styled report in a new tab
2. Click **JSON** to view the structured data in the report viewer
3. Click **JUnit XML** to view the raw XML
4. Per-test reports are accessible from the test results table

### 9.3 Downloading Reports

- **Individual reports**: Click the download icon next to any report type
- **Download All**: Click **Download All** to get a ZIP archive containing all reports for the run
- Reports are stored both in the database and on disk (`reports/{run_id}/`)

### 9.4 Per-Test & Per-File Reports

For granular analysis:

- **Per-test**: Each test function gets its own `result.json` and `junit.xml` in `reports/{run_id}/tests/`
- **Per-file**: Each test file gets an aggregated summary in `reports/{run_id}/files/`
- Access these from the test results table or the API

---

## 10. Test Upload

Upload test files from your local machine for remote execution:

1. Switch to the **Upload** tab in the sidebar
2. Drag and drop a **ZIP file** containing your test files, or click to browse
3. The platform extracts and discovers tests from the uploaded archive
4. Uploaded tests appear in the test explorer alongside server-side tests

**Constraints**:
- Maximum file size: 50 MB (configurable via `MAX_UPLOAD_SIZE_MB`)
- Only ZIP format is accepted
- Duplicate uploads (same content) are automatically deduplicated
- Each client's uploads are isolated — you only see your own uploads

---

## 11. Resource Management

Resources represent shared test environments or hardware that require exclusive access:

1. Enter a **Resource Name** in the client registration section (e.g., `staging-env`, `test-lab-1`)
2. When you start a run, DVP attempts to acquire an exclusive lock on that resource
3. If the resource is already in use:
   - Your run is **queued** with a position number
   - The queue status is visible in the dashboard
   - When the current run finishes, the next queued run starts automatically
4. Resource locks are automatically released when runs complete, fail, or are cancelled

---

## 12. Metrics & Analytics

The **Metrics Panel** on the dashboard provides system-wide statistics:

| Metric | Description |
|--------|-------------|
| **Total Runs** | Lifetime count of all test runs |
| **Success Rate** | Percentage of completed runs vs. failed runs |
| **Running / Pending** | Currently active and waiting runs |
| **Recent (24h)** | Runs created in the last 24 hours |
| **Client Activity** | Run counts per registered client |
| **Resource Utilization** | Run counts per resource |

---

## 13. CLI Tool

DVP includes a command-line tool (`dvp`) for scripting and CI/CD integration:

```bash
# Set the server URL (default: http://localhost:8000)
export DVP_URL=http://your-server:8000

# Health check
dvp health

# Register a client
dvp clients register "ci-pipeline" --email alerts@company.com --webhook https://hooks.slack.com/...

# Discover tests
dvp tests discover --filter smoke

# Create and wait for a run
dvf runs create --client-key abc123 --suite smoke --resource staging --wait

# View run results
dvp runs show 42
dvp runs logs 42 --level FAIL --tail 50

# Download reports
dvp reports html 42 -o report.html
dvp reports junit 42 -o results.xml
dvp reports summary 42
```

### CLI Command Reference

| Command | Description |
|---------|-------------|
| `dvp health` | Check server connectivity |
| `dvp clients register <name>` | Register a new client (options: `--email`, `--webhook`) |
| `dvp clients list` | List all registered clients |
| `dvp resources create <name>` | Create a named resource |
| `dvp resources list` | List all resources |
| `dvp tests discover` | Discover available tests (`--filter` for substring matching) |
| `dvp tests suites` | List all test suites |
| `dvp runs create` | Create a test run (`--client-key`, `--suite`/`--tests`, `--resource`, `--wait`) |
| `dvp runs list` | List recent runs (`--limit N`) |
| `dvp runs show <id>` | Show run details |
| `dvp runs logs <id>` | View run logs (`--level`, `--tail`) |
| `dvp runs cancel <id>` | Cancel a running run |
| `dvp reports list <id>` | List available reports for a run |
| `dvp reports summary <id>` | Display test result summary |
| `dvp reports html <id>` | Download HTML report (`-o file`) |
| `dvp reports json <id>` | Download JSON report (`-o file`, `--pretty`) |
| `dvp reports junit <id>` | Download JUnit XML (`-o file`) |
| `dvp reports file <id> <path>` | Show per-file report |

---

## 14. Notifications

DVP sends notifications when test runs complete:

### Email Notifications
- Configure SMTP settings via environment variables (`SMTP_SERVER`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`)
- Register a client with an email address: the client receives completion emails with run status, test counts, and timestamps

### Webhook Notifications
- Register a client with a webhook URL
- DVP sends an HTTP POST with JSON payload on run completion:

```json
{
  "run_id": 42,
  "client_name": "ci-pipeline",
  "status": "completed",
  "selected_tests": ["tests/test_smoke.py::test_health"],
  "started_at": "2026-04-18T10:30:00Z",
  "finished_at": "2026-04-18T10:31:15Z",
  "note": null
}
```

---

## 15. Themes

DVP supports **dark** and **light** themes:

- Toggle via the theme button in the title bar (☀/🌙)
- Preference is saved to `localStorage` and persists across sessions
- HTML reports respect the selected theme

---

## 16. Configuration Reference

All configuration is via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/app.db` | Database connection string. Use `postgresql+asyncpg://...` for production |
| `SECRET_KEY` | `changeme-dev-only` | JWT signing key. **Change this in production** |
| `CORS_ORIGINS` | `*` | Comma-separated allowed origins for CORS |
| `ADMIN_API_KEY` | *(empty)* | Shared secret for admin endpoints. If unset, admin endpoints are open (dev mode) |
| `SMTP_SERVER` | `smtp.gmail.com` | SMTP server for email notifications |
| `SMTP_PORT` | `587` | SMTP port (TLS) |
| `SMTP_USERNAME` | *(empty)* | SMTP authentication username |
| `SMTP_PASSWORD` | *(empty)* | SMTP authentication password |
| `PYTEST_TIMEOUT` | `3600` | Maximum runtime (seconds) for a single pytest process |
| `MAX_UPLOAD_SIZE_MB` | `50` | Maximum upload ZIP file size in MB |
| `DATA_RETENTION_DAYS` | `7` | Auto-delete completed/failed runs older than N days |
| `MAX_REPORT_COUNT` | `50` | Maximum number of reports retained. Oldest are pruned when exceeded |
| `PURGE_INTERVAL_HOURS` | `24` | Interval (hours) between automatic purge cycles |
| `MAX_REQUEST_BODY_BYTES` | `10485760` | Maximum HTTP request body size (10 MB) |
| `DEBUG` | `false` | Enable detailed error tracebacks in API responses |

---

## 17. Deployment

### 17.1 Docker Compose

**Standard deployment** (PostgreSQL with host-mounted volumes):

```bash
docker compose up -d --build
```

**Portable deployment** (named Docker volumes):

```bash
docker compose -f docker-compose.portable.yml up -d --build
```

Services:
- `db` — PostgreSQL 16 database
- `backend` — FastAPI application (uvicorn)
- `frontend` — Vite-built static frontend served by Node

### 17.2 Kubernetes

Deploy to Kubernetes using Kustomize:

```bash
# Apply all manifests
kubectl apply -k k8s/

# Or apply individually
kubectl apply -f k8s/postgres-deployment.yaml
kubectl apply -f k8s/smtp-secret.yaml
kubectl apply -f k8s/backend-deployment.yaml
kubectl apply -f k8s/frontend-deployment.yaml
kubectl apply -f k8s/ingress.yaml
```

The ingress routes:
- `/` → Frontend service
- `/api` → Backend service

Health checks are configured for liveness and readiness probes at `/api/health`.

---

## 18. Troubleshooting

| Symptom | Cause | Solution |
|---------|-------|----------|
| "Backend unavailable" modal on page load | Backend not running or wrong port | Verify backend is running on port 8000. Check `http://localhost:8000/api/health` |
| Tests not appearing in explorer | No test files in `backend/tests/` | Add `test_*.py` files to the tests directory, or upload test files via the Upload tab |
| Run stuck in "pending" | Resource locked by another run | Check the resource queue or cancel the blocking run |
| "Register a client first" on sidebar tabs | Client not registered | Enter a name in the Client section and click Register |
| Upload rejected | File too large or wrong format | Ensure file is a ZIP under 50 MB |
| Logs not streaming | WebSocket connection failed | Check browser console for WS errors. The system falls back to HTTP polling |
| Reports not generating | pytest process crashed | Check run logs for errors. Ensure `pytest` is installed in the backend environment |

---

## 19. FAQ

**Q: Can I run tests from multiple clients simultaneously?**
A: Yes. Each client can run tests independently. If runs target the same resource, they are queued automatically.

**Q: How does file-level parallelism work?**
A: When you select tests across multiple files, DVP launches one pytest subprocess per file. All files run concurrently, reducing total execution time.

**Q: Are uploaded tests persistent?**
A: Uploaded tests are stored on the server until explicitly deleted. They are isolated per client.

**Q: What happens if my setup step fails?**
A: Depends on the step's failure policy. "Fail Run" aborts everything. "Skip Tests" skips to teardown. "Continue" proceeds to the next setup step.

**Q: Does teardown run if tests fail?**
A: Yes. Teardown always executes after tests complete, regardless of test outcome. This ensures cleanup happens reliably.

**Q: How many reports are retained?**
A: By default, the 50 most recent reports are kept. Older reports are automatically pruned. Additionally, reports older than 7 days are purged. Both limits are configurable via environment variables.

**Q: Can I integrate DVP with CI/CD?**
A: Yes. Use the CLI tool (`dvp`) or the REST API directly. The `--wait` flag on `dvp runs create` blocks until the run completes, making it ideal for pipeline scripts.
