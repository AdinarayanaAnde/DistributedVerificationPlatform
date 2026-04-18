# ─────────────────────────────────────────────────────────────
# DVP — Makefile for common development tasks
# ─────────────────────────────────────────────────────────────
.DEFAULT_GOAL := help
SHELL := /bin/bash

BACKEND_VENV  := backend/.venv
BACKEND_PY    := $(BACKEND_VENV)/bin/python
BACKEND_PIP   := $(BACKEND_VENV)/bin/pip
FRONTEND_DIR  := frontend

# ── Setup ──────────────────────────────────────────────────────────────

.PHONY: setup
setup: ## One-command full setup (backend + frontend + certs)
	@bash setup.sh

.PHONY: setup-backend
setup-backend: $(BACKEND_VENV) ## Install backend dependencies only
	$(BACKEND_PY) -m pip install --upgrade pip -q
	$(BACKEND_PIP) install -e backend -q
	@echo "Backend ready."

$(BACKEND_VENV):
	python3 -m venv $(BACKEND_VENV)

.PHONY: setup-frontend
setup-frontend: ## Install frontend dependencies only
	cd $(FRONTEND_DIR) && npm install --silent

# ── Run ────────────────────────────────────────────────────────────────

.PHONY: dev
dev: ## Start backend + frontend (requires 2 terminals — prints instructions)
	@echo "Start in two terminals:"
	@echo "  make backend    # Terminal 1"
	@echo "  make frontend   # Terminal 2"

.PHONY: backend
backend: ## Start backend dev server (port 8000)
	cd backend && . .venv/bin/activate && python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

.PHONY: frontend
frontend: ## Start frontend dev server (port 5173)
	cd $(FRONTEND_DIR) && npm run dev

.PHONY: docker
docker: ## Start full stack via Docker Compose
	docker compose up --build

.PHONY: docker-down
docker-down: ## Stop Docker Compose stack
	docker compose down

# ── Test ───────────────────────────────────────────────────────────────

.PHONY: test
test: test-backend test-frontend ## Run all tests

.PHONY: test-backend
test-backend: ## Run backend tests
	cd backend && . .venv/bin/activate && pytest tests/ -v

.PHONY: test-frontend
test-frontend: ## Type-check frontend
	cd $(FRONTEND_DIR) && npx tsc --noEmit

.PHONY: coverage
coverage: ## Run backend tests with coverage report
	cd backend && . .venv/bin/activate && pytest tests/ --cov=app --cov-report=html --cov-report=term-missing

# ── Lint / Format ─────────────────────────────────────────────────────

.PHONY: lint
lint: ## Lint backend (ruff) + frontend (tsc)
	cd backend && . .venv/bin/activate && python -m ruff check app/ || true
	cd $(FRONTEND_DIR) && npx tsc --noEmit

.PHONY: format
format: ## Auto-format backend code
	cd backend && . .venv/bin/activate && python -m ruff format app/

# ── Clean ──────────────────────────────────────────────────────────────

.PHONY: clean
clean: ## Remove caches and build artifacts
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf backend/htmlcov backend/.coverage
	rm -rf $(FRONTEND_DIR)/dist

.PHONY: clean-all
clean-all: clean ## Remove venvs, node_modules, and all caches
	rm -rf $(BACKEND_VENV) $(FRONTEND_DIR)/node_modules

# ── Database ───────────────────────────────────────────────────────────

.PHONY: db-reset
db-reset: ## Reset local SQLite database (WARNING: deletes all data)
	@read -p "This will DELETE the database. Continue? [y/N] " confirm; \
	[ "$$confirm" = "y" ] && rm -f backend/data/app.db && echo "Database reset." || echo "Cancelled."

# ── Help ───────────────────────────────────────────────────────────────

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
