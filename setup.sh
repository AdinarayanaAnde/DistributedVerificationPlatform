#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# DVP Bootstrap — One-command setup for Linux / macOS
# Usage:  ./setup.sh [--skip-certs] [--skip-frontend]
# ─────────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "$0")"

SKIP_CERTS=false
SKIP_FRONTEND=false
for arg in "$@"; do
    case "$arg" in
        --skip-certs)    SKIP_CERTS=true ;;
        --skip-frontend) SKIP_FRONTEND=true ;;
        *) echo "Unknown option: $arg"; exit 1 ;;
    esac
done

step()  { printf '\n\033[36m>> %s\033[0m\n' "$1"; }
ok()    { printf '   \033[32m%s\033[0m\n' "$1"; }
warn()  { printf '   \033[33m%s\033[0m\n' "$1"; }

# ── 1. Prerequisites ───────────────────────────────────────────────────
step "Checking prerequisites"

if ! command -v python3 &>/dev/null; then
    echo "ERROR: Python 3 not found. Install Python 3.11+ from https://www.python.org/downloads/" >&2; exit 1
fi
PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 11 ]; }; then
    echo "ERROR: Python 3.11+ required (found $PY_VER). Download from https://www.python.org/downloads/" >&2; exit 1
fi
ok "Python $PY_VER"

if [ "$SKIP_FRONTEND" = false ]; then
    if ! command -v node &>/dev/null; then
        echo "ERROR: Node.js not found. Install Node.js 18+ from https://nodejs.org/en/download/" >&2; exit 1
    fi
    NODE_VER=$(node --version | tr -d 'v')
    NODE_MAJOR=$(echo "$NODE_VER" | cut -d. -f1)
    if [ "$NODE_MAJOR" -lt 18 ]; then
        echo "ERROR: Node.js 18+ required (found $NODE_VER). Download from https://nodejs.org/en/download/" >&2; exit 1
    fi
    ok "Node.js $NODE_VER"
fi

# ── 2. Backend venv + deps ─────────────────────────────────────────────
step "Setting up backend"

if [ ! -d "backend/.venv" ]; then
    python3 -m venv backend/.venv
    ok "Created backend/.venv"
else
    ok "backend/.venv already exists"
fi

backend/.venv/bin/python -m pip install --upgrade pip -q
backend/.venv/bin/pip install -e backend -q
ok "Backend dependencies installed"

# ── 3. Environment file ────────────────────────────────────────────────
step "Configuring environment"

if [ ! -f "backend/.env" ]; then
    SECRET=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
    sed -e "s|change-this-to-a-random-secret|$SECRET|" \
        -e "s|postgresql+asyncpg://appuser:apppass@db/dvf|sqlite+aiosqlite:///./data/app.db|" \
        .env.example > backend/.env
    ok "Created backend/.env (SQLite, random SECRET_KEY)"
else
    ok "backend/.env already exists — skipping"
fi

# ── 4. Data directories ───────────────────────────────────────────────
step "Creating data directories"
mkdir -p backend/data reports
ok "backend/data/ and reports/ ready"

# ── 5. Frontend ────────────────────────────────────────────────────────
if [ "$SKIP_FRONTEND" = false ]; then
    step "Setting up frontend"
    (cd frontend && npm install --silent 2>/dev/null)
    ok "Frontend dependencies installed"
fi

# ── 6. HTTPS certs ────────────────────────────────────────────────────
if [ "$SKIP_CERTS" = false ]; then
    step "Generating HTTPS dev certificates"
    if [ -f "certs/cert.pem" ] && [ -f "certs/key.pem" ]; then
        ok "certs/ already exist — skipping (delete certs/ to regenerate)"
    else
        mkdir -p certs
        LAN_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "127.0.0.1")
        [ -z "$LAN_IP" ] && LAN_IP="127.0.0.1"

        if command -v openssl &>/dev/null; then
            openssl req -x509 -newkey rsa:2048 -nodes -days 730 \
                -keyout certs/key.pem -out certs/cert.pem \
                -subj "/CN=DVP Dev" \
                -addext "subjectAltName=DNS:localhost,IP:$LAN_IP,IP:127.0.0.1" \
                2>/dev/null
            ok "HTTPS certs created for localhost + $LAN_IP (valid 2 years)"
        else
            warn "openssl not found — skipping cert generation"
            warn "Install openssl or create certs manually (see README.md)"
        fi
    fi
else
    warn "Skipping HTTPS certs (use --skip-certs to confirm, or run setup.sh again later)"
fi

# ── 7. Summary ─────────────────────────────────────────────────────────
echo ""
echo "============================================================"
echo "  Setup complete! Start the platform:"
echo "============================================================"
echo ""
echo "  Terminal 1 (Backend):"
echo "    cd backend"
echo "    source .venv/bin/activate"
echo "    python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
echo ""
echo "  Terminal 2 (Frontend):"
echo "    cd frontend"
echo "    npm run dev"
echo ""
echo "  Or use Docker:  docker compose up --build"
echo ""
echo "  Then open: http://localhost:5173"
echo ""
