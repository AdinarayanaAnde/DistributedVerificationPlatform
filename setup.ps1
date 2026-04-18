<#
.SYNOPSIS
    One-command bootstrap for Distributed Verification Platform (Windows).
.DESCRIPTION
    Creates Python venv, installs backend/frontend dependencies, copies .env,
    and optionally generates HTTPS dev certs. Run from the project root.
.EXAMPLE
    .\setup.ps1            # Full setup
    .\setup.ps1 -SkipCerts # Skip HTTPS cert generation
#>
param(
    [switch]$SkipCerts,
    [switch]$SkipFrontend
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Write-Step($msg) { Write-Host "`n>> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "   $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "   $msg" -ForegroundColor Yellow }

# ── 1. Check prerequisites ─────────────────────────────────────────────
Write-Step "Checking prerequisites"

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { throw "Python not found. Install Python 3.11+ from https://python.org" }
$pyVer = (python --version 2>&1) -replace 'Python ',''
$pyMajor, $pyMinor = $pyVer.Split('.')[0..1] | ForEach-Object { [int]$_ }
if ($pyMajor -lt 3 -or ($pyMajor -eq 3 -and $pyMinor -lt 11)) {
    throw "Python 3.11+ required (found $pyVer)"
}
Write-Ok "Python $pyVer"

if (-not $SkipFrontend) {
    $node = Get-Command node -ErrorAction SilentlyContinue
    if (-not $node) { throw "Node.js not found. Install Node.js 18+ from https://nodejs.org" }
    $nodeVer = (node --version) -replace 'v',''
    $nodeMajor = [int]($nodeVer.Split('.')[0])
    if ($nodeMajor -lt 18) { throw "Node.js 18+ required (found $nodeVer)" }
    Write-Ok "Node.js $nodeVer"
}

# ── 2. Backend: venv + dependencies ────────────────────────────────────
Write-Step "Setting up backend"

if (-not (Test-Path "backend\.venv")) {
    python -m venv backend\.venv
    Write-Ok "Created backend\.venv"
} else {
    Write-Ok "backend\.venv already exists"
}

& backend\.venv\Scripts\python -m pip install --upgrade pip --quiet
& backend\.venv\Scripts\pip install -e backend --quiet
Write-Ok "Backend dependencies installed"

# ── 3. Environment file ────────────────────────────────────────────────
Write-Step "Configuring environment"

if (-not (Test-Path "backend\.env")) {
    $secretKey = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 32 | ForEach-Object { [char]$_ })
    $envContent = (Get-Content ".env.example" -Raw) `
        -replace 'change-this-to-a-random-secret', $secretKey `
        -replace 'postgresql\+asyncpg://appuser:apppass@db/dvf', 'sqlite+aiosqlite:///./data/app.db'
    Set-Content "backend\.env" -Value $envContent
    Write-Ok "Created backend\.env (SQLite, random SECRET_KEY)"
} else {
    Write-Ok "backend\.env already exists — skipping"
}

# ── 4. Data directories ───────────────────────────────────────────────
Write-Step "Creating data directories"

@("backend\data", "reports") | ForEach-Object {
    if (-not (Test-Path $_)) { New-Item -ItemType Directory -Path $_ -Force | Out-Null }
}
Write-Ok "backend\data\ and reports\ ready"

# ── 5. Frontend ────────────────────────────────────────────────────────
if (-not $SkipFrontend) {
    Write-Step "Setting up frontend"
    Push-Location frontend
    npm install --silent 2>$null
    Pop-Location
    Write-Ok "Frontend dependencies installed"
}

# ── 6. HTTPS certs (optional) ─────────────────────────────────────────
if (-not $SkipCerts) {
    Write-Step "Generating HTTPS dev certificates"

    if ((Test-Path "certs\cert.pem") -and (Test-Path "certs\key.pem")) {
        Write-Ok "certs\ already exist — skipping (delete certs\ to regenerate)"
    } else {
        if (-not (Test-Path "certs")) { New-Item -ItemType Directory -Path "certs" -Force | Out-Null }

        # Detect LAN IP
        $lanIp = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object {
            $_.InterfaceAlias -notmatch 'Loopback' -and $_.IPAddress -notmatch '^169\.'
        } | Select-Object -First 1).IPAddress
        if (-not $lanIp) { $lanIp = "127.0.0.1" }

        $san = "2.5.29.17={text}DNS=localhost&IPAddress=$lanIp&IPAddress=127.0.0.1"
        $cert = New-SelfSignedCertificate `
            -Subject "CN=DVP Dev" `
            -TextExtension @($san) `
            -CertStoreLocation "Cert:\CurrentUser\My" `
            -NotAfter (Get-Date).AddYears(2) `
            -KeyAlgorithm RSA -KeyLength 2048 -HashAlgorithm SHA256 `
            -KeyExportPolicy Exportable

        # Export via PFX → PEM using backend's Python (cryptography is installed)
        $pwd = ConvertTo-SecureString -String "dvp-tmp" -Force -AsPlainText
        Export-PfxCertificate -Cert $cert -FilePath "certs\temp.pfx" -Password $pwd | Out-Null

        & backend\.venv\Scripts\python -c @"
from cryptography.hazmat.primitives.serialization import pkcs12, Encoding, PrivateFormat, NoEncryption
from pathlib import Path
pfx = Path('certs/temp.pfx').read_bytes()
key, cert, _ = pkcs12.load_key_and_certificates(pfx, b'dvp-tmp')
Path('certs/key.pem').write_bytes(key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()))
Path('certs/cert.pem').write_bytes(cert.public_bytes(Encoding.PEM))
Path('certs/temp.pfx').unlink()
"@

        Remove-Item "Cert:\CurrentUser\My\$($cert.Thumbprint)" -ErrorAction SilentlyContinue
        Write-Ok "HTTPS certs created for localhost + $lanIp (valid 2 years)"
    }
} else {
    Write-Warn "Skipping HTTPS certs (use plain HTTP or run setup.ps1 without -SkipCerts later)"
}

# ── 7. Summary ─────────────────────────────────────────────────────────
Write-Host "`n" -NoNewline
Write-Host "=" * 60 -ForegroundColor Green
Write-Host "  Setup complete! Start the platform:" -ForegroundColor Green
Write-Host "=" * 60 -ForegroundColor Green
Write-Host ""
Write-Host "  Terminal 1 (Backend):" -ForegroundColor White
Write-Host "    cd backend" -ForegroundColor Gray
Write-Host "    .\.venv\Scripts\activate" -ForegroundColor Gray
Write-Host "    python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000" -ForegroundColor Gray
Write-Host ""
Write-Host "  Terminal 2 (Frontend):" -ForegroundColor White
Write-Host "    cd frontend" -ForegroundColor Gray
Write-Host "    npm run dev" -ForegroundColor Gray
Write-Host ""
Write-Host "  Or use Docker:  docker compose up --build" -ForegroundColor White
Write-Host ""
Write-Host "  Then open: http://localhost:5173" -ForegroundColor Cyan
Write-Host ""
