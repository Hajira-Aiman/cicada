# Demo Shop API (`shop-api`)

Demo e-commerce shop service running on port 7000 (T16).

## Running the Service

Because the folder name contains a hyphen (`shop-api`), run it using either:

```bash
# Option 1: Uvicorn with --app-dir (Recommended)
uvicorn --app-dir shop-api main:app --port 7000 --host 0.0.0.0

# Option 2: Python script execution directly
python shop-api/main.py
```

## Endpoints

- `GET /health` : Health probe returning `status: "ok"`, `service: "shop-api"`, and `uptime_seconds`.
- `POST /auth/login` : User authentication (`username`, `password`). Emits structured log events for login failures or successes.
- `GET /catalog` : Lists product catalog items.
- `POST /cart/checkout` : Processes checkout and logs masked card transactions.
- `POST /chaos/inject-log` : Injects arbitrary text lines into `data/shop-api.log` (e.g., from the Chaos Console / Try-to-leak challenge).

## Logging

Logs are written in JSONL format to `data/shop-api.log` (configurable via `SHOP_LOG_PATH` env var). The Guard's log tailer continuously ingests and scrubs these logs.
