import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { TopNav } from '../../features/TopNav';
import { CopilotDrawer } from '../../features/CopilotDrawer';
import { GuardInspector } from '../../features/GuardInspector';
import { OverviewTab } from './pages/OverviewTab';
import { LiveMapTab } from './pages/LiveMapTab';
import { IncidentsTab } from './pages/IncidentsTab';
import { PrivacyTab } from './pages/PrivacyTab';
import { TelemetryTab } from './pages/TelemetryTab';
import { LeakProofTab } from './pages/LeakProofTab';
import { TamperTab } from './pages/TamperTab';
import { useLiveSocket } from '../../services/liveSocket';
import { useLiveSync } from '../../services/liveSync';
import { LoginPage } from '../../features/LoginPage';
import { useUiStore } from '../../stores/uiStore';

export const HqApp: React.FC = () => {
  useLiveSocket(); // Single live WebSocket connection
  useLiveSync();   // Real REST poller for metrics & baselines
  const token = useUiStore((s) => s.authToken);
  if (!token) return <LoginPage />;   // nothing loads without a login

  return (
    <div className="flex h-screen flex-col bg-[#080A10] text-[#D1D5DB] overflow-hidden font-sans">
      <TopNav />
      <main className="flex-1 overflow-auto relative">
        <Routes>
          <Route path="/overview" element={<OverviewTab />} />
          <Route path="/live-map" element={<LiveMapTab />} />
          <Route path="/telemetry" element={<TelemetryTab />} />
          <Route path="/incidents" element={<IncidentsTab />} />
          <Route path="/privacy" element={<PrivacyTab />} />
          <Route path="/leak-proof" element={<LeakProofTab />} />
          <Route path="/tamper" element={<TamperTab />} />
          <Route path="*" element={<Navigate to="/overview" replace />} />
        </Routes>
      </main>
      <CopilotDrawer />
      <GuardInspector />
    </div>
  );
};
