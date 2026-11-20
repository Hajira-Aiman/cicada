# Airlock - Guard & Shop Services

## Demo Shop API (Port 7000)

You can launch the demo shop service with either:

```bash
python shop-api/main.py
```

Or using the Uvicorn CLI:

```bash
uvicorn --app-dir shop-api main:app --port 7000
```

### Endpoints
- `GET /health` - Health and uptime probe
- `POST /auth/login` - User login verification (records credentials in log)
- `GET /catalog` - Security appliances catalog
- `POST /cart/checkout` - Order checkout
- `POST /chaos/inject-log` - Arbitrary log injection for try-to-leak testing

## Guard Telemetry Collector & Airlock Ingest

- Run Guard telemetry collector:
  ```bash
  python -m guard.thin_slice
  ```
- Run Ingest service (India region):
  ```bash
  python -m hq.ingest.main
  ```
