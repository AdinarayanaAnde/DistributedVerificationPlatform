# Distributed Verification Platform

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Node.js 18+](https://img.shields.io/badge/node.js-18+-green.svg)](https://nodejs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18+-61dafb.svg)](https://reactjs.org/)

A comprehensive web-based test automation platform with distributed execution, real-time monitoring, and advanced reporting capabilities.

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [API Documentation](#api-documentation)
- [Development](#development)
- [Deployment](#deployment)
- [Contributing](#contributing)
- [License](#license)
- [Support](#support)
- [Project Structure](#project-structure)
- [Missing (Optional but Recommended)](#missing-optional-but-recommended)
- React frontend for test selection, logs, and summaries
- FastAPI backend with async orchestration
- Pytest test execution and result capture
- PostgreSQL-compatible centralized storage
- Multi-client concurrent request handling with resource queueing
- Real-time log streaming via WebSockets
- Advanced test discovery with filtering
- Run history and client management UI
- Docker deployment support
- JWT-based authentication
- Advanced run filtering
- CI/CD with GitHub Actions
- **Email and webhook notifications for run completion**
- **Metrics dashboard with system statistics**
- **Kubernetes deployment manifests**

## Features

### Core Functionality
- **Test Selection**: Browse and select tests from discovered pytest test files
- **Parallel Execution**: Run multiple tests concurrently with configurable parallelism
- **Resource Queueing**: Handle multiple clients accessing shared resources with intelligent queuing
- **Real-time Logs**: Stream test execution logs in real-time via WebSocket connections
- **Centralized Storage**: Store all test runs, logs, and client data in PostgreSQL

### Management & Monitoring
- **Run History**: View past test runs with filtering by status, test name, and date
- **Client Management**: Register and manage multiple test clients
- **Queue Monitoring**: View current queue status for resource-constrained tests
- **Metrics Dashboard**: System statistics including success rates, client activity, and resource utilization

### Notifications
- **Email Notifications**: Automatic email alerts for run completion (configurable per client)
- **Webhook Notifications**: HTTP webhook callbacks for integration with external systems

### Deployment
- **Docker Support**: Complete containerization with docker-compose for local development
- **Kubernetes**: Production-ready K8s manifests with ingress, secrets, and persistent storage
- **CI/CD**: Automated testing and building with GitHub Actions

## Architecture

### System Architecture Overview

```mermaid
graph TB
    subgraph "Clients"
        A[Web Browser]
        B[CLI Client]
        B2[CI/CD Pipeline]
    end

    subgraph "Frontend — React 18 + TypeScript + Vite :5173"
        C1[Test Explorer]
        C2[Live Logs]
        C3[Reports & Metrics]
        C4[Run Management]
        C5[Setup/Teardown Config]
    end

    subgraph "API Gateway — FastAPI :8000"
        D1[REST API]
        D2[WebSocket /ws/logs]
        D3[JWT Auth + Rate Limiting]
    end

    subgraph "Service Layer — Python 3.11 Async"
        E1[Test Runner<br/>File-level parallel pytest]
        E2[Queue Manager<br/>FIFO resource locking]
        E3[Report Generator<br/>HTML · JSON · JUnit XML]
        E4[Notifier<br/>Email + Webhook]
        E5[Purge Service<br/>Retention policies]
    end

    subgraph "Supporting Services"
        F1[Test Discovery<br/>Auto-scan + filter]
        F2[Suite Manager<br/>Custom + auto suites]
        F3[Upload Handler<br/>ZIP + dedup]
        F4[CLI Executor<br/>Allowlisted commands]
        F5[Setup/Teardown<br/>Pre/post hooks]
    end

    subgraph "Data Layer"
        G[(PostgreSQL / SQLite<br/>16 tables)]
        H[File Storage<br/>reports · uploads · scripts]
    end

    A --> C1
    B --> D1
    B2 --> D1

    C1 --> D1
    C2 --> D2
    C3 --> D1
    C4 --> D1
    C5 --> D1

    D1 --> E1
    D1 --> E2
    D1 --> E3
    D1 --> E4
    D1 --> F1
    D1 --> F2
    D1 --> F3
    D1 --> F4
    D1 --> F5
    D1 --> E5

    E1 --> G
    E1 --> H
    E2 --> G
    E3 --> G
    E3 --> H
    E4 --> G
    E5 --> G
    E5 --> H
    F3 --> H

    style C1 fill:#e1f5fe
    style C2 fill:#e1f5fe
    style C3 fill:#e1f5fe
    style C4 fill:#e1f5fe
    style C5 fill:#e1f5fe
    style D1 fill:#f3e5f5
    style D2 fill:#f3e5f5
    style D3 fill:#f3e5f5
    style E1 fill:#fff3e0
    style E2 fill:#fff3e0
    style E3 fill:#fff3e0
    style E4 fill:#fff3e0
    style E5 fill:#fff3e0
    style F1 fill:#e8f5e9
    style F2 fill:#e8f5e9
    style F3 fill:#e8f5e9
    style F4 fill:#e8f5e9
    style F5 fill:#e8f5e9
    style G fill:#ede7f6
    style H fill:#ede7f6
```

> **Detailed architecture** with sequence diagrams: see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

## Requirements

- **Python** >= 3.11
- **Node.js** >= 18
- **PostgreSQL** (production) or SQLite (local development)
- **Docker** (optional, for containerized deployment)

For complete dependency lists, see:
- Backend: [backend/pyproject.toml](backend/pyproject.toml)
- Frontend: [frontend/package.json](frontend/package.json)

Dependency updates are automated with GitHub Dependabot using `.github/dependabot.yml`.

## Quick Start

### Backend

1. Install dependencies:
   ```powershell
   cd backend
   pip install -U pip
   python -m pip install -e .
   ```
2. Create or update `backend/.env` with a valid `DATABASE_URL`.
3. Start the backend server:
   ```powershell
   cd backend
   .venv\Scripts\activate
   python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

### Frontend

1. Install dependencies:
   ```powershell
   cd frontend
   npm install
   ```
2. Start the client:
   ```powershell
   npm run dev -- --host 0.0.0.0 --port 5173
   ```

### Using Docker Compose

```powershell
docker compose up --build
```

## API Documentation

Once the backend is running, visit:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI Schema**: http://localhost:8000/openapi.json

### Key Endpoints

- `POST /clients/register` - Register a new client
- `GET /tests/discover` - Discover available tests
- `POST /runs` - Start a new test run
- `GET /runs/{id}/logs` - Get real-time logs for a run
- `GET /runs/{id}/reports/{type}` - Get generated reports
- `GET /metrics` - Get system metrics

## Development

### Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL (optional, defaults to SQLite)

### Backend Development

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e .
cp .env.example .env  # Configure your settings
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend Development

```bash
cd frontend
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

### Testing

```bash
# Backend tests
cd backend
pytest tests/ -v

# Frontend tests
cd frontend
npm test
```

## Deployment

1. Build and push Docker images:
   ```bash
   docker build -t dvp-backend:latest ./backend
   docker build -t dvp-frontend:latest ./frontend
   docker push dvp-backend:latest
   docker push dvp-frontend:latest
   ```

2. Update SMTP credentials in `k8s/smtp-secret.yaml`

3. Deploy to Kubernetes:
   ```bash
   kubectl apply -k k8s/
   ```

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Commit your changes: `git commit -m 'Add amazing feature'`
4. Push to the branch: `git push origin feature/amazing-feature`
5. Open a Pull Request

### Development Guidelines

- Follow PEP 8 for Python code
- Use TypeScript strict mode for frontend code
- Write tests for new features
- Update documentation as needed
- Ensure all tests pass before submitting PR

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

For questions or issues:
- Create an issue on GitHub
- Check the documentation in the `docs/` directory
- Review the API documentation at `/docs` when running locally

## Project Structure

- `backend/app` — FastAPI app, SQLAlchemy models, service layer
- `frontend/src` — React + TypeScript UI (test selection, run status, logs, reports)
- `tests/` — pytest test suites for discovery and execution
- `docs/` — Architecture, requirements, and user guide
- `k8s/` — Kubernetes deployment manifests
- `setup_scripts/` — Pre-run environment checks and validation
- `teardown_scripts/` — Post-run cleanup and archival

