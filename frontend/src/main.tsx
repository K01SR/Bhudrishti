import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import PerfOverlay from './perf/PerfOverlay';
import { installPerfProbe, isPerfEnabled, startPerf, trackWebglContexts } from './perf/perf';
import 'maplibre-gl/dist/maplibre-gl.css';
import './index.css';

// Instrumentation is opt-in via ?perf=1 and inert otherwise. The probe is
// installed before React mounts so a test can read counters from the first
// frame, and the WebGL counter is patched before any renderer is constructed.
if (isPerfEnabled()) {
  installPerfProbe();
  trackWebglContexts();
  startPerf();
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
    <PerfOverlay />
  </React.StrictMode>
);
