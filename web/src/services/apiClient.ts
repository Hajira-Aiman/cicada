import { useUiStore } from '../stores/uiStore';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

interface RequestOptions extends RequestInit {
  timeoutMs?: number;
}

export async function apiFetch<T = any>(endpoint: string, options: RequestOptions = {}): Promise<T> {
  const { timeoutMs = 8000, headers = {}, ...rest } = options;
  const token = useUiStore.getState().authToken;

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  const finalHeaders: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(headers as Record<string, string>),
  };

  if (token) {
    finalHeaders['Authorization'] = `Bearer ${token}`;
  }

  try {
    const url = endpoint.startsWith('http') ? endpoint : `${API_BASE_URL}${endpoint}`;
    const response = await fetch(url, {
      ...rest,
      headers: finalHeaders,
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      const errText = await response.text();
      let errMsg = `HTTP ${response.status}: ${response.statusText}`;
      try {
        const errJson = JSON.parse(errText);
        if (errJson.detail) errMsg = errJson.detail;
      } catch {
        if (errText) errMsg = errText;
      }
      throw new Error(errMsg);
    }

    return (await response.json()) as T;
  } catch (err: any) {
    clearTimeout(timeoutId);
    if (err.name === 'AbortError') {
      throw new Error(`Request to ${endpoint} timed out after ${timeoutMs}ms`);
    }
    throw err;
  }
}

export const api = {
  // Authentication
  login: (username: string, password: string) =>
    apiFetch<{ token: string; user_id: string; tenant_id: string | null; role: string }>(
      '/api/login',
      { method: 'POST', body: JSON.stringify({ username, password }) }
    ),

  getTenants: () => apiFetch<{ tenants: { tenant_id: string; name: string; assigned_region: string }[] }>('/api/tenants'),

  // Health and Metrics
  getHealth: () => apiFetch<{ health: any[] }>('/api/health'),
  getMetrics: () => apiFetch<{ metrics: any[] }>('/api/metrics'),
  getEvents: () => apiFetch<{ events: any[] }>('/api/events'),
  getPayloads: () => apiFetch<{ payloads: any[] }>('/api/payloads'),

  // Incidents and Alerts
  getIncidents: () => apiFetch<{ incidents: any[] }>('/api/incidents'),
  getAlerts: () => apiFetch<{ alerts: any[] }>('/api/alerts'),

  // Reconciliation and Checkpoints
  getReconciliation: () => apiFetch<{ reconciliation: any[] }>('/api/reconciliation'),
  getGuardReconciliation: (guardId: string) => apiFetch<any>(`/api/reconciliation/${guardId}`),
  getCheckpoint: (guardId: string, upToSeq?: number) =>
    apiFetch<any>(`/api/checkpoints/${guardId}${upToSeq ? `?up_to_seq=${upToSeq}` : ''}`),
  compareCheckpoint: (guardId: string, upToSeq: number, root: string, hashes?: string[]) =>
    apiFetch<any>('/api/checkpoints/compare', {
      method: 'POST',
      body: JSON.stringify({ guard_id: guardId, up_to_seq: upToSeq, root, hashes }),
    }),

  // Regional control
  getRegionStatus: (region: string) => apiFetch<{ region: string; is_paused: boolean }>(`/api/regions/${region}/status`),
  pauseRegion: (region: string) => apiFetch<any>(`/api/regions/${region}/pause`, { method: 'POST' }),
  unpauseRegion: (region: string) => apiFetch<any>(`/api/regions/${region}/unpause`, { method: 'POST' }),

  // Reveal Requests
  getRevealRequests: (status?: string) =>
    apiFetch<{ reveal_requests: any[] }>(`/reveal-requests${status ? `?status=${status}` : ''}`),
  createRevealRequest: (pseudonym: string, reason: string, tenantId?: string) =>
    apiFetch<any>('/reveal-requests', {
      method: 'POST',
      body: JSON.stringify({ pseudonym, reason, tenant_id: tenantId }),
    }),
  decideRevealRequest: (requestId: string, status: 'approved' | 'rejected', decisionReason?: string) =>
    apiFetch<any>(`/reveal-requests/${requestId}/decision`, {
      method: 'POST',
      body: JSON.stringify({ status, decision_reason: decisionReason }),
    }),

  // AI Copilot
  aiChat: (question: string) =>
    apiFetch<{ answer: string; evidence_ids: string[] }>('/api/ai/chat', {
      method: 'POST',
      body: JSON.stringify({ question }),
    }),

  // Counters
  getCounters: (tenantId: string) => apiFetch<any>(`/api/counters/${tenantId}`),

  // Feedback
  postFeedback: (alertId: string) =>
    apiFetch<any>('/api/feedback', {
      method: 'POST',
      body: JSON.stringify({ alert_id: alertId }),
    }),
};
