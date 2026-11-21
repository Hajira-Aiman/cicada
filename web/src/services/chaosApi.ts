// Chaos Console Service (connects to Chaos agent on port 9100 / HQ API)
import { api } from './apiClient';

const SHOP_API_URL = import.meta.env.VITE_SHOP_API_URL || 'http://localhost:7000';
export const CHAOS_API_URL =import.meta.env.VITE_CHAOS_API_URL || 'http://localhost:9100';

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
  { id: 'port_scan', name: 'Port Scan', description: 'Network: sequential connection attempts across ports 1-1024', category: 'attack', endpoint: '/scenarios/port_scan' },
  { id: 'data_exfil', name: 'Data Exfil Burst', description: 'Network: large unusual outbound transfer (about 30 Mbps) to an unknown address', category: 'attack', endpoint: '/scenarios/data_exfil' },
  { id: 'crypto_miner', name: 'Crypto-Miner', description: 'Compute: sustained 70% CPU from an unknown process, with steady outbound traffic', category: 'attack', endpoint: '/scenarios/crypto_miner' },
  { id: 'crash_loop', name: 'Service Crash Loop', description: 'Compute: the shop app is killed and restarted every ~8 s', category: 'reliability', endpoint: '/scenarios/crash_loop' },
  { id: 'ransomware', name: 'Ransomware File Churn', description: 'Storage: mass file rewrites and .locked renames, heavy disk writes', category: 'attack', endpoint: '/scenarios/ransomware' },
  { id: 'slow_disk', name: 'Slow Disk / Slow DB', description: 'Storage: disk saturated with synced writes, shop answers 800 ms slower', category: 'reliability', endpoint: '/scenarios/slow_disk' },
  { id: 'http_5xx', name: 'HTTP 5xx Error Storm', description: 'Web app: catalog and checkout return HTTP 500 while customers keep coming', category: 'reliability', endpoint: '/scenarios/http_5xx' },
  { id: 'credential_stuffing', name: 'Credential Stuffing', description: 'Web app: leaked username/password pairs against the shop login, then one success', category: 'attack', endpoint: '/scenarios/credential_stuffing' },
];

const NEW_IDS = new Set(['port_scan', 'data_exfil', 'crypto_miner', 'crash_loop', 'ransomware', 'slow_disk', 'http_5xx', 'credential_stuffing']);
const NO_SIGNAL: Record<string, string> = {
  port_scan: 'The guard has no port-scan metric yet.',
  ransomware: 'The guard has no file-churn metric yet; only disk and network movement show.',
  http_5xx: 'The guard has no HTTP error-rate metric yet; only latency shows.',
  credential_stuffing: 'See the login-failure chart; the guard has no login metric in this readout.',
};

// before -> peak -> after, as the guard measured it on the laptop
const describeReadings = (id: string, r: any): string => {
  const f = (v: any) => (typeof v === 'number' ? Math.round(v * 10) / 10 : '-');
  const rows = (r.shown as string[])
    .filter((k) => k in r.before || k in r.peak)
    .map((k) => `${k} ${f(r.before[k])} -> ${f(r.peak[k])} -> ${f(r.after[k])}`);
  return `Guard readings (before -> peak -> after): ${rows.join('; ') || 'none (guard API not reachable)'}.${NO_SIGNAL[id] ? ' ' + NO_SIGNAL[id] : ''}`;
};

const describeResult =(id: string, r: any): string => {
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
      if (NEW_IDS.has(scenarioId)) {
        // readings come from the guard on the laptop: before, peak during, and 10 s after the scenario
        for (let i = 0; i < Math.ceil(duration / 2) + 12; i++) {
          await new Promise((r) => setTimeout(r, 2000));
          try {
            const rec = await (await fetch(`${CHAOS_API_URL}/chaos/readings/${started.id}`, { signal: AbortSignal.timeout(3000) })).json();
            if (rec.done) return { success: true, message: describeReadings(scenarioId, rec) };
          } catch { /* keep trying */ }
        }
        return { success: false, message: `${scenarioId} started, but the guard's readings never came back (is the guard API on :9000 running?)` };
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
