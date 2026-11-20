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
  { id: 'region_outage', name: 'India Region Pause', description: 'Pauses India Ingest (:8001); verifies guard local buffer', category: 'infrastructure', endpoint: '/api/regions/in/pause' },
  { id: 'replay_shuffle', name: 'Replay & Shuffle', description: 'Replays old sequence payload and sends out of order', category: 'reliability', endpoint: '/scenarios/replay_shuffle' },
  { id: 'tamper', name: 'Tamper Schema / HMAC', description: 'Mutates payload bytes to trigger cryptographic rejection', category: 'tamper', endpoint: '/scenarios/tamper' },
  { id: 'kill_chain', name: 'Full Kill Chain', description: 'Burst login -> privilege escalation -> CPU spike -> outbound burst', category: 'attack', endpoint: '/scenarios/kill_chain' },
  { id: 'backup_job', name: 'Periodic Backup Job', description: 'Known scheduled pattern (tests suppression without alerts)', category: 'reliability', endpoint: '/scenarios/backup_job' },
  { id: 'restart_app', name: 'App Restart Crash', description: 'Generates service restart event and rapid recovery', category: 'infrastructure', endpoint: '/scenarios/restart_app' },
];

export const chaosApi = {
  triggerScenario: async (scenarioId: string, targetGuard: string): Promise<{ success: boolean; message: string }> => {
    // Check if it's region pause
    if (scenarioId === 'region_outage') {
      try {
        await api.pauseRegion('in');
        return { success: true, message: 'India Region Ingest paused (HTTP 503 active). Guard buffer accumulating.' };
      } catch (err: any) {
        return { success: false, message: err.message };
      }
    }

    try {
      const res = await fetch(`${CHAOS_API_URL}/scenarios/${scenarioId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ duration_s: 20 }),
        signal: AbortSignal.timeout(5000),
      });
      if (res.ok) return { success: true, message: scenarioId === 'kill_chain' ? 'Kill chain running on the shop, takes about 60 s: login burst, CPU, then outbound traffic' : `Scenario ${scenarioId} running for 20 s on ${targetGuard}` };
      return { success: false, message: `Chaos agent refused ${scenarioId}: HTTP ${res.status}` };
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
      await api.unpauseRegion('in');
      await api.unpauseRegion('eu');
      await fetch(`${CHAOS_API_URL}/chaos/reset`, { method: 'POST' });
    } catch {}
    return true;
  },
};
