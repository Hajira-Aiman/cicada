import { useLiveStore } from '../stores/liveStore';
import { Incident } from '../types';

export const SAMPLE_INCIDENT: Incident = {
  incident_id: 'inc-0042',
  tenant_id: 'acme',
  title: 'Possible compromise: cryptomining',
  severity: 'critical',
  confidence: 0.85,
  started_at: new Date(Date.now() - 300000).toISOString(),
  affected: ['host-7f3a1b2c', 'shop-api', 'checkout'],
  signals: [
    { evidence_id: 'ev-1', name: 'auth_failure_burst', value: 50.0, baseline: 2.0, z: null, contribution_pct: 35.0 },
    { evidence_id: 'ev-2', name: 'cpu_pct', value: 96.0, baseline: 21.0, z: 7.4, contribution_pct: 40.0 },
    { evidence_id: 'ev-3', name: 'net_out_kbps', value: 900.0, baseline: 40.0, z: 5.1, contribution_pct: 25.0 },
  ],
  reasoning_path: [
    'login burst (50 attempts) detected at 04:10',
    'successful sudo login after failures at 04:11',
    'CPU anomaly (+7.4 sigma) on host-7f3a at 04:12',
    'outbound network spike (+5.1 sigma) at 04:12',
    'kill-chain rule matched: compromise & cryptominer',
  ],
  counterfactual: 'Without the outbound spike this would be a High security incident, not Critical',
  recommendation: {
    action: 'kill_process',
    target: 'proc-1a2b3c4d',
    why: 'Process started immediately following anomalous login; consuming 96% CPU and streaming outbound traffic',
    risk: 'low',
    reversible: true,
    rollback: 'Restart shop-api service if dependent processes drop',
  },
  changes_before: ['proc-1a2b3c4d started by user-7f3a', 'iptables rule added'],
  suppressed_reason: null,
  repeat_count: 1,
  narrative: 'AIOps Engine correlated SSH credential stuffing with an instant CPU and network burst. Single actionable incident created from 47 raw alerts.',
  status: 'open',
};

let demoInterval: any = null;

export function startDemoFeed() {
  const store = useLiveStore.getState();
  store.setMode('SIMULATED');
  store.setConnected(true);
  store.addIncident(SAMPLE_INCIDENT);

  if (demoInterval) clearInterval(demoInterval);

  let seq = 1500;
  demoInterval = setInterval(() => {
    seq++;
    const now = new Date().toISOString();

    // Emit metrics batch
    const cpuVal = 20 + Math.random() * 25 + (Math.random() > 0.8 ? 50 : 0);
    const latencyVal = 40 + Math.random() * 30;

    store.apply({
      event_type: 'metrics_batch',
      tenant_id: 'acme',
      timestamp: now,
      payload: {
        guard_id: 'guard-acme-01',
        source: 'host-7f3a1234',
        metrics: [
          { name: 'cpu_pct', avg: parseFloat(cpuVal.toFixed(1)), max: parseFloat((cpuVal + 5).toFixed(1)), baseline: 21.0, spread: 4.5 },
          { name: 'latency_ms', avg: parseFloat(latencyVal.toFixed(1)), max: parseFloat((latencyVal + 10).toFixed(1)), baseline: 42.0, spread: 8.0 },
          { name: 'net_out_kbps', avg: 45.0, max: 60.0, baseline: 40.0, spread: 6.0 },
          { name: 'mem_pct', avg: 54.0, max: 56.0, baseline: 52.0, spread: 3.0 },
        ],
      },
    });

    // Emit payload receipt
    store.apply({
      event_type: 'payload_receipt',
      tenant_id: 'acme',
      timestamp: now,
      payload: {
        guard_id: 'guard-acme-01',
        payload_id: `pay-${seq}`,
        seq,
        status: 'stored',
        sha256: `sha256:${seq}a1b2c3d4e5f6...`,
        event_time: now,
        received_at: now,
      },
    });

    // Update counters
    store.apply({
      event_type: 'counters',
      tenant_id: 'acme',
      timestamp: now,
      payload: {
        raw_alerts: 54 + (seq % 10),
        incidents: 4,
        flaps_prevented: 15,
      },
    });
  }, 2000);
}

export function stopDemoFeed() {
  if (demoInterval) {
    clearInterval(demoInterval);
    demoInterval = null;
  }
  const store = useLiveStore.getState();
  store.setMode('LIVE');
}
