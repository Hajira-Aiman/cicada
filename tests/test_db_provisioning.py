# tests/test_db_provisioning.py
import pytest
from hq.db import init_all_databases, lookup_guard, register_guard, execute_query

def test_database_initialization_and_guard_lookup():
    init_all_databases()
    register_guard("guard-test-01", "globex", "secret-test-key")
    guard = lookup_guard("guard-test-01")
    assert guard is not None
    assert guard["tenant_id"] == "globex"
    assert guard["hmac_secret"] == "secret-test-key"
