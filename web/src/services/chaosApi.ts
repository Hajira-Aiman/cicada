// Chaos Console Service (connects to Chaos agent on port 9100 / HQ API)
import { api } from './apiClient';

const SHOP_API_URL = import.meta.env.VITE_SHOP_API_URL || 'http://localhost:7000';
const CHAOS_API_URL = import.meta.env.VITE_CHAOS_API_URL || 'http://localhost:9100';

export interface ChaosScenario {
  id: string;
  name: string;
  description: string;
  category: 'attack' | 'infrastructure' | 'reliability' | 'tamper';
  endpoint: string;
}

export const SCENARIOS: ChaosScenario[] = [
  { id: 'cpu_spike', name: 'CPU Spike', description: 'Pushes the shop laptop to about 70% CPU (low priority, so the guard keeps sending)', category: 'attack', endpoint: '/scenarios/cpu_spike' },
  { id: 'latency', name: 'Latency Spike', description: 'Injects 240ms network latency window', category: 'reliability', endpoint: '/scenarios/latency' },
  { id: 'brute_force', name: 'Brute Force Attack', description: 'Emits 50 failed SSH logins in 2 seconds', category: 'attack', endpoint: '/scenarios/brute_force' },
  { id: 'replay_shuffle', name: 'Replay & Shuffle', description: 'Replays old sequence payload and sends out of order', category: 'reliability', endpoint: '/scenarios/replay_shuffle' },
  { id: 'tamper', name: 'Tamper Schema / HMAC', description: 'Mutates payload bytes to trigger cryptographic rejection', category: 'tamper', endpoint: '/scenarios/tamper' },
  { id: 'kill_chain', name: 'Full Kill Chain', description: 'Burst login -> privilege escalation -> CPU spike -> outbound burst', category: 'attack', endpoint: '/scenarios/kill_chain' },
  { id: 'backup_job', name: 'Periodic Backup Job', description: 'Known scheduled pattern (tests suppression without alerts)', category: 'reliability', endpoint: '/scenarios/backup_job' },
];

const describeResult = (id: string, r: any): string => {
  if (r.error) return `Could not reach head office ingest: ${r.error}`;
  if (id === 'tamper') {
    const a = r.byte_flipped, b = r.extra_field;
    return `Altered byte -> HTTP ${a} ${a === 401 ? '(signature rejected)' : ''}; unknown field -> HTTP ${b} ${b === 422 ? '(schema rejected)' : ''}. Nothing was stored.`;
  }
  const codes: number[] = r.status_codes || [];
  const dup = codes.filter((c) => c === 200).length;
  return `${r.replayed} old payloads re-sent out of order -> ${dup} answered "duplicate" (HTTP 200), nothing stored twice.${dup < codes.length ? ` Other codes: ${codes.join(', ')}` : ''}`;
};

export const chaosApi = {
  triggerScenario: async (scenarioId: string, targetGuard: string): Promise<{ success: boolean; message: string }> => {
    // every scenario, region pause included, goes through the shop's chaos agent (it pauses the region at head office with the guard's signature)
    const duration = scenarioId === 'region_outage' ? 20 : 20;
    try {
      const res = await fetch(`${CHAOS_API_URL}/scenarios/${scenarioId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ duration_s: duration, ...(scenarioId === 'region_outage' ? { target: 'in' } : {}) }),
        signal: AbortSignal.timeout(5000),
      });
      if (!res.ok) return { success: false, message: `Chaos agent refused ${scenarioId}: HTTP ${res.status}` };
      const started = await res.json();
      if (scenarioId === 'kill_chain') return { success: true, message: 'Kill chain running on the shop, takes about 60 s: login burst, CPU, then outbound traffic. Watch Incidents & Alerts.' };
      if (scenarioId === 'region_outage') return { success: true, message: 'India ingest paused at head office for 20 s (HTTP 503). The guard buffers, then catches up when it resumes.' };
      // tamper / replay finish in a moment: show what head office answered
      if (scenarioId === 'tamper' || scenarioId === 'replay_shuffle') {
        for (let i = 0; i < 6; i++) {
          await new Promise((r) => setTimeout(r, 700));
          try {
            const act = await (await fetch(`${CHAOS_API_URL}/chaos/active`, { signal: AbortSignal.timeout(3000) })).json();
            const mine = (act.active || []).find((a: any) => a.id === started.id);
            if (mine?.result) return { success: true, message: describeResult(scenarioId, mine.result) };
          } catch { /* keep trying */ }
        }
      }
      const what: Record<string, string> = {
        cpu_spike: 'CPU pushed to about 70% for 20 s. See CPU on the Telemetry View.',
        latency: 'Shop answers 240 ms slower for 20 s. See Latency on the Telemetry View.',
        brute_force: 'Failed logins sent to the shop for 20 s. See the login-failures chart.',
        backup_job: 'Scheduled-job burst started: repeating CPU pulses. Head office learns the pattern.',
        restart_app: 'Shop app stopped and started again: the guard reports app_restarted.',
      };
      return { success: true, message: what[scenarioId] || `Scenario ${scenarioId} running for ${duration} s on ${targetGuard}` };
    } catch {
      return { success: false, message: `Chaos agent not reachable on ${CHAOS_API_URL}. Start it with: python -m chaos.agent` };
    }
  },

  injectLog: async (rawText: string, _targetGuard: string): Promise<{ success: boolean; message: string }> => {
    try {
      const res = await fetch(`${SHOP_API_URL}/chaos/inject-log`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: rawText }),
        signal: AbortSignal.timeout(3000),
      });
      if (res.ok) return { success: true, message: 'Written to the shop log. The guard scrubs it before anything leaves the shop.' };
      return { success: false, message: `Shop API refused the log line: HTTP ${res.status}` };
    } catch {
      return { success: false, message: `Shop API not reachable on ${SHOP_API_URL}.` };
    }
  },

  reset: async (): Promise<boolean> => {
    try {
      await fetch(`${CHAOS_API_URL}/chaos/reset`, { method: 'POST' });
    } catch {}
    return true;
  },
};
