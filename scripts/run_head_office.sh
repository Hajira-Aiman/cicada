#!/usr/bin/env bash
# scripts/run_head_office.sh
# Starts Head-Office services:
# 1. PostgreSQL container (airlock_core, airlock_in, airlock_eu)
# 2. Ingest India on port 8001
# 3. Ingest Europe on port 8002
# 4. Head-Office API & WebSocket on port 8000
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$ROOT_DIR"

echo "=== Initializing PostgreSQL databases ==="
"$SCRIPT_DIR/init_postgres.sh"

echo "=== Starting Head-Office Services ==="

# Trap to kill all child background processes on exit
trap 'echo "Stopping services..."; kill $(jobs -p) 2>/dev/null || true' EXIT

# 1. Ingest India (:8001)
REGION=in PORT=8001 .venv/bin/uvicorn hq.ingest.main:app --host 0.0.0.0 --port 8001 &
INGEST_IN_PID=$!
echo "Started Ingest-IN (India) on port 8001 (PID: $INGEST_IN_PID)"

# 2. Ingest Europe (:8002)
REGION=eu PORT=8002 .venv/bin/uvicorn hq.ingest.main:app --host 0.0.0.0 --port 8002 &
INGEST_EU_PID=$!
echo "Started Ingest-EU (Europe) on port 8002 (PID: $INGEST_EU_PID)"

# 3. Head-Office API (:8000)
PORT=8000 .venv/bin/uvicorn hq.api.main:app --host 0.0.0.0 --port 8000 &
HQ_API_PID=$!
echo "Started Head-Office API on port 8000 (PID: $HQ_API_PID)"

echo "=== Head-Office is live. Press Ctrl+C to terminate all services ==="
wait
