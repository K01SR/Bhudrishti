import React, { createContext, useContext, useState, useCallback } from 'react';
import { loginRequest, type AuthUser } from '../services/api';

export type Role = 'DISTRICT_VERIFIER' | 'STATE_ADMIN' | 'BUILDER' | 'CITIZEN' | 'PUBLIC' | 'TALUKA_VERIFIER';

const SESSION_KEY = 'bhudrishti.session';

function loadSession(): { token: string; user: AuthUser } | null {
  try {
    const raw = typeof window !== 'undefined' ? window.localStorage.getItem(SESSION_KEY) : null;
    return raw ? (JSON.parse(raw) as { token: string; user: AuthUser }) : null;
  } catch {
    return null;
  }
}

export interface HighlightState {
  category: string;
  ids: string[];
  mode: string;
  label: string;
  /**
   * The query's focus point, in the 3D studio's local scene coordinates, plus
   * the colour the backend asked for. Both are carried so the 2D map views can
   * place the same pointer the 3D view highlights: the scene point has to be
   * converted through the local-to-geo transform before it is any use as a
   * longitude, and dropping it would leave both 2D views inert.
   */
  focusPoint?: [number, number];
  color?: string;
}

export const ROLE_PERMISSIONS: Record<Role, {
  canApprove: boolean;
  canSubmit: boolean;
  canFileObjection: boolean;
  canExport: boolean;
  canViewSensitive: boolean;
  canViewLiDAR: boolean;
  canViewPipelines: boolean;
  canSetPolicy: boolean;
  /**
   * Whether this role may write raw source material into the cadastre through
   * the ingest desk. Ingestion is a reviewer/administrator action on purpose:
   * it changes what the platform holds and what its provenance claims, and a
   * party that is filing a submission must not be able to alter the record it
   * is being filed against. Mirrors the backend's own posture, where every
   * /ingest route is behind a required session.
   */
  canIngest: boolean;
  navItems: string[];
  label: string;
    color: string;
}> = {
  STATE_ADMIN: { canApprove: false, canSubmit: false, canFileObjection: false, canExport: true, canViewSensitive: true, canViewLiDAR: true, canViewPipelines: true, canSetPolicy: true, canIngest: true, navItems: ['home','map','properties','locate','ingest','analytics','audit','settings'], label: 'State Administrator', color: 'purple' },
  DISTRICT_VERIFIER: { canApprove: true, canSubmit: false, canFileObjection: false, canExport: true, canViewSensitive: true, canViewLiDAR: true, canViewPipelines: true, canSetPolicy: false, canIngest: true, navItems: ['home','map','properties','locate','ingest','ulpin','validation','evidence','review','analytics','audit','settings'], label: 'Reviewer (demo)', color: 'blue' },
  TALUKA_VERIFIER: { canApprove: true, canSubmit: false, canFileObjection: false, canExport: true, canViewSensitive: true, canViewLiDAR: true, canViewPipelines: false, canSetPolicy: false, canIngest: true, navItems: ['home','map','properties','locate','ingest','validation','review','settings'], label: 'Taluka Verifier', color: 'sky' },
  BUILDER: { canApprove: false, canSubmit: true, canFileObjection: false, canExport: true, canViewSensitive: false, canViewLiDAR: false, canViewPipelines: false, canSetPolicy: false, canIngest: false, navItems: ['home','map','properties','locate','evidence','settings'], label: 'Builder / Developer', color: 'amber' },
  CITIZEN: { canApprove: false, canSubmit: false, canFileObjection: true, canExport: false, canViewSensitive: false, canViewLiDAR: false, canViewPipelines: false, canSetPolicy: false, canIngest: false, navItems: ['home','map','properties','locate','settings'], label: 'Citizen', color: 'green' },
  PUBLIC: { canApprove: false, canSubmit: false, canFileObjection: false, canExport: false, canViewSensitive: false, canViewLiDAR: false, canViewPipelines: false, canSetPolicy: false, canIngest: false, navItems: ['home','map','properties','locate'], label: 'Public', color: 'gray' },
};

interface AppContextValue {
  role: Role;
  token: string | null;
  user: AuthUser | null;
  permissions: typeof ROLE_PERMISSIONS[Role];
  login: (username: string, password: string) => Promise<AuthUser>;
  logout: () => void;
  highlight: HighlightState | null;
  applyHighlight: (h: HighlightState) => void;
  clearHighlight: () => void;
  mapFocus: string | null;
  setMapFocus: (id: string | null) => void;
  toast: string | null;
  showToast: (msg: string) => void;
}

const AppContext = createContext<AppContextValue | null>(null);

export const AppProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [session, setSession] = useState<{ token: string; user: AuthUser } | null>(loadSession);
  const [highlight, setHighlight] = useState<HighlightState | null>(null);
  const [mapFocus, setMapFocus] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const role: Role = session ? (session.user.role_name as Role) : 'PUBLIC';
  const token = session ? session.token : null;
  const user = session ? session.user : null;

  const login = useCallback(async (username: string, password: string): Promise<AuthUser> => {
    const resp = await loginRequest(username, password);
    const next = { token: resp.access_token, user: resp.user };
    try {
      window.localStorage.setItem(SESSION_KEY, JSON.stringify(next));
    } catch { /* storage unavailable — in-memory session only */ }
    setSession(next);
    setHighlight(null);
    setMapFocus(null);
    return resp.user;
  }, []);

  const logout = useCallback(() => {
    try {
      window.localStorage.removeItem(SESSION_KEY);
    } catch { /* ignore */ }
    setSession(null);
    setHighlight(null);
    setMapFocus(null);
    setToast('Signed out · browsing as Public guest');
  }, []);

  const applyHighlight = useCallback((h: HighlightState) => setHighlight(h), []);
  const clearHighlight = useCallback(() => setHighlight(null), []);

  const showToast = useCallback((msg: string) => {
    setToast(msg);
    window.setTimeout(() => setToast(null), 4200);
  }, []);

  const permissions = ROLE_PERMISSIONS[role];

  return (
    <AppContext.Provider value={{ role, token, user, permissions, login, logout, highlight, applyHighlight, clearHighlight, mapFocus, setMapFocus, toast, showToast }}>
      {children}
    </AppContext.Provider>
  );
};

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp must be used within AppProvider');
  return ctx;
}