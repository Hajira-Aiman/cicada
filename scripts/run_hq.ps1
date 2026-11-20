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
# --host 0.0.0.0 so the shop laptop can reach them over the hotspot
Start-Svc "ingest-in" "-m uvicorn hq.ingest.main:app --host 0.0.0.0 --port 8001" @{ REGION = "in" }
Start-Svc "ingest-eu" "-m uvicorn hq.ingest.main:app --host 0.0.0.0 --port 8002" @{ REGION = "eu" }
Start-Svc "worker" "-m hq.aiops.worker" @{ DB_USER = "aiops_worker"; DB_PASSWORD = "aiops_secret_2026" }
Start-Svc "ai" "-m uvicorn hq.ai.service:app --port 8010"
Start-Svc "api" "-m uvicorn hq.api.main:app --host 0.0.0.0 --port 8000"
Start-Sleep 6
Start-Svc "sim" "-m tools.simulate_timeline --tenants globex contoso"
Push-Location web
Start-Process -FilePath "npx.cmd" -ArgumentList "vite --host 0.0.0.0 --port 5173" -WindowStyle Minimized -RedirectStandardOutput "..\logs\web.out.log" -RedirectStandardError "..\logs\web.err.log"
Pop-Location
$ip = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notmatch '^(127|169)' } | Select-Object -First 1).IPAddress
Write-Host "Head office up. This laptop's IP: $ip   UI: http://${ip}:5173   (logs in .\logs)"
