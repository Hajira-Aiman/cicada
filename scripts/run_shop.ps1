# LAPTOP B (shop): run from the repo root:  powershell -ExecutionPolicy Bypass -File scripts\run_shop.ps1 -HqIp 192.168.137.1
# Starts: demo shop API :7000, guard collector, guard local API :9000, chaos agent :9100
param([Parameter(Mandatory = $true)][string]$HqIp)
$py = if (Test-Path "airlock\.venv\Scripts\python.exe") { "airlock\.venv\Scripts\python.exe" } elseif (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }
New-Item -ItemType Directory -Force logs, data | Out-Null
# With certs\hq.crt present (copied from head office) the guard talks HTTPS and trusts only that certificate.
$scheme = "http"
if (Test-Path "certs\hq.crt") { $scheme = "https"; $env:INGEST_CA_CERT = (Resolve-Path "certs\hq.crt").Path }
Write-Host "Guard -> ingest transport: $scheme"
$env:INGEST_URL = "${scheme}://${HqIp}:8001/ingest"   # the guard sends here (India region)
$env:HQ_URL = "http://${HqIp}:8000"              # the guard pulls reveal requests from here
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
Write-Host "Shop up. Open http://${HqIp}:5173/shop.html and http://${HqIp}:5173/chaos.html in a browser on THIS laptop."
