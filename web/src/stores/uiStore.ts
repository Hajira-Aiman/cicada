import { create } from 'zustand';
import { CameraPreset, Layer, TzMode } from '../types';

interface UiState {
  selectedGuardId: string | null;
  activeTenant: string | 'ALL';
  tzMode: TzMode;
  cameraPreset: CameraPreset;
  activeLayers: Layer[];
  copilotOpen: boolean;
  inspectorOpen: boolean;
  authRole: 'engineer' | 'customer';
  authToken: string | null;
  currentUserId: string | null;

  setSelectedGuardId: (id: string | null) => void;
  setActiveTenant: (t: string | 'ALL') => void;
  setTzMode: (m: TzMode) => void;
  setCameraPreset: (p: CameraPreset) => void;
  toggleLayer: (l: Layer) => void;
  setCopilotOpen: (open: boolean) => void;
  setInspectorOpen: (open: boolean) => void;
  setAuth: (token: string | null, userId: string | null, role: 'engineer' | 'customer', tenantId?: string) => void;
  logout: () => void;
}

export const useUiStore = create<UiState>((set) => ({
  selectedGuardId: 'guard-acme-01',
  activeTenant: 'ALL',
  tzMode: 'UTC',
  cameraPreset: 'OVERVIEW',
  activeLayers: ['HEALTH', 'PAYLOAD', 'RECEIPT', 'BUFFER', 'LOCAL', 'STATS'],
  copilotOpen: false,
  inspectorOpen: false,
  authRole: 'engineer',
  authToken: null,
  currentUserId: 'admin',

  setSelectedGuardId: (id) => set({ selectedGuardId: id }),
  setActiveTenant: (t) => set({ activeTenant: t }),
  setTzMode: (m) => set({ tzMode: m }),
  setCameraPreset: (p) => set({ cameraPreset: p }),
  toggleLayer: (l) =>
    set((s) => ({
      activeLayers: s.activeLayers.includes(l)
        ? s.activeLayers.filter((x) => x !== l)
        : [...s.activeLayers, l],
    })),
  setCopilotOpen: (open) => set({ copilotOpen: open }),
  setInspectorOpen: (open) => set({ inspectorOpen: open }),
  setAuth: (token, userId, role, tenantId) =>
    set({
      authToken: token,
      currentUserId: userId,
      authRole: role,
      activeTenant: role === 'customer' && tenantId ? tenantId : 'ALL',
    }),
  logout: () =>
    set({
      authToken: null,
      currentUserId: null,
      authRole: 'engineer',
      activeTenant: 'ALL',
    }),
}));
