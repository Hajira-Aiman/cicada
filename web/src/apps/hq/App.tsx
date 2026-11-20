import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { TopNav } from '../../features/TopNav';
import { SimulatedBanner } from '../../features/SimulatedBanner';
import { CopilotDrawer } from '../../features/CopilotDrawer';
import { GuardInspector } from '../../features/GuardInspector';
import { OverviewTab } from './pages/OverviewTab';
import { LiveMapTab } from './pages/LiveMapTab';
import { FleetTab } from './pages/FleetTab';
import { IncidentsTab } from './pages/IncidentsTab';
import { SecurityTab } from './pages/SecurityTab';
import { PrivacyTab } from './pages/PrivacyTab';
import { ActionsTab } from './pages/ActionsTab';
import { HistoryTab } from './pages/HistoryTab';
import { SettingsTab } from './pages/SettingsTab';
import { useLiveSocket } from '../../services/liveSocket';

export const HqApp: React.FC = () => {
  useLiveSocket(); // Single live WebSocket connection for the application

  return (
    <div className="flex h-screen flex-col bg-[#0B0E14] text-[#D1D5DB] overflow-hidden font-sans">
      <TopNav />
      <SimulatedBanner />
      <main className="flex-1 overflow-auto relative">
        <Routes>
          <Route path="/overview" element={<OverviewTab />} />
          <Route path="/live-map" element={<LiveMapTab />} />
          <Route path="/fleet" element={<FleetTab />} />
          <Route path="/incidents" element={<IncidentsTab />} />
          <Route path="/security" element={<SecurityTab />} />
          <Route path="/privacy" element={<PrivacyTab />} />
          <Route path="/actions" element={<ActionsTab />} />
          <Route path="/history" element={<HistoryTab />} />
          <Route path="/settings" element={<SettingsTab />} />
          <Route path="*" element={<Navigate to="/overview" replace />} />
        </Routes>
      </main>
      <CopilotDrawer />
      <GuardInspector />
    </div>
  );
};
