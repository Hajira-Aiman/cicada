-- scripts/init_postgres.sql
-- Airlock Multi-Database Initialization Schema

-- Database 1: airlock_core
CREATE DATABASE airlock_core;
\c airlock_core;

CREATE TABLE IF NOT EXISTS tenants (
    tenant_id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    assigned_region VARCHAR(16) NOT NULL,
    pinned_policy_hash VARCHAR(128),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS guards (
    guard_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) REFERENCES tenants(tenant_id),
    hmac_secret VARCHAR(256) NOT NULL,
    status VARCHAR(32) DEFAULT 'active',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS users (
    user_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) REFERENCES tenants(tenant_id),
    role VARCHAR(32) NOT NULL, -- 'engineer' or 'customer'
    password_hash VARCHAR(256) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS audit_log (
    event_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64),
    actor VARCHAR(128) NOT NULL,
    action VARCHAR(128) NOT NULL,
    details JSONB,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS leak_counters (
    tenant_id VARCHAR(64) PRIMARY KEY,
    leak_count INT DEFAULT 0,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS region_states (
    region VARCHAR(32) PRIMARY KEY,
    is_paused BOOLEAN DEFAULT FALSE,
    paused_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS reveal_requests (
    request_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    pseudonym VARCHAR(64) NOT NULL,
    requested_by VARCHAR(128) NOT NULL,
    reason TEXT NOT NULL,
    requested_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    status VARCHAR(32) DEFAULT 'pending',
    decided_at TIMESTAMP WITH TIME ZONE,
    decision_reason TEXT
);

CREATE TABLE IF NOT EXISTS action_intents (
    intent_id VARCHAR(64) PRIMARY KEY,
    incident_id VARCHAR(64),
    tenant_id VARCHAR(64) NOT NULL,
    action VARCHAR(64) NOT NULL,
    target VARCHAR(128) NOT NULL,
    risk VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'proposed',
    details JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    approved_by VARCHAR(128),
    expires_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS action_audit (
    event_id VARCHAR(64) PRIMARY KEY,
    intent_id VARCHAR(64),
    actor VARCHAR(128) NOT NULL,
    step VARCHAR(64) NOT NULL,
    details JSONB,
    at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

INSERT INTO region_states (region, is_paused) VALUES ('in', FALSE), ('eu', FALSE)
ON CONFLICT (region) DO NOTHING;

ALTER TABLE tenants ADD COLUMN IF NOT EXISTS pinned_policy_hash VARCHAR(128);

-- Seed initial tenants & guards
INSERT INTO tenants (tenant_id, name, assigned_region, pinned_policy_hash) VALUES
    ('acme', 'Acme Shop A', 'in', 'sha256:v1-default-policy,sha256:ab1289cf001e35a9'),
    ('globex', 'Globex Shop B', 'eu', 'sha256:ab1289cf001e35a9,sha256:v1-default-policy'),
    ('contoso', 'Contoso Organizer', 'in', 'sha256:ab1289cf001e35a9'),
    ('guests', 'Judges Phones', 'eu', 'sha256:v1-default-policy')
ON CONFLICT (tenant_id) DO UPDATE SET pinned_policy_hash = EXCLUDED.pinned_policy_hash;

INSERT INTO guards (guard_id, tenant_id, hmac_secret) VALUES
    ('guard-acme-01', 'acme', 'sec-acme-super-secret-key-2026'),
    ('guard-globex-01', 'globex', 'sec-globex-super-secret-key-2026'),
    ('guard-contoso-01', 'contoso', 'sec-contoso-super-secret-key-2026')
ON CONFLICT (guard_id) DO NOTHING;

-- Seed initial users with scrypt password hashes
INSERT INTO users (user_id, tenant_id, role, password_hash) VALUES
    ('admin', NULL, 'engineer', 'scrypt$c2FsdC1hZG1pbi0yMDI2$S2+LAEdp1XilDF4COmPPTmFtgBRYLbGJCLN/YRBBCed8W6ydmpsBA0eVPGlSOarK7HoNh10X1DK3VgiCAC0a/Q=='),
    ('user-acme', 'acme', 'customer', 'scrypt$c2FsdC1hY21lLTIwMjY=$PcWWqwev1hDgD44VIaMpVfJMao5xJYupDGV/DHm+M0cD32h0apYSxB5bhLGpLF23LEeMQLJskw8yX+3wkTG9MQ=='),
    ('user-globex', 'globex', 'customer', 'scrypt$c2FsdC1nbG9iZXgtMjAyNg==$517FJoycv+sWCUl7NrwXfj4Z7aYH/ublDkR7felDxpvnzX4Ae99zAMRB81H/DlYLz4b1Z3stmkDn65BCvvROMg=='),
    ('user-contoso', 'contoso', 'customer', 'scrypt$c2FsdC1jb250b3NvLTIwMjY=$oxtispFeK2x1FKFQw6CKnGWUakmxOsO+djrmVLAIULC0ekXR2RGTjDn21+Hgcul1yXM1Jyo8kjJyLDmL425udg==')
ON CONFLICT (user_id) DO UPDATE SET password_hash = EXCLUDED.password_hash, role = EXCLUDED.role, tenant_id = EXCLUDED.tenant_id;

-- Limited DB role for AIOps worker
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'aiops_worker') THEN
        CREATE ROLE aiops_worker WITH LOGIN PASSWORD 'aiops_secret_2026';
    END IF;
END
$$;

-- Database 2: airlock_in (India Region)
CREATE DATABASE airlock_in;
\c airlock_in;

CREATE TABLE IF NOT EXISTS payloads (
    payload_id VARCHAR(64) PRIMARY KEY,
    guard_id VARCHAR(64) NOT NULL,
    tenant_id VARCHAR(64) NOT NULL,
    seq BIGINT NOT NULL,
    prev_hash VARCHAR(128) NOT NULL,
    sent_at TIMESTAMP WITH TIME ZONE NOT NULL,
    window_start TIMESTAMP WITH TIME ZONE NOT NULL,
    window_end TIMESTAMP WITH TIME ZONE NOT NULL,
    raw_payload JSONB NOT NULL,
    received_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS metrics (
    id BIGSERIAL PRIMARY KEY,
    payload_id VARCHAR(64) REFERENCES payloads(payload_id),
    tenant_id VARCHAR(64) NOT NULL,
    source VARCHAR(64) NOT NULL,
    name VARCHAR(64) NOT NULL,
    avg DOUBLE PRECISION NOT NULL,
    max DOUBLE PRECISION NOT NULL,
    event_time TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id BIGSERIAL PRIMARY KEY,
    payload_id VARCHAR(64) REFERENCES payloads(payload_id),
    tenant_id VARCHAR(64) NOT NULL,
    source VARCHAR(64) NOT NULL,
    category VARCHAR(64) NOT NULL,
    severity VARCHAR(32) NOT NULL,
    actor VARCHAR(64),
    count INT NOT NULL,
    window_s INT DEFAULT 2,
    event_time TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE IF NOT EXISTS receipts (
    payload_id VARCHAR(64) PRIMARY KEY,
    guard_id VARCHAR(64) NOT NULL,
    sha256 VARCHAR(128) NOT NULL,
    received_at TIMESTAMP WITH TIME ZONE NOT NULL,
    status VARCHAR(32) NOT NULL
);

CREATE TABLE IF NOT EXISTS health_history (
    id BIGSERIAL PRIMARY KEY,
    tenant_id VARCHAR(64),
    source VARCHAR(64),
    state VARCHAR(32),
    old_state VARCHAR(32),
    reasons JSONB,
    at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS health_current (
    tenant_id VARCHAR(64),
    source VARCHAR(64),
    state VARCHAR(32),
    reasons JSONB,
    since TIMESTAMP WITH TIME ZONE,
    flaps_prevented INT DEFAULT 0,
    updated TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY(tenant_id, source)
);

CREATE TABLE IF NOT EXISTS incidents (
    incident_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    body JSONB NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'open',
    started_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS tenant_thresholds (
    tenant_id VARCHAR(64) PRIMARY KEY,
    config JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS feedback (
    alert_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    metric VARCHAR(64),
    source VARCHAR(64),
    at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS aiops_baselines (
    id BIGSERIAL PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    source VARCHAR(64) NOT NULL,
    metric VARCHAR(64) NOT NULL,
    mean DOUBLE PRECISION NOT NULL,
    std DOUBLE PRECISION NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS guard_reconciliation (
    guard_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    sent_count BIGINT DEFAULT 0,
    received_count BIGINT DEFAULT 0,
    duplicate_count BIGINT DEFAULT 0,
    max_seq BIGINT DEFAULT 0,
    last_hash VARCHAR(128),
    gaps JSONB DEFAULT '[]'::jsonb,
    last_seen TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS aiops_alerts (
    alert_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    source VARCHAR(64),
    title VARCHAR(256),
    severity VARCHAR(32),
    body JSONB,
    status VARCHAR(32) DEFAULT 'open',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS aiops_counters (
    tenant_id VARCHAR(64) PRIMARY KEY,
    raw_alerts INT DEFAULT 0,
    incidents INT DEFAULT 0,
    noise_cut_pct REAL DEFAULT 0,
    flaps_prevented INT DEFAULT 0,
    updated TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
GRANT ALL PRIVILEGES ON aiops_counters TO aiops_worker;

CREATE INDEX IF NOT EXISTS idx_payloads_guard_seq ON payloads(guard_id, seq);
CREATE INDEX IF NOT EXISTS idx_metrics_payload ON metrics(payload_id);
CREATE INDEX IF NOT EXISTS idx_events_payload ON events(payload_id);

-- Row-Level Security on tenant_id
ALTER TABLE payloads ENABLE ROW LEVEL SECURITY;
ALTER TABLE metrics ENABLE ROW LEVEL SECURITY;
ALTER TABLE events ENABLE ROW LEVEL SECURITY;
ALTER TABLE health_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE health_current ENABLE ROW LEVEL SECURITY;
ALTER TABLE incidents ENABLE ROW LEVEL SECURITY;
ALTER TABLE aiops_alerts ENABLE ROW LEVEL SECURITY;
ALTER TABLE guard_reconciliation ENABLE ROW LEVEL SECURITY;

ALTER TABLE payloads FORCE ROW LEVEL SECURITY;
ALTER TABLE metrics FORCE ROW LEVEL SECURITY;
ALTER TABLE events FORCE ROW LEVEL SECURITY;
ALTER TABLE health_history FORCE ROW LEVEL SECURITY;
ALTER TABLE health_current FORCE ROW LEVEL SECURITY;
ALTER TABLE incidents FORCE ROW LEVEL SECURITY;
ALTER TABLE aiops_alerts FORCE ROW LEVEL SECURITY;
ALTER TABLE guard_reconciliation FORCE ROW LEVEL SECURITY;
ALTER TABLE aiops_counters ENABLE ROW LEVEL SECURITY;
ALTER TABLE aiops_counters FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation_payloads ON payloads;
CREATE POLICY tenant_isolation_payloads ON payloads FOR ALL USING (
    current_setting('app.current_tenant', true) IS NULL 
    OR current_setting('app.current_tenant', true) = '' 
    OR current_setting('app.current_tenant', true) = 'all' 
    OR tenant_id = current_setting('app.current_tenant', true)
);

DROP POLICY IF EXISTS tenant_isolation_metrics ON metrics;
CREATE POLICY tenant_isolation_metrics ON metrics FOR ALL USING (
    current_setting('app.current_tenant', true) IS NULL 
    OR current_setting('app.current_tenant', true) = '' 
    OR current_setting('app.current_tenant', true) = 'all' 
    OR tenant_id = current_setting('app.current_tenant', true)
);

DROP POLICY IF EXISTS tenant_isolation_events ON events;
CREATE POLICY tenant_isolation_events ON events FOR ALL USING (
    current_setting('app.current_tenant', true) IS NULL 
    OR current_setting('app.current_tenant', true) = '' 
    OR current_setting('app.current_tenant', true) = 'all' 
    OR tenant_id = current_setting('app.current_tenant', true)
);

DROP POLICY IF EXISTS tenant_isolation_health_history ON health_history;
CREATE POLICY tenant_isolation_health_history ON health_history FOR ALL USING (
    current_setting('app.current_tenant', true) IS NULL 
    OR current_setting('app.current_tenant', true) = '' 
    OR current_setting('app.current_tenant', true) = 'all' 
    OR tenant_id = current_setting('app.current_tenant', true)
);

DROP POLICY IF EXISTS tenant_isolation_health_current ON health_current;
CREATE POLICY tenant_isolation_health_current ON health_current FOR ALL USING (
    current_setting('app.current_tenant', true) IS NULL 
    OR current_setting('app.current_tenant', true) = '' 
    OR current_setting('app.current_tenant', true) = 'all' 
    OR tenant_id = current_setting('app.current_tenant', true)
);

DROP POLICY IF EXISTS tenant_isolation_incidents ON incidents;
CREATE POLICY tenant_isolation_incidents ON incidents FOR ALL USING (
    current_setting('app.current_tenant', true) IS NULL 
    OR current_setting('app.current_tenant', true) = '' 
    OR current_setting('app.current_tenant', true) = 'all' 
    OR tenant_id = current_setting('app.current_tenant', true)
);

DROP POLICY IF EXISTS tenant_isolation_aiops_alerts ON aiops_alerts;
CREATE POLICY tenant_isolation_aiops_alerts ON aiops_alerts FOR ALL USING (
    current_setting('app.current_tenant', true) IS NULL 
    OR current_setting('app.current_tenant', true) = '' 
    OR current_setting('app.current_tenant', true) = 'all' 
    OR tenant_id = current_setting('app.current_tenant', true)
);

DROP POLICY IF EXISTS tenant_isolation_guard_recon ON guard_reconciliation;
CREATE POLICY tenant_isolation_guard_recon ON guard_reconciliation FOR ALL USING (
    current_setting('app.current_tenant', true) IS NULL 
    OR current_setting('app.current_tenant', true) = '' 
    OR current_setting('app.current_tenant', true) = 'all' 
    OR tenant_id = current_setting('app.current_tenant', true)
);

DROP POLICY IF EXISTS tenant_isolation_aiops_counters ON aiops_counters;
CREATE POLICY tenant_isolation_aiops_counters ON aiops_counters FOR ALL USING (
    current_setting('app.current_tenant', true) IS NULL 
    OR current_setting('app.current_tenant', true) = '' 
    OR current_setting('app.current_tenant', true) = 'all' 
    OR tenant_id = current_setting('app.current_tenant', true)
);

-- Permissions for AIOps worker role
GRANT CONNECT ON DATABASE airlock_in TO aiops_worker;
GRANT USAGE ON SCHEMA public TO aiops_worker;
GRANT SELECT ON payloads, metrics, events, receipts TO aiops_worker;
GRANT ALL PRIVILEGES ON health_history, health_current, incidents, aiops_alerts, aiops_counters, tenant_thresholds, feedback, guard_reconciliation TO aiops_worker;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO aiops_worker;

-- Database 3: airlock_eu (Europe Region)
CREATE DATABASE airlock_eu;
\c airlock_eu;

CREATE TABLE IF NOT EXISTS payloads (
    payload_id VARCHAR(64) PRIMARY KEY,
    guard_id VARCHAR(64) NOT NULL,
    tenant_id VARCHAR(64) NOT NULL,
    seq BIGINT NOT NULL,
    prev_hash VARCHAR(128) NOT NULL,
    sent_at TIMESTAMP WITH TIME ZONE NOT NULL,
    window_start TIMESTAMP WITH TIME ZONE NOT NULL,
    window_end TIMESTAMP WITH TIME ZONE NOT NULL,
    raw_payload JSONB NOT NULL,
    received_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS metrics (
    id BIGSERIAL PRIMARY KEY,
    payload_id VARCHAR(64) REFERENCES payloads(payload_id),
    tenant_id VARCHAR(64) NOT NULL,
    source VARCHAR(64) NOT NULL,
    name VARCHAR(64) NOT NULL,
    avg DOUBLE PRECISION NOT NULL,
    max DOUBLE PRECISION NOT NULL,
    event_time TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id BIGSERIAL PRIMARY KEY,
    payload_id VARCHAR(64) REFERENCES payloads(payload_id),
    tenant_id VARCHAR(64) NOT NULL,
    source VARCHAR(64) NOT NULL,
    category VARCHAR(64) NOT NULL,
    severity VARCHAR(32) NOT NULL,
    actor VARCHAR(64),
    count INT NOT NULL,
    window_s INT DEFAULT 2,
    event_time TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE IF NOT EXISTS receipts (
    payload_id VARCHAR(64) PRIMARY KEY,
    guard_id VARCHAR(64) NOT NULL,
    sha256 VARCHAR(128) NOT NULL,
    received_at TIMESTAMP WITH TIME ZONE NOT NULL,
    status VARCHAR(32) NOT NULL
);

CREATE TABLE IF NOT EXISTS health_history (
    id BIGSERIAL PRIMARY KEY,
    tenant_id VARCHAR(64),
    source VARCHAR(64),
    state VARCHAR(32),
    old_state VARCHAR(32),
    reasons JSONB,
    at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS health_current (
    tenant_id VARCHAR(64),
    source VARCHAR(64),
    state VARCHAR(32),
    reasons JSONB,
    since TIMESTAMP WITH TIME ZONE,
    flaps_prevented INT DEFAULT 0,
    updated TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY(tenant_id, source)
);

CREATE TABLE IF NOT EXISTS incidents (
    incident_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    body JSONB NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'open',
    started_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS tenant_thresholds (
    tenant_id VARCHAR(64) PRIMARY KEY,
    config JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS feedback (
    alert_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    metric VARCHAR(64),
    source VARCHAR(64),
    at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS aiops_baselines (
    id BIGSERIAL PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    source VARCHAR(64) NOT NULL,
    metric VARCHAR(64) NOT NULL,
    mean DOUBLE PRECISION NOT NULL,
    std DOUBLE PRECISION NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS guard_reconciliation (
    guard_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    sent_count BIGINT DEFAULT 0,
    received_count BIGINT DEFAULT 0,
    duplicate_count BIGINT DEFAULT 0,
    max_seq BIGINT DEFAULT 0,
    last_hash VARCHAR(128),
    gaps JSONB DEFAULT '[]'::jsonb,
    last_seen TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS aiops_alerts (
    alert_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    source VARCHAR(64),
    title VARCHAR(256),
    severity VARCHAR(32),
    body JSONB,
    status VARCHAR(32) DEFAULT 'open',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS aiops_counters (
    tenant_id VARCHAR(64) PRIMARY KEY,
    raw_alerts INT DEFAULT 0,
    incidents INT DEFAULT 0,
    noise_cut_pct REAL DEFAULT 0,
    flaps_prevented INT DEFAULT 0,
    updated TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
GRANT ALL PRIVILEGES ON aiops_counters TO aiops_worker;

CREATE INDEX IF NOT EXISTS idx_payloads_guard_seq ON payloads(guard_id, seq);
CREATE INDEX IF NOT EXISTS idx_metrics_payload ON metrics(payload_id);
CREATE INDEX IF NOT EXISTS idx_events_payload ON events(payload_id);

-- Row-Level Security on tenant_id
ALTER TABLE payloads ENABLE ROW LEVEL SECURITY;
ALTER TABLE metrics ENABLE ROW LEVEL SECURITY;
ALTER TABLE events ENABLE ROW LEVEL SECURITY;
ALTER TABLE health_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE health_current ENABLE ROW LEVEL SECURITY;
ALTER TABLE incidents ENABLE ROW LEVEL SECURITY;
ALTER TABLE aiops_alerts ENABLE ROW LEVEL SECURITY;
ALTER TABLE guard_reconciliation ENABLE ROW LEVEL SECURITY;

ALTER TABLE payloads FORCE ROW LEVEL SECURITY;
ALTER TABLE metrics FORCE ROW LEVEL SECURITY;
ALTER TABLE events FORCE ROW LEVEL SECURITY;
ALTER TABLE health_history FORCE ROW LEVEL SECURITY;
ALTER TABLE health_current FORCE ROW LEVEL SECURITY;
ALTER TABLE incidents FORCE ROW LEVEL SECURITY;
ALTER TABLE aiops_alerts FORCE ROW LEVEL SECURITY;
ALTER TABLE guard_reconciliation FORCE ROW LEVEL SECURITY;
ALTER TABLE aiops_counters ENABLE ROW LEVEL SECURITY;
ALTER TABLE aiops_counters FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation_payloads ON payloads;
CREATE POLICY tenant_isolation_payloads ON payloads FOR ALL USING (
    current_setting('app.current_tenant', true) IS NULL 
    OR current_setting('app.current_tenant', true) = '' 
    OR current_setting('app.current_tenant', true) = 'all' 
    OR tenant_id = current_setting('app.current_tenant', true)
);

DROP POLICY IF EXISTS tenant_isolation_metrics ON metrics;
CREATE POLICY tenant_isolation_metrics ON metrics FOR ALL USING (
    current_setting('app.current_tenant', true) IS NULL 
    OR current_setting('app.current_tenant', true) = '' 
    OR current_setting('app.current_tenant', true) = 'all' 
    OR tenant_id = current_setting('app.current_tenant', true)
);

DROP POLICY IF EXISTS tenant_isolation_events ON events;
CREATE POLICY tenant_isolation_events ON events FOR ALL USING (
    current_setting('app.current_tenant', true) IS NULL 
    OR current_setting('app.current_tenant', true) = '' 
    OR current_setting('app.current_tenant', true) = 'all' 
    OR tenant_id = current_setting('app.current_tenant', true)
);

DROP POLICY IF EXISTS tenant_isolation_health_history ON health_history;
CREATE POLICY tenant_isolation_health_history ON health_history FOR ALL USING (
    current_setting('app.current_tenant', true) IS NULL 
    OR current_setting('app.current_tenant', true) = '' 
    OR current_setting('app.current_tenant', true) = 'all' 
    OR tenant_id = current_setting('app.current_tenant', true)
);

DROP POLICY IF EXISTS tenant_isolation_health_current ON health_current;
CREATE POLICY tenant_isolation_health_current ON health_current FOR ALL USING (
    current_setting('app.current_tenant', true) IS NULL 
    OR current_setting('app.current_tenant', true) = '' 
    OR current_setting('app.current_tenant', true) = 'all' 
    OR tenant_id = current_setting('app.current_tenant', true)
);

DROP POLICY IF EXISTS tenant_isolation_incidents ON incidents;
CREATE POLICY tenant_isolation_incidents ON incidents FOR ALL USING (
    current_setting('app.current_tenant', true) IS NULL 
    OR current_setting('app.current_tenant', true) = '' 
    OR current_setting('app.current_tenant', true) = 'all' 
    OR tenant_id = current_setting('app.current_tenant', true)
);

DROP POLICY IF EXISTS tenant_isolation_aiops_alerts ON aiops_alerts;
CREATE POLICY tenant_isolation_aiops_alerts ON aiops_alerts FOR ALL USING (
    current_setting('app.current_tenant', true) IS NULL 
    OR current_setting('app.current_tenant', true) = '' 
    OR current_setting('app.current_tenant', true) = 'all' 
    OR tenant_id = current_setting('app.current_tenant', true)
);

DROP POLICY IF EXISTS tenant_isolation_guard_recon ON guard_reconciliation;
CREATE POLICY tenant_isolation_guard_recon ON guard_reconciliation FOR ALL USING (
    current_setting('app.current_tenant', true) IS NULL 
    OR current_setting('app.current_tenant', true) = '' 
    OR current_setting('app.current_tenant', true) = 'all' 
    OR tenant_id = current_setting('app.current_tenant', true)
);

DROP POLICY IF EXISTS tenant_isolation_aiops_counters ON aiops_counters;
CREATE POLICY tenant_isolation_aiops_counters ON aiops_counters FOR ALL USING (
    current_setting('app.current_tenant', true) IS NULL 
    OR current_setting('app.current_tenant', true) = '' 
    OR current_setting('app.current_tenant', true) = 'all' 
    OR tenant_id = current_setting('app.current_tenant', true)
);

-- Permissions for AIOps worker role
GRANT CONNECT ON DATABASE airlock_eu TO aiops_worker;
GRANT USAGE ON SCHEMA public TO aiops_worker;
GRANT SELECT ON payloads, metrics, events, receipts TO aiops_worker;
GRANT ALL PRIVILEGES ON health_history, health_current, incidents, aiops_alerts, aiops_counters, tenant_thresholds, feedback, guard_reconciliation TO aiops_worker;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO aiops_worker;
