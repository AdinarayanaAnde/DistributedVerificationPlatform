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
    subgraph "User Interface"
        A[Web Browser]
        B[CLI Client]
    end
    
    subgraph "Frontend Layer"
        C[React + TypeScript<br/>Port 5173]
        C1[Dashboard]
        C2[Test Tree]
        C3[Log Viewer]
        C4[Reports]
    end
    
    subgraph "API Gateway"
        D[FastAPI Server<br/>Port 8000]
        D1[REST API]
        D2[WebSocket]
    end
    
    subgraph "Business Logic"
        E[Test Runner]
        F[Queue Manager]
        G[Resource Manager]
        H[Report Generator]
    end
    
    subgraph "Execution Layer"
        I[pytest Process 1]
        J[pytest Process 2]
        K[pytest Process N]
    end
    
    subgraph "Data Layer"
        L[(SQLite/PostgreSQL)]
        L1[runs table]
        L2[clients table]
        L3[logs table]
        L4[resources table]
        L5[queue_entries table]
    end
    
    subgraph "File Storage"
        M[Reports Directory]
        M1[HTML Reports]
        M2[JSON Reports]
        M3[JUnit XML]
        M4[Coverage Reports]
        M5[Allure Results]
    end
    
    A --> C
    B --> D
    
    C --> D
    C1 --> D1
    C2 --> D1
    C3 --> D2
    C4 --> D1
    
    D --> E
    D --> F
    D --> G
    D --> H
    
    E --> I
    E --> J
    E --> K
    
    I --> L
    J --> L
    K --> L
    
    E --> M
    H --> M
    
    L --> L1
    L --> L2
    L --> L3
    L --> L4
    L --> L5
    
    M --> M1
    M --> M2
    M --> M3
    M --> M4
    M --> M5
    
    style C fill:#e1f5fe
    style D fill:#f3e5f5
    style E fill:#e8f5e8
    style I fill:#fff3e0
    style L fill:#fce4ec
    style M fill:#f1f8e9
```

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

