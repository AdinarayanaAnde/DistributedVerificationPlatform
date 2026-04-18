# DVP — Requirements Specification

**Distributed Verification Platform**
Version 1.0

---

## 1. Document Overview

This document defines the functional and non-functional requirements for the Distributed Verification Platform (DVP). Requirements follow a traceable identifier scheme and are categorized by domain.

### Conventions

| Prefix | Domain |
|--------|--------|
| `REQ-AUTH` | Authentication & Authorization |
| `REQ-CLI` | Client Management |
| `REQ-TD` | Test Discovery |
| `REQ-EXE` | Test Execution |
| `REQ-STE` | Setup & Teardown |
| `REQ-SUI` | Test Suites |
| `REQ-RPT` | Reporting |
| `REQ-MON` | Monitoring & Real-Time |
| `REQ-RES` | Resource Management |
| `REQ-UPL` | File Upload |
| `REQ-NOT` | Notifications |
| `REQ-RET` | Data Retention |
| `REQ-ADM` | Administration |
| `REQ-CMD` | Command-Line Interface |
| `REQ-DEP` | Deployment |
| `REQ-SEC` | Security |
| `REQ-PER` | Performance |
| `REQ-USA` | Usability |

**Priority**: **P1** = Must Have, **P2** = Should Have, **P3** = Nice to Have

---

## 2. Functional Requirements

### 2.1 Authentication & Authorization

| ID | Priority | Requirement | Acceptance Criteria |
|----|----------|-------------|---------------------|
| REQ-AUTH-001 | P1 | The system shall authenticate users via JWT bearer tokens using HS256 algorithm | Login returns a signed JWT; protected endpoints reject requests without valid tokens |
| REQ-AUTH-002 | P1 | The system shall hash passwords using bcrypt before storage | No plaintext passwords exist in the database |
| REQ-AUTH-003 | P1 | JWT tokens shall expire after a configurable duration (default: 15 minutes) | Expired tokens are rejected with HTTP 401 |
| REQ-AUTH-004 | P1 | Administrative endpoints shall require an API key passed via `x-admin-key` header | Admin operations fail with HTTP 403 when the key is missing or incorrect |
| REQ-AUTH-005 | P2 | The system shall rate-limit login attempts to 5 per client per 60-second window | The 6th attempt within 60 seconds returns HTTP 429 |
| REQ-AUTH-006 | P2 | In development mode (no `ADMIN_API_KEY` configured), admin endpoints shall be accessible without a key | Allows easy local development and testing |

### 2.2 Client Management

| ID | Priority | Requirement | Acceptance Criteria |
|----|----------|-------------|---------------------|
| REQ-CLI-001 | P1 | The system shall allow registration of named clients with a unique, auto-generated client key | `POST /api/clients/register` returns a client object with a unique `client_key` |
| REQ-CLI-002 | P1 | Client names shall be unique (case-insensitive) | Registering the same name returns the existing client without creating a duplicate |
| REQ-CLI-003 | P2 | Clients shall optionally provide an email address and webhook URL at registration | Fields are stored and used for notifications on run completion |
| REQ-CLI-004 | P1 | The system shall list all registered clients ordered by creation date (newest first) | `GET /api/clients` returns a complete, ordered list |

### 2.3 Test Discovery

| ID | Priority | Requirement | Acceptance Criteria |
|----|----------|-------------|---------------------|
| REQ-TD-001 | P1 | The system shall discover test files matching the `test_*.py` pattern from the server's `tests/` directory | `GET /api/tests/discover` returns nodeids for all matching tests |
| REQ-TD-002 | P1 | The system shall parse Python files to extract `def test_*` functions and `class Test*` classes | All test functions and methods are returned with correct nodeids (`file::class::method` or `file::function`) |
| REQ-TD-003 | P2 | When a `client_key` is provided, the system shall also discover tests from that client's uploaded files | Uploaded tests appear alongside server-side tests |
| REQ-TD-004 | P2 | Discovery results shall be cached with a 10-second TTL to reduce file system overhead | Repeated calls within 10 seconds return cached results |

### 2.4 Test Execution

| ID | Priority | Requirement | Acceptance Criteria |
|----|----------|-------------|---------------------|
| REQ-EXE-001 | P1 | The system shall execute selected tests by launching one pytest subprocess per test file (file-level parallelism) | Tests across N files result in N concurrent subprocesses |
| REQ-EXE-002 | P1 | The system shall capture stdout and stderr from each subprocess in real-time | Log entries appear in the database within 300ms of being emitted |
| REQ-EXE-003 | P1 | Each run shall transition through defined states: `pending` → `running` → `completed` / `failed` / `cancelled` | Run status is updated in the database at each transition |
| REQ-EXE-004 | P1 | The system shall enforce a configurable timeout (`PYTEST_TIMEOUT`, default: 3600s) per run | All subprocesses are killed when the timeout is reached; run status becomes `failed` |
| REQ-EXE-005 | P1 | Users shall be able to cancel a running or queued run | `POST /api/runs/{id}/cancel` kills all subprocesses and sets status to `cancelled` |
| REQ-EXE-006 | P2 | Users shall be able to cancel a specific test file within a running run | `POST /api/runs/{id}/cancel/{file_path}` kills only that file's subprocess |
| REQ-EXE-007 | P1 | Each subprocess shall generate a per-file JUnit XML report | JUnit XML files exist in `reports/{run_id}/` for each executed file |
| REQ-EXE-008 | P2 | The system shall support CLI command execution restricted to an allowlist (`pytest`, `python -m pytest`, `python -m unittest`) | `POST /api/cli/execute` rejects commands not on the allowlist |

### 2.5 Setup & Teardown

| ID | Priority | Requirement | Acceptance Criteria |
|----|----------|-------------|---------------------|
| REQ-STE-001 | P2 | Users shall create setup configurations with ordered steps | CRUD operations on `/api/setup-configurations` function correctly |
| REQ-STE-002 | P2 | Each setup step shall have: name, type (command/script/check/env), command, timeout, failure policy, and environment variables | All fields are persisted and used during execution |
| REQ-STE-003 | P2 | Setup steps shall execute sequentially before tests begin | Log entries show setup steps completing before the first test log |
| REQ-STE-004 | P2 | The failure policy shall control behavior: "fail" aborts the run, "skip" skips to teardown, "continue" proceeds to the next step | Each policy produces the documented behavior |
| REQ-STE-005 | P2 | Users shall create teardown configurations with the same structure as setup | CRUD operations on `/api/teardown-configurations` function correctly |
| REQ-STE-006 | P2 | Teardown shall execute after tests complete, regardless of test outcome | Teardown steps run even when all tests fail or the run is cancelled |
| REQ-STE-007 | P3 | Pre-defined setup and teardown scripts shall be listed from the `setup_scripts/` and `teardown_scripts/` directories | `GET /api/setup-scripts` and `GET /api/teardown-scripts` return available scripts |

### 2.6 Test Suites

| ID | Priority | Requirement | Acceptance Criteria |
|----|----------|-------------|---------------------|
| REQ-SUI-001 | P1 | The system shall auto-generate suites based on directory structure (smoke, unit, integration) and naming patterns (quick, security, data) | `GET /api/test-suites` includes auto-generated suites with correct test memberships |
| REQ-SUI-002 | P2 | The system shall generate suites from `@pytest.mark.*` decorators | Marker-based suites appear with the correct tests |
| REQ-SUI-003 | P2 | Users shall create, update, and delete custom test suites | CRUD operations on `/api/custom-suites` function correctly |
| REQ-SUI-004 | P2 | Suites shall track run history and estimated duration (based on last 5 completed runs) | `GET /api/test-suites` includes `estimated_duration` and `last_run` fields |
| REQ-SUI-005 | P2 | Suite runs shall be tracked via run-suite link records | `run_suite_links` table is populated when a suite is used in a run |

### 2.7 Reporting

| ID | Priority | Requirement | Acceptance Criteria |
|----|----------|-------------|---------------------|
| REQ-RPT-001 | P1 | The system shall generate JUnit XML reports by merging per-file outputs | A unified `junit.xml` exists in `reports/{run_id}/` after completion |
| REQ-RPT-002 | P1 | The system shall generate styled HTML reports with summary cards and test results | HTML report renders correctly in a browser with dark/light theme support |
| REQ-RPT-003 | P1 | The system shall generate JSON reports containing run metadata, statistics, test results, and logs | JSON report includes all expected fields |
| REQ-RPT-004 | P2 | The system shall generate per-test reports (result.json + junit.xml per test function) | Individual test reports exist in `reports/{run_id}/tests/` |
| REQ-RPT-005 | P2 | The system shall generate per-file aggregated reports | File-level summaries exist in `reports/{run_id}/files/` |
| REQ-RPT-006 | P2 | The system shall dynamically generate per-suite reports from per-test data | `GET /api/runs/{id}/reports/suite/{suite_id}` returns aggregated results |
| REQ-RPT-007 | P2 | Coverage reports shall be included when pytest-cov produces output | Coverage data is available via `GET /api/runs/{id}/reports/coverage` |
| REQ-RPT-008 | P3 | Allure reports shall be included when allure-pytest produces output | Allure data is available via `GET /api/runs/{id}/reports/allure` |
| REQ-RPT-009 | P1 | Users shall download individual reports or all reports as a ZIP archive | Download endpoints return correct content types and file attachments |
| REQ-RPT-010 | P1 | Reports shall be stored in both the database and the file system | Report data exists in `report_data` table and `reports/` directory |

### 2.8 Monitoring & Real-Time

| ID | Priority | Requirement | Acceptance Criteria |
|----|----------|-------------|---------------------|
| REQ-MON-001 | P1 | The system shall stream log entries via WebSocket at `WS /api/runs/{id}/logs/ws` | Client receives new log entries within 1 second of generation |
| REQ-MON-002 | P1 | The WebSocket shall auto-close when the run reaches a terminal state | Connection closes after a final drain when run completes/fails/cancels |
| REQ-MON-003 | P2 | HTTP polling shall serve as a fallback for log retrieval | `GET /api/runs/{id}/logs` returns all log entries |
| REQ-MON-004 | P1 | The dashboard shall display per-test status indicators (not-started, running, passed, failed, error, cancelled) | Status icons update in real-time as tests execute |
| REQ-MON-005 | P1 | The dashboard shall display summary cards with test result counts | Passed, failed, error, running, and not-started counts are accurate |

### 2.9 Resource Management

| ID | Priority | Requirement | Acceptance Criteria |
|----|----------|-------------|---------------------|
| REQ-RES-001 | P2 | Users shall create named resources representing shared test environments | `POST /api/resources` creates a resource with a unique name |
| REQ-RES-002 | P2 | The system shall enforce exclusive locking — only one run may hold a resource lock at a time | Concurrent lock attempts for the same resource result in queuing |
| REQ-RES-003 | P2 | Runs waiting for a locked resource shall be enqueued with position tracking | `GET /api/resources/{name}/queue` shows queued runs with positions |
| REQ-RES-004 | P2 | When a lock is released, the next queued run shall start automatically | The queued run transitions to `running` when the preceding run finishes |
| REQ-RES-005 | P2 | Stale locks from terminated runs shall be auto-released | Locks held by completed/failed/cancelled runs are released on next acquire attempt |

### 2.10 File Upload

| ID | Priority | Requirement | Acceptance Criteria |
|----|----------|-------------|---------------------|
| REQ-UPL-001 | P2 | Users shall upload test files as ZIP archives | `POST /api/tests/upload` accepts ZIP files and extracts them |
| REQ-UPL-002 | P1 | Uploads shall be limited to a configurable max size (default: 50 MB) | Files exceeding the limit are rejected with an appropriate error |
| REQ-UPL-003 | P1 | The system shall reject ZIP entries with path traversal sequences | Filenames containing `..` are rejected |
| REQ-UPL-004 | P2 | Duplicate uploads (same content hash) shall be deduplicated | SHA-256 hash match returns the existing upload |
| REQ-UPL-005 | P2 | Uploads shall be isolated per client | Clients can only see and delete their own uploads |

### 2.11 Notifications

| ID | Priority | Requirement | Acceptance Criteria |
|----|----------|-------------|---------------------|
| REQ-NOT-001 | P2 | The system shall send email notifications on run completion via SMTP/TLS | Clients with configured email receive completion notifications |
| REQ-NOT-002 | P2 | The system shall send webhook notifications (HTTP POST with JSON payload) on run completion | Clients with configured webhook URLs receive POST requests |
| REQ-NOT-003 | P2 | Email and webhook notifications shall execute in parallel | Both are dispatched concurrently via `asyncio.gather` |
| REQ-NOT-004 | P3 | Notification failures shall be logged but shall not affect run status | A failed email/webhook does not change the run's final status |

### 2.12 Data Retention

| ID | Priority | Requirement | Acceptance Criteria |
|----|----------|-------------|---------------------|
| REQ-RET-001 | P1 | The system shall automatically delete runs older than `DATA_RETENTION_DAYS` (default: 7) | Runs, logs, locks, queue entries, and reports older than the threshold are purged |
| REQ-RET-002 | P1 | The system shall prune reports exceeding `MAX_REPORT_COUNT` (default: 50), removing the oldest first | At most 50 completed run reports exist at any time |
| REQ-RET-003 | P2 | The purge service shall run as a background task at a configurable interval (default: every 24 hours) | Purge executes automatically without manual intervention |
| REQ-RET-004 | P2 | Report pruning shall also execute after every test run completes | Excess reports are cleaned up immediately, not only during periodic purge |

### 2.13 Administration

| ID | Priority | Requirement | Acceptance Criteria |
|----|----------|-------------|---------------------|
| REQ-ADM-001 | P2 | Administrators shall trigger manual data purge with configurable retention and report limits | `POST /api/admin/purge` accepts `retention_days` and `max_reports` parameters |
| REQ-ADM-002 | P2 | Administrators shall trigger cleanup of stale locks and stuck runs | `POST /api/admin/cleanup` releases stale locks and fails stuck runs |
| REQ-ADM-003 | P1 | On server startup, all unreleased resource locks shall be released and stuck runs marked as failed | No stale state persists after a server restart |

### 2.14 Command-Line Interface

| ID | Priority | Requirement | Acceptance Criteria |
|----|----------|-------------|---------------------|
| REQ-CMD-001 | P2 | The CLI shall support health checking, client registration, test discovery, run creation, log viewing, and report downloading | All listed subcommands execute correctly |
| REQ-CMD-002 | P2 | The CLI shall support a `--wait` flag that blocks until a run completes | The command exits only after the run reaches a terminal state |
| REQ-CMD-003 | P3 | The CLI shall use formatted output (Rich tables, colored text) for readability | Output is visually structured when run in a terminal |
| REQ-CMD-004 | P2 | The CLI shall connect to a configurable server URL via `DVP_URL` environment variable | Changing `DVP_URL` directs all commands to the specified server |

### 2.15 Deployment

| ID | Priority | Requirement | Acceptance Criteria |
|----|----------|-------------|---------------------|
| REQ-DEP-001 | P1 | The system shall be deployable via Docker Compose with PostgreSQL, backend, and frontend services | `docker compose up` starts all services correctly |
| REQ-DEP-002 | P2 | A portable Docker Compose variant shall use named volumes for data persistence | `docker-compose.portable.yml` uses `dvp-db` and `dvp-reports` named volumes |
| REQ-DEP-003 | P2 | The system shall be deployable to Kubernetes via Kustomize manifests | `kubectl apply -k k8s/` deploys all resources |
| REQ-DEP-004 | P1 | Health checks shall be available at `GET /api/health` for liveness and readiness probes | Returns 200 when healthy, 503 when the database is unavailable |

---

## 3. Non-Functional Requirements

### 3.1 Security

| ID | Priority | Requirement | Acceptance Criteria |
|----|----------|-------------|---------------------|
| REQ-SEC-001 | P1 | The system shall use timing-safe comparison for API key validation | `secrets.compare_digest` is used for admin key checks |
| REQ-SEC-002 | P1 | The system shall limit HTTP request body size (default: 10 MB) | Requests exceeding the limit are rejected |
| REQ-SEC-003 | P1 | CLI command execution shall reject shell metacharacters (`;`, `|`, `&`, `` ` ``, `$`, `<`, `>`, `\n`, `\r`) | Commands containing metacharacters are rejected with HTTP 400 |
| REQ-SEC-004 | P1 | Report download paths shall be validated against the reports directory to prevent path traversal | Attempts to access files outside `reports/` are rejected |
| REQ-SEC-005 | P1 | ZIP uploads shall be protected against zip bombs (3× decompressed size limit) | Excessively large archives are rejected during extraction |
| REQ-SEC-006 | P2 | CORS origins shall be configurable; wildcard origins shall disable credential support | `Access-Control-Allow-Credentials` is `false` when `CORS_ORIGINS=*` |
| REQ-SEC-007 | P1 | The system shall log a warning when the default `SECRET_KEY` is in use | A visible warning appears in server logs at startup |
| REQ-SEC-008 | P1 | Full error tracebacks shall only be returned when `DEBUG=true` | Production responses contain only "Internal server error" |

### 3.2 Performance

| ID | Priority | Requirement | Acceptance Criteria |
|----|----------|-------------|---------------------|
| REQ-PER-001 | P1 | Test execution shall use file-level parallelism to minimize total run duration | N test files execute concurrently in N subprocesses |
| REQ-PER-002 | P2 | WebSocket log delivery latency shall not exceed 1 second under normal load | Logs appear in the frontend within 1 second of subprocess output |
| REQ-PER-003 | P2 | Test discovery results shall be cached (10-second TTL) to reduce I/O | Repeated discovery calls within 10 seconds do not re-scan the file system |
| REQ-PER-004 | P2 | The database connection pool shall be configurable for production (default: pool_size=10, max_overflow=20) | PostgreSQL connections are pooled and recycled |

### 3.3 Usability

| ID | Priority | Requirement | Acceptance Criteria |
|----|----------|-------------|---------------------|
| REQ-USA-001 | P2 | The UI shall support dark and light themes with persistence across sessions | Theme preference is saved in `localStorage` and restored on reload |
| REQ-USA-002 | P1 | The dashboard shall display context-appropriate messages before and after client registration | Welcome message before registration; "ready to run" message after registration with no runs |
| REQ-USA-003 | P2 | The sidebar shall organize functionality into tabbed panels (Tests, Suites, Setup, Teardown, Upload, CLI) | All panels are accessible via tabs |
| REQ-USA-004 | P2 | The log viewer shall support multiple simultaneous log tabs | Users can open logs for different tests/files at the same time |
| REQ-USA-005 | P2 | HTML reports shall respect the user's selected theme | Reports render in the same dark/light mode as the main UI |

---

## 4. Traceability Matrix

| Requirement | Component(s) | Verification Method |
|-------------|-------------|---------------------|
| REQ-AUTH-001 to 006 | `auth.py`, `routes.py` | Unit test + integration test |
| REQ-CLI-001 to 004 | `routes.py`, `models.py` | API test |
| REQ-TD-001 to 004 | `routes.py` (discover endpoint) | API test + manual |
| REQ-EXE-001 to 008 | `runner.py`, `routes.py` | Integration test + E2E test |
| REQ-STE-001 to 007 | `runner.py`, `routes.py`, `models.py` | Integration test |
| REQ-SUI-001 to 005 | `routes.py`, `models.py` | API test |
| REQ-RPT-001 to 010 | `report_generator.py`, `routes.py` | Integration test + manual |
| REQ-MON-001 to 005 | `routes.py` (WebSocket), `Dashboard.tsx` | E2E test + manual |
| REQ-RES-001 to 005 | `queue.py`, `routes.py` | Integration test |
| REQ-UPL-001 to 005 | `routes.py` (upload endpoint) | API test + security test |
| REQ-NOT-001 to 004 | `notifications.py` | Integration test + manual |
| REQ-RET-001 to 004 | `purge.py`, `routes.py` | Integration test |
| REQ-ADM-001 to 003 | `routes.py`, `main.py` | API test |
| REQ-CMD-001 to 004 | `cli.py` | CLI test + manual |
| REQ-DEP-001 to 004 | Docker/K8s manifests | Deployment test |
| REQ-SEC-001 to 008 | `auth.py`, `routes.py`, `main.py` | Security test |
| REQ-PER-001 to 004 | `runner.py`, `routes.py`, `db.py` | Performance test |
| REQ-USA-001 to 005 | Frontend components | Manual + E2E test |
