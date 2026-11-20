"""
tools/verify_e2e_ingest.py
End-to-End Proof Verification Script:
1. Starts Regional Ingest IN (port 8003/8001) and EU (port 8002)
2. Runs Guard collection and posts real signed payloads to both endpoints
3. Confirms HTTP 200 receipts
4. Confirms metrics rows stored in database
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import time
import socket
import threading
import uvicorn
from contracts.models import IngestReceipt
from hq.ingest.main import create_ingest_app
from hq.db import init_all_databases, get_sqlite_conn
from guard.thin_slice import GuardThinSlice
from guard.config import GuardConfig


def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


class ServerThread(threading.Thread):
    def __init__(self, app, port):
        super().__init__(daemon=True)
        self.port = port
        self.config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
        self.server = uvicorn.Server(self.config)

    def run(self):
        self.server.run()

    def stop(self):
        self.server.should_exit = True


def main():
    print("Initializing databases...")
    init_all_databases()

    # If port 8001 is occupied by local NPU server, use 8003 for India regional ingest test
    port_in = 8003 if is_port_in_use(8001) else 8001
    port_eu = 8002
    print(f"Starting Ingest IN (port {port_in}) and Ingest EU (port {port_eu})...")

    app_in = create_ingest_app(region="in")
    app_eu = create_ingest_app(region="eu")

    t_in = ServerThread(app_in, port_in)
    t_eu = ServerThread(app_eu, port_eu)

    t_in.start()
    t_eu.start()
    time.sleep(1.5)

    try:
        # 1. Test Guard against Ingest IN (Acme)
        print(f"\n--- Testing Guard -> Ingest IN (port {port_in}) ---")
        cfg_in = GuardConfig()
        cfg_in.TENANT_ID = "acme"
        cfg_in.GUARD_ID = "guard-acme-01"
        cfg_in.GUARD_SECRET_KEY = "sec-acme-super-secret-key-2026"
        cfg_in.REGION_URL = f"http://127.0.0.1:{port_in}/ingest"

        guard_in = GuardThinSlice(cfg=cfg_in)
        p_in, b_in = guard_in.collect_window()
        receipt_in = guard_in.send_payload(p_in, b_in)

        assert receipt_in is not None, "Failed to receive receipt from Ingest IN!"
        assert receipt_in.status == "stored", f"Unexpected status: {receipt_in.status}"
        print(f"✅ Ingest IN Receipt: payload_id={receipt_in.payload_id} sha256={receipt_in.sha256} status={receipt_in.status}")

        # Check DB rows
        conn_in = get_sqlite_conn("airlock_in")
        cur_in = conn_in.cursor()
        cur_in.execute("SELECT name, avg, max FROM metrics WHERE payload_id = ?", (p_in.payload_id,))
        rows_in = cur_in.fetchall()
        print(f"✅ Verified {len(rows_in)} metric rows stored in airlock_in: {[r[0] for r in rows_in]}")
        assert len(rows_in) >= 3

        # 2. Test Guard against Ingest EU (Globex)
        print(f"\n--- Testing Guard -> Ingest EU (port {port_eu}) ---")
        cfg_eu = GuardConfig()
        cfg_eu.TENANT_ID = "globex"
        cfg_eu.GUARD_ID = "guard-globex-01"
        cfg_eu.GUARD_SECRET_KEY = "sec-globex-super-secret-key-2026"
        cfg_eu.REGION_URL = f"http://127.0.0.1:{port_eu}/ingest"
        cfg_eu.TIMEZONE = "Europe/Berlin"

        guard_eu = GuardThinSlice(cfg=cfg_eu)
        p_eu, b_eu = guard_eu.collect_window()
        receipt_eu = guard_eu.send_payload(p_eu, b_eu)

        assert receipt_eu is not None, "Failed to receive receipt from Ingest EU!"
        assert receipt_eu.status == "stored", f"Unexpected status: {receipt_eu.status}"
        print(f"✅ Ingest EU Receipt: payload_id={receipt_eu.payload_id} sha256={receipt_eu.sha256} status={receipt_eu.status}")

        conn_eu = get_sqlite_conn("airlock_eu")
        cur_eu = conn_eu.cursor()
        cur_eu.execute("SELECT name, avg, max FROM metrics WHERE payload_id = ?", (p_eu.payload_id,))
        rows_eu = cur_eu.fetchall()
        print(f"✅ Verified {len(rows_eu)} metric rows stored in airlock_eu: {[r[0] for r in rows_eu]}")
        assert len(rows_eu) >= 3

        print(f"\n🎉 End-to-End Guard & Ingest pipeline verified successfully on live ports {port_in} and {port_eu}!")

    finally:
        t_in.stop()
        t_eu.stop()


if __name__ == "__main__":
    main()
