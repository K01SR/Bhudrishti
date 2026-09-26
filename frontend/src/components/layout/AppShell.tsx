import React, { useEffect, useState } from 'react';
import { NavLink, Link, Outlet, useLocation, useSearchParams } from 'react-router-dom';
import {
  LayoutDashboard,
  Compass,
  ScanLine,
  Upload,
  Building2,
  QrCode,
  ClipboardCheck,
  ShieldCheck,
  FolderOpen,
  BarChart3,
  FileText,
  Grid2x2,
  Search,
  RotateCcw,
  Shield,
  Globe,
  Menu,
  X,
  Settings as SettingsIcon,
  LogIn,
  LogOut,
} from 'lucide-react';
import { GlobalSearch } from './GlobalSearch';
import { SmallScreenNotice } from './SmallScreenNotice';
import { useApp } from '../../context/AppContext';
import { useTranslation } from '../../i18n/LanguageContext';
import { Language } from '../../i18n/translations';
import { ROLE_BADGE_CLASSES, ROLE_BADGE_FALLBACK, type RoleColor } from '../../lib/roleBadge';
import { AskTheMapModal } from '../workspace/AskTheMapModal';
import { GuidedTourModal } from '../modals/GuidedTourModal';
import { LoginModal } from '../auth/LoginModal';
import { DemoWizard } from '../ui/DemoWizard';
import { LANGUAGE_OPTIONS } from '../../i18n/LanguageContext';

const NAV_SECTIONS = [
  { id: 'home', to: '/app', label: 'Overview', icon: LayoutDashboard, end: true },
  { id: 'map', to: '/app/map', label: '3D Command Center', icon: Globe, end: false },
  { id: 'lidar', to: '/app/lidar', label: 'LiDAR', icon: ScanLine, end: false },
  { id: 'ingest', to: '/app/ingest', label: 'Data Ingest', icon: Upload, end: false },
  { id: 'properties', to: '/app/properties', label: 'Properties', icon: Building2, end: false },
  { id: 'locate', to: '/app/locate', label: 'Locate', icon: Compass, end: false },
  { id: 'ulpin', to: '/app/ulpin', label: 'ULPIN', icon: QrCode, end: false },
  { id: 'review', to: '/app/review', label: 'Review', icon: ClipboardCheck, end: false },
  { id: 'validation', to: '/app/validation', label: 'Validation', icon: ShieldCheck, end: false },
  { id: 'evidence', to: '/app/evidence', label: 'Evidence', icon: FolderOpen, end: false },
  { id: 'analytics', to: '/app/analytics', label: 'Analytics', icon: BarChart3, end: false },
  { id: 'audit', to: '/app/audit', label: 'Audit', icon: FileText, end: false },
  { id: 'console', to: '/app/console', label: 'System Console', icon: Grid2x2, end: false },
];

export const AppShell: React.FC<{ onResetDemo: () => void }> = ({ onResetDemo }) => {
  const { user, logout, toast, permissions } = useApp();
  const { language, setLanguage } = useTranslation();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [askOpen, setAskOpen] = useState(false);
  const [tourOpen, setTourOpen] = useState(false);
  const [loginOpen, setLoginOpen] = useState(false);

  // Deep pages can hit an auth-gated endpoint while signed out -- the demand
  // notice on the analytics table is one -- and the LoginModal is only mounted
  // here. Rather than threading an onRequestSignIn prop down through every
  // page and modal that might need it, those call sites raise this event and
  // the shell, which owns the dialog, answers it.
  useEffect(() => {
    const open = () => setLoginOpen(true);
    window.addEventListener('bhudrishti:request-signin', open);
    return () => window.removeEventListener('bhudrishti:request-signin', open);
  }, []);
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();

  const visibleSections = NAV_SECTIONS.filter(
    (tab) => permissions.navItems.includes(tab.id) || (tab.id === 'lidar' && permissions.canViewLiDAR)
  );

  useEffect(() => {
    if (searchParams.get('tour') === '1') {
      setTourOpen(true);
      searchParams.delete('tour');
      setSearchParams(searchParams, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  return (
    <div className="app-shell min-h-screen bg-canvas flex flex-col">
      {/* Top bar */}
      <header className="bg-chalk border-b-2 border-ink sticky top-0 z-40 shadow-brutal-sm">
        <div className="max-w-[1600px] mx-auto px-4 h-16 flex items-center gap-4">
          <Link to="/app" className="flex items-center gap-2.5 shrink-0">
            <div className="w-9 h-9 rounded-none bg-accent text-ink border-2 border-ink flex items-center justify-center shadow-brutal-sm font-black text-base">
              भू
            </div>
            <div className="hidden sm:block leading-tight">
              <div className="flex items-center gap-2">
                <span className="font-extrabold text-sm tracking-tight text-ink font-display">Bhu-Drishti 3D</span>
                <span className="text-[9px] uppercase font-mono font-black bg-ink text-white border-2 border-ink px-1.5 py-0.5 rounded-none">
                  SIH26011
                </span>
                <span className={`text-[10px] font-black uppercase tracking-wide px-2 py-0.5 rounded-none border-2 flex items-center gap-1 ml-1 ${ROLE_BADGE_CLASSES[permissions.color as RoleColor] ?? ROLE_BADGE_FALLBACK}`}>
                  <span className="w-1.5 h-1.5 rounded-none bg-ink"></span> {permissions.label}
                </span>
              </div>
              <span className="text-[10px] text-ink-soft font-bold">Vertical Property Mapping Platform</span>
            </div>
          </Link>

          <div className="flex-1 flex justify-center px-2">
            <GlobalSearch />
          </div>

          <div className="flex items-center gap-1.5 shrink-0">
            <button
              onClick={() => setAskOpen(true)}
              className="hidden md:flex items-center gap-1.5 px-3 py-1.5 rounded-none bg-canvas hover:bg-accent text-ink text-xs font-black uppercase tracking-wide border-2 border-ink shadow-brutal-sm transition"
              title="Ask natural-language questions about the 3D cadastre"
            >
              <Search className="w-3.5 h-3.5 text-accent-strong" />
              <span className="hidden xl:inline">Ask the Map</span>
            </button>

            <div className="hidden sm:flex items-center gap-1 bg-canvas border-2 border-ink px-2 py-1 rounded-none text-xs">
              <Globe className="w-3.5 h-3.5 text-ink-soft" />
              <select
                value={language}
                onChange={(e) => setLanguage(e.target.value as Language)}
                className="bg-transparent font-bold text-ink focus:outline-none cursor-pointer text-xs max-w-[9rem]"
                aria-label="Language"
              >
                {LANGUAGE_OPTIONS.map((opt) => (
                  <option key={opt.code} value={opt.code}>
                    {opt.code === 'en' ? 'EN' : 'HI'}
                  </option>
                ))}
              </select>
            </div>

            {user ? (
              <div
                className="hidden xl:flex items-center gap-1.5 bg-canvas border-2 border-ink px-2.5 py-1 rounded-none"
                title={user.full_name}
              >
                <Shield className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
                <span className="max-w-[13rem] truncate text-xs font-bold text-ink">{user.full_name}</span>
                <button
                  onClick={logout}
                  className="p-1 rounded-none border-2 border-transparent hover:border-ink text-ink hover:bg-accent transition"
                  title="Sign out"
                  aria-label="Sign out"
                >
                  <LogOut className="w-3.5 h-3.5" />
                </button>
              </div>
            ) : (
              <button
                onClick={() => setLoginOpen(true)}
                className="hidden xl:flex items-center gap-1.5 px-3 py-1.5 rounded-none bg-ink text-white text-xs font-black uppercase tracking-wide border-2 border-ink shadow-brutal-sm transition hover:bg-accent hover:text-ink hover:shadow-none hover:translate-x-[2px] hover:translate-y-[2px]"
                title="Sign in with a role account"
                aria-label="Sign in"
              >
                <LogIn className="w-3.5 h-3.5" />
                Sign in
              </button>
            )}

            <button
              onClick={onResetDemo}
              className="flex items-center gap-1 px-2 py-1.5 rounded-none border-2 border-transparent hover:border-ink text-ink hover:bg-accent text-xs transition"
              title="Reset demo scenario"
            >
              <RotateCcw className="w-3.5 h-3.5" />
            </button>

            <NavLink
              to="/app/settings"
              className={({ isActive }) =>
                `p-2 rounded-none border-2 border-transparent transition ${isActive ? 'bg-ink text-white border-ink' : 'text-ink hover:bg-accent hover:border-ink'}`
              }
              title="Settings"
            >
              <SettingsIcon className="w-4 h-4" />
            </NavLink>

            <button
              onClick={() => setMobileOpen(true)}
              className="lg:hidden p-2 rounded-none border-2 border-ink text-ink hover:bg-accent transition"
              aria-label="Open navigation"
            >
              <Menu className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Secondary section nav */}
        <nav className="hidden lg:block border-t-2 border-ink bg-chalk">
          <div className="max-w-[1600px] mx-auto px-4 flex items-center gap-0.5 overflow-x-auto">
            {visibleSections.map((item) => {
              const Icon = item.icon;
              const active = item.end
                ? location.pathname === item.to
                : location.pathname.startsWith(item.to);
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  className={`flex items-center gap-1.5 px-3 py-2 text-xs font-black uppercase tracking-wide transition border-r-2 -mb-px ${
                    active
                      ? 'bg-ink text-white border-ink shadow-brutal-sm translate-x-[2px] translate-y-[2px]'
                      : 'text-ink hover:bg-accent border-ink'
                  }`}
                >
                  <Icon className="w-3.5 h-3.5" />
                  {item.label}
                </NavLink>
              );
            })}
          </div>
        </nav>
      </header>

      <SmallScreenNotice />

      {/* Mobile drawer */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="absolute inset-0 bg-ink/60" onClick={() => setMobileOpen(false)} />
          <div className="absolute right-0 top-0 h-full w-72 bg-chalk border-l-2 border-ink shadow-brutal-lg flex flex-col animate-in slide-in-from-right duration-200">
            <div className="flex items-center justify-between px-4 py-4 border-b-2 border-ink">
              <span className="font-extrabold text-sm text-ink font-display">Bhu-Drishti 3D</span>
              <button onClick={() => setMobileOpen(false)} className="p-1.5 rounded-none text-ink-soft hover:bg-canvas" aria-label="Close">
                <X className="w-5 h-5" />
              </button>
            </div>
            <nav className="flex-1 overflow-y-auto p-2">
              {visibleSections.map((item) => {
                const Icon = item.icon;
                return (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    end={item.end}
                    onClick={() => setMobileOpen(false)}
                    className={({ isActive }) =>
                      `flex items-center gap-2.5 px-3 py-2.5 rounded-none text-sm font-black uppercase tracking-wide border-2 border-ink mb-1 transition ${
                        isActive ? 'bg-ink text-white shadow-brutal-sm' : 'bg-chalk text-ink hover:bg-accent'
                      }`
                    }
                  >
                    <Icon className="w-4 h-4" />
                    {item.label}
                  </NavLink>
                );
              })}
            </nav>
            {user ? (
              <div className="p-3 border-t-2 border-ink space-y-1.5">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-bold text-ink truncate">{user.full_name}</span>
                  <button
                    onClick={() => {
                      setMobileOpen(false);
                      logout();
                    }}
                    className="flex items-center gap-1 text-xs font-bold text-red-600 hover:underline"
                  >
                    <LogOut className="w-3 h-3" />
                    Sign out
                  </button>
                </div>
                <div className="text-[11px] text-ink-soft">{permissions.label}</div>
              </div>
            ) : (
              <div className="p-3 border-t-2 border-ink">
                <button
                  onClick={() => {
                    setMobileOpen(false);
                    setLoginOpen(true);
                  }}
                  className="w-full flex items-center justify-center gap-1.5 py-2.5 text-sm font-black uppercase tracking-wide bg-ink text-white border-2 border-ink shadow-brutal rounded-none transition hover:bg-accent hover:text-ink"
                >
                  <LogIn className="w-4 h-4" />
                  Sign in
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Toast */}
      {toast && (
        <div className="fixed top-20 right-6 z-50 bg-ink text-chalk text-xs font-bold px-4 py-2.5 rounded-none shadow-brutal animate-in slide-in-from-top-2 duration-200">
          {toast}
        </div>
      )}

      <main className="flex-1 pb-16 lg:pb-0">
        <div className="max-w-[1600px] mx-auto px-4 sm:px-6 py-6 animate-fade-up">
          <Outlet />
        </div>
      </main>

      {/* Mobile bottom nav — five primary destinations; full menu stays in the drawer. */}
      <nav
        className="lg:hidden fixed bottom-0 inset-x-0 bg-chalk border-t-2 border-ink z-40 flex justify-around py-1.5"
        aria-label="Primary mobile navigation"
      >
        {(
          [
            { to: '/app', icon: LayoutDashboard, label: 'Home', end: true },
            { to: '/app/map', icon: Globe, label: 'Map', end: false },
            { to: '/app/ingest', icon: Upload, label: 'Ingest', end: false },
            { to: '/app/ulpin', icon: QrCode, label: 'ULPIN', end: false },
            { to: '/app/settings', icon: SettingsIcon, label: 'More', end: false },
          ] as const
        ).map((t) => (
          <NavLink
            key={t.to}
            to={t.to}
            end={t.end}
            className={({ isActive }) =>
              `flex flex-col items-center gap-0.5 text-[10px] px-2 py-1 font-bold uppercase tracking-wide ${
                isActive ? 'text-accent-strong' : 'text-ink-soft'
              }`
            }
          >
            <t.icon className="w-5 h-5" />
            {t.label}
          </NavLink>
        ))}
      </nav>

      <DemoWizard />
      <AskTheMapModal isOpen={askOpen} onClose={() => setAskOpen(false)} />
      <GuidedTourModal isOpen={tourOpen} onClose={() => setTourOpen(false)} />
      <LoginModal isOpen={loginOpen} onClose={() => setLoginOpen(false)} />
    </div>
  );
};