// Shop Screen Local Data Service: talks to the shop's own Guard API on port 9000 only. No mock data: if the guard is down, the screen says so.
const GUARD_API_URL = import.meta.env.VITE_GUARD_API_URL || 'http://localhost:9000';

export async function askShopAI(question: string): Promise<string> {
  const res = await fetch(`${GUARD_API_URL}/api/ask`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question }),
    signal: AbortSignal.timeout(60000),
  });
  if (!res.ok) throw new Error(`Shop AI unavailable (HTTP ${res.status})`);
  return (await res.json()).answer;
}

export interface LocalGuardStatus {
  status: 'active' | 'degraded' | 'paused';
  buffer_depth: number;
  retention_countdown_s: number;
  canaries_planted: number;
  secrets_redacted: number;
  checkpoint_seq: number;
  checkpoint_root: string;
  guard_id?: string;
  tenant_id?: string;
  guard_cpu_pct?: number;
  guard_mem_mb?: number;
  policy_version?: string;
}

export interface LocalLogEntry {
  id: string;
  timestamp: string;
  level: 'DEBUG' | 'INFO' | 'WARN' | 'ERROR';
  message: string;
  has_secret: boolean;
  secret_type?: string;
  redacted_preview?: string;
  parts?: { text: string; secret: boolean }[];   // raw line split around the secrets (shown only on this local screen)
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
  revealed_value?: string;
}

export interface ActionRequestItem {
  intent_id: string;
  action: string;
  target: string;
  status: 'pending' | 'running' | 'done' | 'failed' | 'rolled_back' | 'rejected' | 'expired';
  approved_by?: string;
  details?: { why?: string; impact?: string; [k: string]: any };
  created_at: string;
  expires_at?: string;
}

const SECRETS: [string, RegExp][] = [
  ['Cloud Key', /AKIA[0-9A-Z]{8,}/g], ['Password', /password=\S+/gi], ['Token', /(?:token|secret|access_key|api_key)=\S+/gi],
  ['JWT Token', /eyJ[\w-]+\.[\w-]+\.[\w-]+/g], ['Card Number', /(?:\d{4}[ -]?){3}\d{4}/g],
  ['Database Credential', /\w+:\/\/[^\s:@]+:[^\s@]+@\S+/g],
];

async function get<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${GUARD_API_URL}${path}`, { signal: AbortSignal.timeout(2500) });
    return res.ok ? ((await res.json()) as T) : null;
  } catch { return null; }
}
const split = (text: string, spans: string[]) => {
  let parts = [{ text, secret: false }];
  for (const x of new Set(spans)) {
    parts = parts.flatMap((p) => p.secret ? [p] : p.text.split(x).flatMap((t, i) => (i ? [{ text: x, secret: true }, { text: t, secret: false }] : [{ text: t, secret: false }])));
  }
  return parts.filter((p) => p.text);
};
const iso = (t: number | string) => (typeof t === 'number' ? new Date(t * 1000).toISOString() : t);

export const shopApi = {
  getStatus: async (): Promise<LocalGuardStatus | null> => {
    const [st, cp] = await Promise.all([get<any>('/api/status'), get<any>('/api/checkpoint')]);
    if (!st) return null;
    return { status: st.status, buffer_depth: st.buffer_depth, retention_countdown_s: Math.round(st.retention_countdown_seconds),
      canaries_planted: st.canaries_planted, secrets_redacted: st.secrets_redacted, checkpoint_seq: cp?.up_to_seq ?? st.last_seq,
      checkpoint_root: cp?.root ?? '', guard_id: st.guard_id, tenant_id: st.tenant_id, guard_cpu_pct: st.guard_cpu_pct,
      guard_mem_mb: st.guard_mem_mb, policy_version: st.policy_version };
  },

  getRawLogs: async (): Promise<LocalLogEntry[]> => {
    const r = await get<{ logs: any[] }>('/api/raw-logs?minutes=60');
    return (r?.logs || []).map((l) => {
      const spans = SECRETS.flatMap(([, re]) => l.raw_text.match(re) || []);
      const type = SECRETS.find(([, re]) => (l.raw_text.match(re) || []).length)?.[0];
      let preview = l.raw_text;
      spans.forEach((x: string) => (preview = preview.split(x).join('[REDACTED]')));
      return { id: String(l.id), timestamp: iso(l.timestamp), level: /fail|error|denied/i.test(l.raw_text) ? 'WARN' : 'INFO',
        message: l.raw_text, has_secret: spans.length > 0 || l.source === 'canary-tripwire', secret_type: type,
        redacted_preview: spans.length ? preview : undefined, parts: split(l.raw_text, spans) } as LocalLogEntry;
    });
  },

  getEgressLedger: async (): Promise<EgressPayloadEntry[]> => {
    const r = await get<{ payloads: any[] }>('/api/egress');
    return (r?.payloads || []).map((p) => ({ payload_id: p.payload_id, seq: p.seq, sent_at: p.body?.sent_at || p.receipt_at || '',
      sha256: p.sha256, receipt_sha256: p.status === 'stored' ? p.sha256 : '', match: p.status === 'stored', raw_payload: p.body }));
  },

  getRevealRequests: async (): Promise<RevealRequestItem[]> => {
    const r = await get<{ requests: any[] }>('/api/reveal-requests');
    return (r?.requests || []).map((q) => ({ request_id: q.id, pseudonym: q.pseudonym, reason: q.reason, requested_by: 'head-office',
      status: q.status, requested_at: iso(q.requested_at), revealed_value: q.revealed_value }));
  },

  getActionRequests: async (): Promise<ActionRequestItem[]> => (await get<{ requests: ActionRequestItem[] }>('/api/action-requests'))?.requests || [],

  decideAction: async (intentId: string, approve: boolean): Promise<boolean> => {
    try {
      const res = await fetch(`${GUARD_API_URL}/api/action-requests/${intentId}/${approve ? 'approve' : 'reject'}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
      return res.ok;
    } catch { return false; }
  },

  decideReveal: async (requestId: string, status: 'approved' | 'rejected', reason?: string): Promise<boolean> => {
    try {
      const res = await fetch(`${GUARD_API_URL}/api/reveal-requests/${requestId}/${status === 'approved' ? 'approve' : 'reject'}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ decision_reason: reason }) });
      return res.ok;
    } catch { return false; }
  },
};
