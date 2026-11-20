import sqlite3
import pytest
from pathlib import Path
from guard.shop_ai import ShopAIAssistant

DB_PATH = "data/test_raw.db"


@pytest.fixture(autouse=True)
def setup_test_db():
    Path("data").mkdir(exist_ok=True)
    if Path(DB_PATH).exists():
        try:
            Path(DB_PATH).unlink()
        except OSError:
            pass

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE raw_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            level TEXT NOT NULL,
            source_ip TEXT,
            username TEXT,
            message TEXT NOT NULL
        )
        """
    )
    cursor.execute(
        """
        INSERT INTO raw_logs (timestamp, level, source_ip, username, message)
        VALUES 
            ('2026-11-20T10:00:00Z', 'INFO', '192.168.1.10', 'alice', 'User alice logged in successfully'),
            ('2026-11-20T10:05:00Z', 'WARNING', '192.168.1.50', 'admin_backup', 'Login failed for admin_backup: invalid password'),
            ('2026-11-20T10:06:00Z', 'ERROR', '192.168.1.50', 'admin_backup', 'Login failed: connection closed')
        """
    )
    conn.commit()
    conn.close()
    yield
    try:
        if Path(DB_PATH).exists():
            Path(DB_PATH).unlink()
    except OSError:
        pass


def test_shop_ai_local_tools():
    ai = ShopAIAssistant(raw_db_path=DB_PATH)

    # 1. Test search_raw_logs tool
    results = ai.search_raw_logs(query="logged in", minutes=600000)
    assert len(results) == 1
    assert results[0]["username"] == "alice"
    assert results[0]["source_ip"] == "192.168.1.10"

    # 2. Test recent_auth_failures tool
    failures = ai.recent_auth_failures(minutes=600000)
    assert len(failures) == 2
    assert failures[0]["username"] == "admin_backup"
    assert failures[0]["source_ip"] == "192.168.1.50"
