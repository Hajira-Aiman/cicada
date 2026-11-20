-- scripts/init_postgres.sql
-- Airlock Multi-Database Initialization Schema

-- Database 1: airlock_core
CREATE DATABASE airlock_core;
\c airlock_core;

CREATE TABLE IF NOT EXISTS tenants (
    tenant_id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    assigned_region VARCHAR(16) NOT NULL,
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

-- Seed initial tenants & guards
INSERT INTO tenants (tenant_id, name, assigned_region) VALUES
    ('acme', 'Acme Shop A', 'in'),
    ('globex', 'Globex Shop B', 'eu'),
    ('contoso', 'Contoso Organizer', 'in'),
    ('guests', 'Judges Phones', 'eu')
ON CONFLICT (tenant_id) DO NOTHING;

INSERT INTO guards (guard_id, tenant_id, hmac_secret) VALUES
    ('guard-acme-01', 'acme', 'sec-acme-super-secret-key-2026'),
    ('guard-globex-01', 'globex', 'sec-globex-super-secret-key-2026'),
    ('guard-contoso-01', 'contoso', 'sec-contoso-super-secret-key-2026')
ON CONFLICT (guard_id) DO NOTHING;

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
    event_time TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE IF NOT EXISTS receipts (
    payload_id VARCHAR(64) PRIMARY KEY,
    guard_id VARCHAR(64) NOT NULL,
    sha256 VARCHAR(128) NOT NULL,
    received_at TIMESTAMP WITH TIME ZONE NOT NULL,
    status VARCHAR(32) NOT NULL
);

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
    event_time TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE IF NOT EXISTS receipts (
    payload_id VARCHAR(64) PRIMARY KEY,
    guard_id VARCHAR(64) NOT NULL,
    sha256 VARCHAR(128) NOT NULL,
    received_at TIMESTAMP WITH TIME ZONE NOT NULL,
    status VARCHAR(32) NOT NULL
);
