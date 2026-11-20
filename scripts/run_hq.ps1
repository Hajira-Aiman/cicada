# LAPTOP A (head office): Postgres must already be running. Run from the repo root:  powershell -ExecutionPolicy Bypass -File scripts\run_hq.ps1
# Starts: ingest India :8001, ingest Europe :8002, AIOps worker, AI service :8010, API :8000, simulated Globex+Contoso, web UI :5173
$py = if (Test-Path "airlock\.venv\Scripts\python.exe") { "airlock\.venv\Scripts\python.exe" } else { "python" }
$env:DB_PASSWORD = if ($env:DB_PASSWORD) { $env:DB_PASSWORD } else { "airlock_dev" }
New-Item -ItemType Directory -Force logs | Out-Null
function Start-Svc($name, $arguments, $extraEnv = @{}) {
    foreach ($k in $extraEnv.Keys) { Set-Item "env:$k" $extraEnv[$k] }
    Start-Process -FilePath $py -ArgumentList $arguments -WindowStyle Minimized -RedirectStandardOutput "logs\$name.out.log" -RedirectStandardError "logs\$name.err.log"
    foreach ($k in $extraEnv.Keys) { Remove-Item "env:$k" }
}
# --host 0.0.0.0 so the shop laptop can reach them over the hotspot.
# Guard -> ingest is encrypted when certs\hq.crt + certs\hq.key exist (python scripts\make_cert.py); copy hq.crt to the shop laptop's certs\ folder.
$tls = if ((Test-Path "certs\hq.crt") -and (Test-Path "certs\hq.key")) { "--ssl-keyfile certs\hq.key --ssl-certfile certs\hq.crt" } else { "" }
Write-Host ("Ingest transport: " + $(if ($tls) { "HTTPS (certs\hq.crt)" } else { "plain HTTP (run python scripts\make_cert.py to encrypt)" }))
Start-Svc "ingest-in" "-m uvicorn hq.ingest.main:app --host 0.0.0.0 --port 8001 $tls" @{ REGION = "in" }
Start-Svc "ingest-eu" "-m uvicorn hq.ingest.main:app --host 0.0.0.0 --port 8002 $tls" @{ REGION = "eu" }
Start-Svc "worker" "-m hq.aiops.worker" @{ DB_USER = "aiops_worker"; DB_PASSWORD = "aiops_secret_2026" }
Start-Svc "ai" "-m uvicorn hq.ai.service:app --port 8010"
Start-Svc "api" "-m uvicorn hq.api.main:app --host 0.0.0.0 --port 8000"
Start-Sleep 6
Start-Svc "sim" "-m tools.simulate_timeline --tenants globex contoso"
Push-Location web
Start-Process -FilePath "npx.cmd" -ArgumentList "vite --host 0.0.0.0 --port 5173" -WindowStyle Minimized -RedirectStandardOutput "..\logs\web.out.log" -RedirectStandardError "..\logs\web.err.log"
Pop-Location
Write-Host "Head office up (logs in .\logs). This laptop's addresses (use the one on the hotspot Wi-Fi, usually 192.168.x.x / 172.x / 10.x, NOT 127.* or 100.*):"
Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notmatch '^(127|169)' } | ForEach-Object { Write-Host ("  {0}  ({1})  ->  UI http://{0}:5173" -f $_.IPAddress, $_.InterfaceAlias) }
