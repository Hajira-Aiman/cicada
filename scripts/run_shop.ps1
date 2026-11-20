param (
    [string]$HqIp = "172.17.1.76",
    [switch]$Stop
)

$ErrorActionPreference = "Continue"

if ([string]::IsNullOrWhiteSpace($HqIp) -or $HqIp -eq "HQ_IP") {
    $HqIp = "172.17.1.76"
}

# Stop existing shop processes if requested or starting up fresh
function Stop-PortProcess([int]$targetPort) {
    $conns = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -eq $targetPort }
    foreach ($c in $conns) {
        try {
            Write-Host "Stopping process PID $($c.OwningProcess) on port $targetPort..."
            Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
        } catch {}
    }
}

if ($Stop) {
    Write-Host "Stopping all Airlock Shop services..." -ForegroundColor Yellow
    Stop-PortProcess 7000
    Stop-PortProcess 9000
    Stop-PortProcess 9100
    Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*guard.thin_slice*" } | ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Write-Host "All shop services stopped." -ForegroundColor Green
    return
}

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  AIRLOCK SHOP ENVIRONMENT (Laptop B - Acme / India)     " -ForegroundColor Cyan
Write-Host "  Target Head Office: http://${HqIp}:8001/ingest           " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# Ensure directories exist
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $root
New-Item -ItemType Directory -Force -Path "logs", "data" | Out-Null

# Clean up stale port listeners
Stop-PortProcess 7000
Stop-PortProcess 9000
Stop-PortProcess 9100
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*guard.thin_slice*" } | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}

# Configure Environment Variables
$env:HQ_IP = $HqIp
$ingestUrl = "http://${HqIp}:8001/ingest"
$env:INGEST_URL = $ingestUrl
$env:HQ_INGEST_URL = $ingestUrl
$env:TENANT_ID = "acme"
$env:GUARD_ID = "guard-acme-01"
$env:GUARD_SECRET_KEY = "sec-acme-super-secret-key-2026"
$env:TENANT_SECRET_KEY = "tenant-salt-acme-local-reveal-2026"
$env:SHOP_API_PORT = "7000"
$env:GUARD_PORT = "9000"
$env:CHAOS_PORT = "9100"
$env:PORT = "9100"
$env:SHOP_HEALTH_URL = "http://127.0.0.1:7000/health"
$env:SHOP_LOG_PATH = "data/shop-api.log"
$env:RAW_DB_PATH = "data/raw.db"
$env:OUTBOX_DB_PATH = "data/outbox.db"
$env:REVEAL_DB_PATH = "data/reveal.db"
$env:GUARD_DB_PATH = "data/guard.db"
$env:TIMEZONE = "Asia/Kolkata"

# 1. Start Shop API (Port 7000)
Write-Host "[1/4] Starting Demo Shop API on port 7000..." -ForegroundColor Yellow
Start-Process -FilePath "py" `
    -ArgumentList "-m", "uvicorn", "--app-dir", "shop-api", "main:app", "--port", "7000", "--host", "0.0.0.0" `
    -RedirectStandardOutput "logs/shop_api.out.log" `
    -RedirectStandardError "logs/shop_api.err.log" `
    -WindowStyle Hidden

# 2. Start Guard Local API (Port 9000)
Write-Host "[2/4] Starting Guard Local API on port 9000..." -ForegroundColor Yellow
Start-Process -FilePath "py" `
    -ArgumentList "-m", "uvicorn", "guard.api.server:app", "--port", "9000", "--host", "0.0.0.0" `
    -RedirectStandardOutput "logs/guard_api.out.log" `
    -RedirectStandardError "logs/guard_api.err.log" `
    -WindowStyle Hidden

# 3. Start Chaos Agent (Port 9100)
Write-Host "[3/4] Starting Chaos Agent on port 9100..." -ForegroundColor Yellow
Start-Process -FilePath "py" `
    -ArgumentList "-m", "uvicorn", "chaos.agent:app", "--port", "9100", "--host", "0.0.0.0" `
    -RedirectStandardOutput "logs/chaos.out.log" `
    -RedirectStandardError "logs/chaos.err.log" `
    -WindowStyle Hidden

# 4. Start Guard Collection & Forwarder Loop
Write-Host "[4/4] Starting Guard Collector Loop (target: $env:INGEST_URL)..." -ForegroundColor Yellow
Start-Process -FilePath "py" `
    -ArgumentList "-m", "guard.thin_slice" `
    -RedirectStandardOutput "logs/guard.out.log" `
    -RedirectStandardError "logs/guard.err.log" `
    -WindowStyle Hidden

Write-Host "Waiting 3 seconds for services to initialize..." -ForegroundColor Cyan
Start-Sleep -Seconds 3

# Verify services
Write-Host "`n--- Health Checks ---" -ForegroundColor Cyan
try {
    $hShop = Invoke-RestMethod -Uri "http://localhost:7000/health" -TimeoutSec 3
    Write-Host "✅ Shop API (7000):" ($hShop | ConvertTo-Json -Compress) -ForegroundColor Green
} catch {
    Write-Host "❌ Shop API (7000) failed to respond: $_" -ForegroundColor Red
}

try {
    $hGuard = Invoke-RestMethod -Uri "http://localhost:9000/api/status" -TimeoutSec 3
    Write-Host "✅ Guard API (9000): guard_id=$($hGuard.guard_id) buffer_depth=$($hGuard.buffer_depth) status=$($hGuard.status)" -ForegroundColor Green
} catch {
    Write-Host "❌ Guard API (9000) failed to respond: $_" -ForegroundColor Red
}

try {
    $hChaos = Invoke-RestMethod -Uri "http://localhost:9100/health" -TimeoutSec 3
    Write-Host "✅ Chaos Agent (9100):" ($hChaos | ConvertTo-Json -Compress) -ForegroundColor Green
} catch {
    Write-Host "❌ Chaos Agent (9100) failed to respond: $_" -ForegroundColor Red
}

Write-Host "`nAll shop services running! Check logs in logs\guard.out.log and logs\guard.err.log" -ForegroundColor Green
