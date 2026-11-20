# Airlock Demo & Deployment Runbook

This runbook covers the exact instructions for deploying the Airlock Head Office demo stack, configuring HTTPS certificates via `mkcert` over a local mobile hotspot, configuring host and OS firewalls, and securing the databases.

---

## 1. Network Architecture for the Demo

- **Host (LOQ Laptop):** Runs PostgreSQL (internal only), Ingest IN (port 8001), Ingest EU (port 8002), HQ API & Broadcaster (port 8000), Phone Demo & Dashboard (port 8003), and Chaos Agent (port 9100).
- **Network Interface:** Wi-Fi Mobile Hotspot (e.g., `192.168.137.1` or DHCP hotspot subnet).
- **Target Audience:** 3 teammate laptops (Adithya, Hajira, Anisa) + mobile phones connecting to the LOQ hotspot.

---

## 1b. Guard connection security (what the scripts do for you)

- **Encrypted + pinned (guard -> ingest):** `python scripts/make_cert.py` writes `certs/hq.crt` (public, committed so the shop gets it with `git pull`) and `certs/hq.key` (private, git-ignored). `run_hq.ps1` serves ingest over HTTPS when both exist; `run_shop.ps1` switches the guard to HTTPS and trusts only `certs/hq.crt` (`INGEST_CA_CERT`). Regenerating the cert means committing the new `hq.crt` and restarting both laptops' scripts.
- **Signed guard requests:** every guard call to head office other than an ingest payload (reveal pull/decision, action pull/result) carries `X-Airlock-Guard-ID/-Timestamp/-Signature` (HMAC of timestamp, method, path+query, body; see `contracts/request_auth.py`). Anonymous callers get 401, and a guard only ever sees or changes its own tenant.
- **Logins required** to propose/dry-run/approve actions, send feedback, and read baselines, counters and the damage map.
- **Clock skew:** the guard follows head office's clock (learned from ingest's `Date` header), so a laptop with a wrong clock no longer trips the skew alert.
- **CORS** allows localhost and private networks only (hotspot/LAN), not the whole internet.
- **Tests never touch live Postgres:** `tests/conftest.py` selects SQLite; `truncate_all_data` refuses to run on Postgres unless `AIRLOCK_ALLOW_TRUNCATE=1`.

## 2. HTTPS & Certificate Setup with `mkcert`

### Step 2.1: Generate Local CA & Host Certificates on LOQ Laptop

Install `mkcert` on the LOQ laptop:
```bash
# Linux / WSL
sudo apt-get install -y libnss3-tools
curl -JLO "https://dl.filippo.io/mkcert/latest?for=linux/amd64"
chmod +x mkcert-v*-linux-amd64
sudo mv mkcert-v*-linux-amd64 /usr/local/bin/mkcert
mkcert -install

# Or Windows (via Chocolatey / Scoop)
choco install mkcert
mkcert -install
```

Find the Root CA path:
```bash
mkcert -CAROOT
# Outputs path containing rootCA.pem and rootCA-key.pem
```

Generate the certificates for LOQ's hotspot IP and hostnames:
```bash
mkdir -p certs
mkcert -key-file certs/key.pem -cert-file certs/cert.pem \
    "192.168.137.1" "loq.local" "airlock.local" "localhost" "127.0.0.1"
```

### Step 2.2: Distribute & Install Root CA on Other Laptops

Copy `rootCA.pem` to the other 3 laptops:

- **Windows Laptop:**
  Run in Administrator PowerShell:
  ```powershell
  certutil -addstore -f "ROOT" rootCA.pem
  ```

- **macOS Laptop:**
  ```bash
  sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain rootCA.pem
  ```

- **Linux Laptop:**
  ```bash
  sudo cp rootCA.pem /usr/local/share/ca-certificates/airlock-ca.crt
  sudo update-ca-certificates
  ```

### Step 2.3: Install Root CA on Mobile Phones

1. Host `rootCA.pem` briefly on a simple HTTP server or send via AirDrop / Local Share.
2. **iOS (iPhone):**
   - Open `rootCA.pem` in Safari -> "Profile Downloaded".
   - Settings -> Profile Downloaded -> Tap **Install**.
   - Settings -> General -> About -> **Certificate Trust Settings** -> Toggle ON **Full Trust for Root Certificates**.
3. **Android:**
   - Settings -> Security (or Security & Privacy) -> More security settings -> Encryption & credentials.
   - Tap **Install a certificate** -> **CA certificate** -> "Install anyway".
   - Select `rootCA.pem`.

---

## 3. Starting Services with HTTPS

Set environment variables or launch with flags:

```bash
# 1. Start HQ API (port 8000)
uvicorn hq.api.main:app --host 0.0.0.0 --port 8000 \
    --ssl-keyfile certs/key.pem --ssl-certfile certs/cert.pem

# 2. Start Ingest IN (port 8001)
REGION=in PORT=8001 uvicorn hq.ingest.main:app --host 0.0.0.0 --port 8001 \
    --ssl-keyfile certs/key.pem --ssl-certfile certs/cert.pem

# 3. Start Ingest EU (port 8002)
REGION=eu PORT=8002 uvicorn hq.ingest.main:app --host 0.0.0.0 --port 8002 \
    --ssl-keyfile certs/key.pem --ssl-certfile certs/cert.pem
```

Alternatively, export `SSL_KEYFILE=certs/key.pem` and `SSL_CERTFILE=certs/cert.pem` and run `.venv/bin/python -m hq.api.main` / `hq.ingest.main`.

---

## 4. Windows Firewall Configuration

Run the following in Administrator PowerShell on the LOQ laptop:

```powershell
# Allow inbound TCP on ports 8000, 8001, 8002, 8003
New-NetFirewallRule -DisplayName "Airlock Demo Web & Ingest" \
    -Direction Inbound -LocalPort 8000,8001,8002,8003 -Protocol TCP -Action Allow

# STRICT SECURITY: Ensure Postgres port 5432 is NEVER exposed to the external network
# Verify Docker port binding is bound only to 127.0.0.1 or internal docker network:
# docker run -d --name airlock-postgres -p 127.0.0.1:5432:5432 postgres:16-alpine
Get-NetFirewallRule -DisplayName "*Postgres*" | Disable-NetFirewallRule
```

---

## 5. Verification Commands

From any of the 3 client laptops connected to LOQ's hotspot:

```bash
# Verify Ingest IN over HTTPS with zero warnings
curl -fsSL https://192.168.137.1:8001/health

# Verify Ingest EU over HTTPS
curl -fsSL https://192.168.137.1:8002/health

# Verify HQ API over HTTPS
curl -fsSL https://192.168.137.1:8000/health

# Verify Postgres port 5432 is NOT accessible externally (must time out / connection refused)
nc -zv -w 2 192.168.137.1 5432
# Expected: Connection timed out or Connection refused
```

---

## 6. Chaos Agent (T11) & Network Traffic Emulation (`tc netem`)

The chaos agent runs on port 9100 (`uvicorn chaos.agent:app --host 0.0.0.0 --port 9100`) and triggers real host and network effects.

### Network Latency & Packet Loss Injection via `tc netem`:
To inject network latency and loss on the mobile hotspot or loopback interface:
```bash
# Inject 450ms delay and 3% packet loss
sudo /usr/sbin/tc qdisc add dev lo root netem delay 450ms loss 3%

# Revert / delete rule
sudo /usr/sbin/tc qdisc del dev lo root
```

Triggering via Chaos Agent:
```bash
# CPU spike (burns 1 core at 100% for 15s)
curl -X POST http://localhost:9100/scenarios/cpu_spike -H "Content-Type: application/json" -d '{"duration_s": 15}'

# Network latency & loss
curl -X POST http://localhost:9100/scenarios/latency -H "Content-Type: application/json" -d '{"duration_s": 20, "params": {"delay_ms": 450, "loss_pct": 3}}'

# Region outage (pauses India region ingestion)
curl -X POST http://localhost:9100/scenarios/region_outage -H "Content-Type: application/json" -d '{"duration_s": 30, "target": "in"}'
```
