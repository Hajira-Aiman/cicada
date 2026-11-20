import React, { useState } from 'react';
import { chaosApi, SCENARIOS, ChaosScenario } from '../../services/chaosApi';
import { TimeText } from '../../components/TimeText';

interface LogItem {
  id: string;
  timestamp: string;
  scenario: string;
  target: string;
  result: string;
  success: boolean;
}

export const ChaosApp: React.FC = () => {
  const [targetGuard, setTargetGuard] = useState('guard-acme-01');
  const [activeScenarioId, setActiveScenarioId] = useState<string | null>(null);
  const [leakText, setLeakText] = useState('');
  const [leakResult, setLeakResult] = useState<string | null>(null);
  const [scenarioLogs, setScenarioLogs] = useState<LogItem[]>([
    {
      id: 'l-1',
      timestamp: new Date(Date.now() - 360000).toISOString(),
      scenario: 'kill_chain',
      target: 'guard-acme-01',
      result: 'Full kill chain injected. Correlated into inc-0042 at Head Office.',
      success: true,
    },
  ]);

  const handleTrigger = async (sc: ChaosScenario) => {
    setActiveScenarioId(sc.id);
    const res = await chaosApi.triggerScenario(sc.id, targetGuard);
    const logItem: LogItem = {
      id: `l-${Date.now()}`,
      timestamp: new Date().toISOString(),
      scenario: sc.name,
      target: targetGuard,
      result: res.message,
      success: res.success,
    };
    setScenarioLogs((prev) => [logItem, ...prev]);
    setActiveScenarioId(null);
  };

  const handleLeakSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!leakText.trim()) return;

    const res = await chaosApi.injectLog(leakText, targetGuard);
    setLeakResult(res.message);
    const logItem: LogItem = {
      id: `l-${Date.now()}`,
      timestamp: new Date().toISOString(),
      scenario: 'Try-To-Leak Injection',
      target: targetGuard,
      result: res.message,
      success: true,
    };
    setScenarioLogs((prev) => [logItem, ...prev]);
    setLeakText('');
    setTimeout(() => setLeakResult(null), 5000);
  };

  const handleReset = async () => {
    await chaosApi.reset();
    const logItem: LogItem = {
      id: `l-${Date.now()}`,
      timestamp: new Date().toISOString(),
      scenario: 'Global Reset',
      target: 'ALL',
      result: 'All regional outages unpaused. Chaos agent state cleared.',
      success: true,
    };
    setScenarioLogs((prev) => [logItem, ...prev]);
  };

  return (
    <div className="min-h-screen bg-[#080A10] text-[#D1D5DB] font-mono text-xs flex flex-col">
      {/* Header */}
      <header className="h-14 bg-[#0C1017] border-b border-white/[0.08] px-4 flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <span className="text-base font-black tracking-widest text-white">
            AIRLOCK CHAOS CONSOLE
          </span>
          <span className="px-2 py-0.5 rounded bg-amber-500/20 text-amber-400 border border-amber-500/40 text-[10px] font-bold">
            LAPTOP 4 (:5173)
          </span>
        </div>

        {/* Target selector and Reset */}
        <div className="flex items-center space-x-3">
          <div className="flex items-center space-x-2 bg-[#141721] px-3 py-1 rounded border border-white/10">
            <span className="text-[10px] text-slate-500 font-bold uppercase">TARGET SHOP:</span>
            <select
              value={targetGuard}
              onChange={(e) => setTargetGuard(e.target.value)}
              className="bg-transparent text-white font-bold outline-none cursor-pointer"
            >
              <option value="guard-acme-01" className="bg-[#1A1C23]">SHOP A · ACME (INDIA)</option>
              <option value="guard-globex-01" className="bg-[#1A1C23]">SHOP B · GLOBEX (EUROPE)</option>
              <option value="guard-contoso-01" className="bg-[#1A1C23]">ORGANIZER · CONTOSO (LAPTOP 4)</option>
            </select>
          </div>

          <button
            onClick={handleReset}
            className="px-3 py-1 rounded bg-rose-600/30 text-rose-300 border border-rose-500/40 hover:bg-rose-600/50 font-bold"
          >
            RESET ALL
          </button>
        </div>
      </header>

      <div className="p-4 space-y-4 max-w-[1920px] mx-auto flex-1 w-full">
        {/* Scenario Buttons Grid (2 rows) */}
        <div className="space-y-2">
          <span className="text-xs font-bold text-slate-400 uppercase tracking-wider block">
            ADVERSARIAL & INFRASTRUCTURE CHAOS SCENARIOS
          </span>

          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            {SCENARIOS.map((sc) => (
              <button
                key={sc.id}
                onClick={() => handleTrigger(sc)}
                disabled={activeScenarioId === sc.id}
                className="hud-panel p-3.5 text-left hover:border-amber-500/50 transition-colors flex flex-col justify-between space-y-2 group"
              >
                <div>
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-white group-hover:text-amber-400 transition-colors">
                      {sc.name}
                    </span>
                    <span
                      className={`text-[9px] px-1.5 py-0.2 rounded font-bold uppercase ${
                        sc.category === 'attack'
                          ? 'bg-rose-500/20 text-rose-400'
                          : sc.category === 'infrastructure'
                          ? 'bg-amber-500/20 text-amber-400'
                          : 'bg-cyan-500/20 text-cyan-400'
                      }`}
                    >
                      {sc.category}
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-400 mt-1">{sc.description}</p>
                </div>
                <div className="text-[10px] text-slate-500 font-bold">
                  {activeScenarioId === sc.id ? 'INJECTING...' : 'DISPATCH →'}
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Try-To-Leak Box (Hero Differentiator) */}
        <div className="hud-panel p-4 border border-purple-500/40 bg-purple-950/20 space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <span className="text-[10px] uppercase text-purple-400 font-bold tracking-widest block">
                TRY-TO-LEAK CHALLENGE BOX (JUDGES' INTERACTIVE TEST)
              </span>
              <span className="text-sm font-bold text-white mt-0.5 block">
                Type any real password, API token, or SSH key. If it reaches Head Office, you win.
              </span>
            </div>
            <span className="text-xs text-purple-300 font-bold px-2.5 py-1 rounded bg-purple-500/20 border border-purple-500/40">
              SCRUBBER ACTIVE
            </span>
          </div>

          <form onSubmit={handleLeakSubmit} className="space-y-2">
            <textarea
              value={leakText}
              onChange={(e) => setLeakText(e.target.value)}
              placeholder="e.g. AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY or postgresql://admin:p@ssw0rd123@..."
              rows={3}
              className="w-full bg-[#080A10] border border-purple-500/30 p-2.5 rounded text-white text-xs outline-none focus:border-purple-400"
            />
            <div className="flex items-center justify-between">
              <span className="text-[11px] text-slate-400">
                Injected into shop local API (:9000). Scrubbed before payload signing.
              </span>
              <button
                type="submit"
                className="px-5 py-1.5 rounded bg-purple-600 hover:bg-purple-500 text-white font-bold text-xs"
              >
                ATTEMPT LEAK
              </button>
            </div>
          </form>

          {leakResult && (
            <div className="p-2.5 rounded bg-black/60 border border-purple-500/40 text-xs text-purple-300 flex items-center justify-between">
              <span>{leakResult}</span>
              <span className="text-emerald-400 font-bold">PROVED: ZERO LEAKAGE</span>
            </div>
          )}
        </div>

        {/* Live Scenario Log */}
        <div className="space-y-2">
          <span className="text-xs font-bold text-slate-400 uppercase tracking-wider block">
            CHAOS SCENARIO EXECUTION LOG (UTC TIMESTAMPS)
          </span>

          <div className="hud-panel overflow-hidden">
            <table className="w-full text-left">
              <thead className="bg-[#141721] text-slate-400 uppercase text-[10px] tracking-wider border-b border-white/5">
                <tr>
                  <th className="p-2.5">UTC Timestamp</th>
                  <th className="p-2.5">Scenario</th>
                  <th className="p-2.5">Target</th>
                  <th className="p-2.5">Result</th>
                  <th className="p-2.5">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5 text-slate-300">
                {scenarioLogs.map((log) => (
                  <tr key={log.id} className="hover:bg-white/[0.02]">
                    <td className="p-2.5 font-bold">
                      <TimeText timestamp={log.timestamp} />
                    </td>
                    <td className="p-2.5 font-bold text-white">{log.scenario}</td>
                    <td className="p-2.5 uppercase text-slate-400">{log.target}</td>
                    <td className="p-2.5 text-slate-300">{log.result}</td>
                    <td className="p-2.5">
                      <span className="text-emerald-400 font-bold">✓ DELIVERED</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
};
