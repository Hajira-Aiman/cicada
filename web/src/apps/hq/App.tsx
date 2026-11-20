import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { TopNav } from '../../features/TopNav';
import { CopilotDrawer } from '../../features/CopilotDrawer';
import { GuardInspector } from '../../features/GuardInspector';
import { OverviewTab } from './pages/OverviewTab';
import { LiveMapTab } from './pages/LiveMapTab';
import { IncidentsTab } from './pages/IncidentsTab';
import { PrivacyTab } from './pages/PrivacyTab';
import { useLiveSocket } from '../../services/liveSocket';
import { useLiveSync } from '../../services/liveSync';

export const HqApp: React.FC = () => {
  useLiveSocket(); // Single live WebSocket connection
  useLiveSync();   // Real REST poller for metrics & baselines

  return (
    <div className="flex h-screen flex-col bg-[#080A10] text-[#D1D5DB] overflow-hidden font-sans">
      <TopNav />
      <main className="flex-1 overflow-auto relative">
        <Routes>
          <Route path="/overview" element={<OverviewTab />} />
          <Route path="/live-map" element={<LiveMapTab />} />
          <Route path="/incidents" element={<IncidentsTab />} />
          <Route path="/privacy" element={<PrivacyTab />} />
          <Route path="*" element={<Navigate to="/overview" replace />} />
        </Routes>
      </main>
      <CopilotDrawer />
      <GuardInspector />
    </div>
  );
};
