import React, { Suspense, lazy } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AppProvider } from './context/AppContext';
import { LanguageProvider } from './i18n/LanguageContext';
import { AppShell } from './components/layout/AppShell';
import { resetHeroScenario } from './services/api';
import { Loader2 } from 'lucide-react';
import { useApp } from './context/AppContext';
import { DEMO_ULPIN } from './constants';

/* Lazy helper for modules that export a named component (no default export). */
function lazyNamed<T extends Record<string, unknown>>(loader: () => Promise<T>) {
  return lazy(() =>
    loader().then((m) => {
      const key = Object.keys(m).find((k) => k !== '__esModule') || 'default';
      return { default: m[key] as unknown as React.ComponentType };
    })
  );
}

/* --- Landing (marketing) --- */
const LandingPage = lazyNamed(() => import('./pages/LandingPage'));

/* --- Application pages (code-split; heavy 3D routes split too) --- */
const AppHome = lazyNamed(() => import('./pages/app/AppHome'));
const MapPage = lazyNamed(() => import('./pages/app/MapPage'));
const PropertyRegistry = lazyNamed(() => import('./pages/app/PropertyRegistry'));
const PropertyDetail = lazyNamed(() => import('./pages/app/PropertyDetail'));
const ULPINPage = lazyNamed(() => import('./pages/app/ULPINPage'));
const ValidationPage = lazyNamed(() => import('./pages/app/ValidationPage'));
const EvidencePage = lazyNamed(() => import('./pages/app/EvidencePage'));
const ReviewPage = lazyNamed(() => import('./pages/app/ReviewPage'));
const AnalyticsPage = lazyNamed(() => import('./pages/app/AnalyticsPage'));
const SwissConsolePage = lazyNamed(() => import('./pages/app/SwissConsolePage'));
const AuditPage = lazyNamed(() => import('./pages/app/AuditPage'));
const SettingsPage = lazyNamed(() => import('./pages/app/SettingsPage'));
const LiDARInspectPage = lazyNamed(() => import('./pages/app/LiDARInspectPage'));
const LocatePage = lazyNamed(() => import('./pages/app/LocatePage'));
const IngestPage = lazyNamed(() => import('./pages/app/IngestPage'));

/* --- Public verification (no app chrome, so QR cards keep working) --- */
const PublicVerifyPage = lazyNamed(() => import('./pages/PublicVerifyPage'));
const BlockchainVerifyPage = lazyNamed(() => import('./pages/BlockchainVerifyPage'));
const DocsPage = lazyNamed(() => import('./pages/DocsPage'));

const PageFallback: React.FC = () => (
  <div className="flex items-center justify-center h-[calc(100vh-8rem)] text-slate-500">
    <div className="flex flex-col items-center gap-3">
      <Loader2 className="w-6 h-6 text-accent animate-spin" />
      <span className="text-xs font-mono font-medium">Loading Bhu-Drishti 3D…</span>
    </div>
  </div>
);

const ShellRoot: React.FC = () => {
  const { showToast } = useApp();
  const handleResetDemo = async () => {
    try {
      const res = await resetHeroScenario();
      showToast(res.message || 'Demo scenario reset');
      window.setTimeout(() => window.location.reload(), 600);
    } catch (err) {
      showToast('Could not reset demo');
    }
  };
  return <AppShell onResetDemo={handleResetDemo} />;
};

const App: React.FC = () => (
  <LanguageProvider>
    <AppProvider>
      <BrowserRouter>
        <div className="min-h-screen bg-slate-50 text-slate-900 flex flex-col font-sans antialiased selection:bg-accent/15 selection:text-ink">
          <Suspense fallback={<PageFallback />}>
            <Routes>
              {/* Marketing landing — no application chrome */}
              <Route path="/" element={<LandingPage />} />

              {/* Public verification — no application chrome.
                  The literal /verify/blockchain route is declared before the
                  :token catch-all so a scanned proof does not get swallowed
                  and looked up as if it were a spatial token. */}
              <Route path="/verify/blockchain" element={<BlockchainVerifyPage />} />
              <Route path="/verify/:token" element={<PublicVerifyPage />} />
              <Route path="/docs" element={<DocsPage />} />

              {/* Application core */}
              <Route path="/app" element={<ShellRoot />}>
                <Route index element={<AppHome />} />
                <Route path="map" element={<MapPage />} />
                <Route path="open-studio" element={<Navigate to="/app/map?view=open_twin" replace />} />
                <Route path="properties" element={<PropertyRegistry />} />
                <Route path="locate" element={<LocatePage />} />
                <Route path="properties/:ulpin" element={<PropertyDetail />} />
                <Route path="lidar" element={<LiDARInspectPage />} />
                <Route path="ingest" element={<IngestPage />} />
                <Route path="ulpin" element={<ULPINPage />} />
                <Route path="validation" element={<ValidationPage />} />
                <Route path="evidence" element={<EvidencePage />} />
                <Route path="review" element={<ReviewPage />} />
                <Route path="analytics" element={<AnalyticsPage />} />
                <Route path="audit" element={<AuditPage />} />
                <Route path="console" element={<SwissConsolePage />} />
                <Route path="settings" element={<SettingsPage />} />
              </Route>

              {/* Legacy routes → redirects to keep old links working */}
              <Route path="/workspace" element={<Navigate to={`/app/properties/${DEMO_ULPIN}`} replace />} />
              <Route path="/state" element={<Navigate to="/app/analytics" replace />} />
              <Route path="/district" element={<Navigate to="/app/review" replace />} />
              <Route path="/metrics" element={<Navigate to="/app/analytics" replace />} />
              <Route path="/audit" element={<Navigate to="/app/audit" replace />} />
              <Route path="/id-decoder" element={<Navigate to="/app/ulpin" replace />} />
              <Route path="/pipelines" element={<Navigate to="/app/analytics" replace />} />

              {/* 404 */}
              <Route path="*" element={<Navigate to="/app" replace />} />
            </Routes>
          </Suspense>
        </div>
      </BrowserRouter>
    </AppProvider>
  </LanguageProvider>
);

export default App;