export type TzMode = 'UTC' | 'VIEWER' | 'SHOP';
export type CameraPreset = 'OVERVIEW' | 'GATE' | 'SHOP_A' | 'HEAD_OFFICE';
export type Layer = 'HEALTH' | 'PAYLOAD' | 'RECEIPT' | 'BUFFER' | 'LOCAL' | 'STATS';
export type HealthState = 'Excellent' | 'Good' | 'Fair' | 'Poor' | 'Offline';
export type SeverityLevel = 'info' | 'low' | 'medium' | 'high' | 'critical';

export interface GuardInfo {
  guard_id: string;
  tenant_id: string;
  source: string;
  region: 'in' | 'eu';
  state: HealthState;
  reasons: string[];
  since: string;
  last_seen: string;
  guard_version: string;
  guard_cpu_pct: number;
  guard_mem_mb: number;
  buffer_depth: number;
  config_ok: boolean;
  canaries_planted: number;
  secrets_redacted: number;
  flaps_prevented: number;
  policy_hash: string;
}

export interface MetricDataPoint {
  id?: number;
  name: string;
  source: string;
  tenant_id: string;
  avg: number;
  max: number;
  event_time: string; // ISO-8601 UTC
  baseline?: number;
  spread?: number;
  is_anomaly?: boolean;
}

export interface SignalEvidence {
  evidence_id: string;
  name: string;
  value: number;
  baseline: number;
  z: number | null;
  contribution_pct: number;
}

export interface IncidentRecommendation {
  action: 'kill_process' | 'restart_service' | 'block_source' | 'block_ip' | 'dry_run' | 'investigate';
  target: string;
  why: string;
  risk: 'low' | 'medium' | 'high';
  reversible: boolean;
  rollback: string;
}

export interface Incident {
  incident_id: string;
  tenant_id: string;
  title: string;
  severity: SeverityLevel;
  confidence: number;
  started_at: string;
  affected: string[];
  signals: SignalEvidence[];
  reasoning_path: string[];
  counterfactual: string | null;
  recommendation?: IncidentRecommendation;
  changes_before: string[];
  suppressed_reason: string | null;
  repeat_count: number;
  narrative?: string;
  status: 'open' | 'investigating' | 'mitigated' | 'resolved';
}

export interface Alert {
  alert_id: string;
  tenant_id: string;
  source: string;
  title: string;
  severity: SeverityLevel;
  body: string;
  created_at: string;
  status: 'open' | 'suppressed' | 'resolved';
}

export interface PayloadReceiptEvent {
  guard_id: string;
  payload_id: string;
  seq: number;
  status: 'stored' | 'duplicate' | 'rejected';
  reason?: string;
  sha256?: string;
  event_time: string;
  received_at: string;
}

export interface CheckpointInfo {
  guard_id: string;
  up_to_seq: number;
  root: string;
  match: boolean;
  first_differing_seq?: number | null;
}

export interface ActionRecord {
  action_id: string;
  tenant_id: string;
  action: string;
  target: string;
  state: 'proposed' | 'dry_run' | 'approved' | 'executed' | 'rolled_back';
  result?: string;
  requested_by: string;
  approved_by?: string;
  at: string;
  rollback_window_s: number;
  remaining_s?: number;
}

export interface ReconciliationRow {
  guard_id: string;
  tenant_id: string;
  sent_count: number;
  received_count: number;
  duplicate_count: number;
  max_seq: number;
  last_hash: string;
  gaps: any[];
  last_seen: string;
}

export interface Counters {
  raw_alerts: number;
  incidents: number;
  flaps_prevented: number;
  canaries_planted: number;
  leaks_detected: number;
  duplicates_blocked: number;
}
