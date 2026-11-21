# LAPTOP B (shop): run from the repo root:  powershell -ExecutionPolicy Bypass -File scripts\run_shop.ps1 -HqIp 192.168.137.1
# Starts: demo shop API :7000, guard collector, guard local API :9000, chaos agent :9100
param([string]$HqIp = "192.168.137.1")
$py = if (Test-Path "airlock\.venv\Scripts\python.exe") { "airlock\.venv\Scripts\python.exe" } elseif (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }
New-Item -ItemType Directory -Force logs, data | Out-Null

# Clean up any previous shop, guard, and chaos listeners
function Stop-Port([int]$p) {
    Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue | ForEach-Object {
        Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
    }
}
Stop-Port 7000; Stop-Port 9000; Stop-Port 9100
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*guard.thin_slice*" } | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}

$ingestPort = 8001
$scheme = "http"
if (Test-Path "certs\hq.crt") {
    try {
        $r = [System.Net.HttpWebRequest]::Create("https://${HqIp}:${ingestPort}/health")
        $r.Timeout = 1000
        $r.ServerCertificateValidationCallback = {$true}
        $resp = $r.GetResponse(); $resp.Close()
        $scheme = "https"
        $env:INGEST_CA_CERT = (Resolve-Path "certs\hq.crt").Path
    } catch {
        $scheme = "http"
        Remove-Item "env:INGEST_CA_CERT" -ErrorAction SilentlyContinue
    }
}
Write-Host "Guard -> ingest transport: $scheme (${HqIp}:${ingestPort})"
$env:INGEST_URL = "${scheme}://${HqIp}:${ingestPort}/ingest"
$env:HQ_URL = "http://${HqIp}:8000"
$env:TENANT_ID = "acme"; $env:GUARD_ID = "guard-acme-01"

function Start-Svc($name, $arguments) {
    Start-Process -FilePath $py -ArgumentList $arguments -WindowStyle Minimized -RedirectStandardOutput "logs\$name.out.log" -RedirectStandardError "logs\$name.err.log"
}
Start-Svc "shop" "shop-api\main.py"
Start-Sleep 3
Start-Svc "guard" "-m guard.thin_slice"
Start-Svc "guard-api" "-m guard.api.server"
Start-Svc "chaos" "-m chaos.agent"
Start-Sleep 5
try { Invoke-RestMethod "http://${HqIp}:8000/health" | Out-Null; Write-Host "Head office reachable at $HqIp." } catch { Write-Host "CANNOT reach head office at ${HqIp}:8000. Check the IP and the firewall on laptop A." -ForegroundColor Red }
Write-Host "Shop up. Open http://localhost:5173/shop.html and http://localhost:5173/chaos.html in a browser on THIS laptop."
