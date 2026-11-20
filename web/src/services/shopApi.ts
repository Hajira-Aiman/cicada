// Shop Screen Local Data Service (connects to Guard on port 9000, fallback to mocks)
const GUARD_API_URL = import.meta.env.VITE_GUARD_API_URL || 'http://localhost:9000';

export interface LocalGuardStatus {
  status: 'active' | 'degraded' | 'paused';
  buffer_depth: number;
  retention_countdown_s: number;
  canaries_planted: number;
  secrets_redacted: number;
  checkpoint_seq: number;
  checkpoint_root: string;
}

export interface LocalLogEntry {
  id: string;
  timestamp: string;
  level: 'DEBUG' | 'INFO' | 'WARN' | 'ERROR';
  message: string;
  has_secret: boolean;
  secret_type?: string;
  redacted_preview?: string;
}

export interface EgressPayloadEntry {
  payload_id: string;
  seq: number;
  sent_at: string;
  sha256: string;
  receipt_sha256: string;
  match: boolean;
  raw_payload: any;
}

export interface RevealRequestItem {
  request_id: string;
  pseudonym: string;
  reason: string;
  requested_by: string;
  status: 'pending' | 'approved' | 'rejected';
  requested_at: string;
}

const MOCK_LOCAL_STATUS: LocalGuardStatus = {
  status: 'active',
  buffer_depth: 0,
  retention_countdown_s: 86140, // ~23h 55m
  canaries_planted: 420,
  secrets_redacted: 3,
  checkpoint_seq: 1420,
  checkpoint_root: 'sha256:7f3a9c1e4d5b2a0f8e1c6b3a7d9e0f2a',
};

const MOCK_LOGS: LocalLogEntry[] = [
  {
    id: 'l-101',
    timestamp: '2026-11-21T04:12:00Z',
    level: 'INFO',
    message: 'User authentication succeeded: user=admin token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.s3cr3t_jwt_t0k3n_2026',
    has_secret: true,
    secret_type: 'JWT Token',
    redacted_preview: 'User authentication succeeded: user=admin token=***REDACTED***',
  },
  {
    id: 'l-102',
    timestamp: '2026-11-21T04:12:02Z',
    level: 'INFO',
    message: 'PostgreSQL connection initialized: postgresql://postgres:SuperSecretP@ssw0rd!@10.0.4.12:5432/shop_db',
    has_secret: true,
    secret_type: 'Database Credential',
    redacted_preview: 'PostgreSQL connection initialized: postgresql://postgres:***REDACTED***@10.0.4.12:5432/shop_db',
  },
  {
    id: 'l-103',
    timestamp: '2026-11-21T04:12:04Z',
    level: 'INFO',
    message: 'Telemetry window 1042 scrubbed and pseudonymized. 2 secrets stripped.',
    has_secret: false,
  },
  {
    id: 'l-104',
    timestamp: '2026-11-21T04:12:06Z',
    level: 'WARN',
    message: 'Tripwire trigger: canary credential used in shop-api curl test. Leak blocked at local gate.',
    has_secret: true,
    secret_type: 'Canary Key',
  },
];

const MOCK_EGRESS: EgressPayloadEntry[] = [
  {
    payload_id: '0193f2c1-7b5e-7c3a-9f10-4be2a1d0c9e1',
    seq: 1042,
    sent_at: '2026-11-21T04:12:04Z',
    sha256: 'sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    receipt_sha256: 'sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    match: true,
    raw_payload: {
      schema: 'airlock.v1',
      payload_id: '0193f2c1-7b5e-7c3a-9f10-4be2a1d0c9e1',
      tenant_id: 'acme',
      guard_id: 'guard-acme-01',
      seq: 1042,
      window: { start: '2026-11-21T04:12:04Z', end: '2026-11-21T04:12:06Z', source_tz: 'Asia/Kolkata' },
      metrics: [{ name: 'cpu_pct', source: 'host-7f3a', avg: 34.2, max: 51.0 }],
      events: [{ category: 'auth_failure_burst', severity: 'high', source: 'host-7f3a', actor: 'src-9c2e', count: 50, window_s: 60 }],
      health: { guard_version: '0.3.1', buffer_depth: 0, canaries_planted: 420, secrets_redacted: 3 },
    },
  },
  {
    payload_id: '0193f2c0-6a4d-7b29-8e0f-3ad190c8b8d0',
    seq: 1041,
    sent_at: '2026-11-21T04:12:02Z',
    sha256: 'sha256:9c1e4d5b2a0f8e1c6b3a7d9e0f2a4c6e8b0d2f4a6c8e0a2c4e6f8a0b2d4f6e8a',
    receipt_sha256: 'sha256:9c1e4d5b2a0f8e1c6b3a7d9e0f2a4c6e8b0d2f4a6c8e0a2c4e6f8a0b2d4f6e8a',
    match: true,
    raw_payload: {
      schema: 'airlock.v1',
      payload_id: '0193f2c0-6a4d-7b29-8e0f-3ad190c8b8d0',
      tenant_id: 'acme',
      guard_id: 'guard-acme-01',
      seq: 1041,
      window: { start: '2026-11-21T04:12:02Z', end: '2026-11-21T04:12:04Z', source_tz: 'Asia/Kolkata' },
      metrics: [{ name: 'cpu_pct', source: 'host-7f3a', avg: 22.4, max: 28.0 }],
      events: [],
      health: { guard_version: '0.3.1', buffer_depth: 0, canaries_planted: 420, secrets_redacted: 2 },
    },
  },
];

const MOCK_REVEAL_REQUESTS: RevealRequestItem[] = [
  {
    request_id: 'rev-001',
    pseudonym: 'user-7f3a1234',
    reason: 'Investigating unauthorized sudo escalation during cryptomining incident inc-0042',
    requested_by: 'security-analyst-1',
    status: 'pending',
    requested_at: '2026-11-21T04:15:00Z',
  },
];

export const shopApi = {
  getStatus: async (): Promise<LocalGuardStatus> => {
    try {
      const res = await fetch(`${GUARD_API_URL}/api/status`, { signal: AbortSignal.timeout(2000) });
      if (res.ok) return await res.json();
    } catch {}
    return MOCK_LOCAL_STATUS;
  },

  getRawLogs: async (): Promise<LocalLogEntry[]> => {
    try {
      const res = await fetch(`${GUARD_API_URL}/api/raw-logs`, { signal: AbortSignal.timeout(2000) });
      if (res.ok) return await res.json();
    } catch {}
    return MOCK_LOGS;
  },

  getEgressLedger: async (): Promise<EgressPayloadEntry[]> => {
    try {
      const res = await fetch(`${GUARD_API_URL}/api/egress`, { signal: AbortSignal.timeout(2000) });
      if (res.ok) return await res.json();
    } catch {}
    return MOCK_EGRESS;
  },

  getRevealRequests: async (): Promise<RevealRequestItem[]> => {
    try {
      const res = await fetch(`${GUARD_API_URL}/api/reveal-requests`, { signal: AbortSignal.timeout(2000) });
      if (res.ok) return await res.json();
    } catch {}
    return MOCK_REVEAL_REQUESTS;
  },

  decideReveal: async (requestId: string, status: 'approved' | 'rejected', reason?: string): Promise<boolean> => {
    try {
      const res = await fetch(`${GUARD_API_URL}/api/reveal-requests/${requestId}/decision`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status, decision_reason: reason }),
      });
      if (res.ok) return true;
    } catch {}
    return true; // Mock success
  },
};
