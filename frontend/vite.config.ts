import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import http from 'node:http';

// `changeOrigin` is the correct key for a Vite proxy target; the previous file
// misspelled it as `changeOrigin` on a config Vite never read, so the /api
// rewrite silently did not apply to the dev server.
const apiProxy = () => ({
  '/api': {
    target: process.env.VITE_PROXY_TARGET || 'http://backend:8000',
    changeOrigin: true,
    agent: new http.Agent({ keepAlive: true, maxSockets: 32 }),
  },
});

export default defineConfig({
  plugins: [react()],
  build: {
    chunkSizeWarningLimit: 850,
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          if (!id.includes('node_modules')) return undefined;
          if (id.includes('/three') || id.includes('three.module') || id.includes('three/examples')) return 'three';
          if (id.includes('maplibre') || id.includes('@mapbox') || id.includes('@maplibre')) return 'maplibre';
          if (id.includes('react') || id.includes('scheduler') || id.includes('react-router') || id.includes('history')) return 'react';
          if (id.includes('lucide-react')) return 'icons';
          return 'vendor';
        },
      },
    },
  },
  server: {
    port: 3000,
    host: '0.0.0.0',
    // No blanket host allowlist. The previous entry hardcoded a single
    // ephemeral Cloudflare quick-tunnel hostname, which was valid for one dev
    // session and meaningless to anyone else, plus a '.trycloudflare.com'
    // wildcard that was always on. Since the dev server binds 0.0.0.0, an
    // always-permissive wildcard is a Host-header risk in any environment that
    // is not purely a local laptop. Tunnels are opt-in now:
    //   VITE_ALLOWED_HOSTS=abc.trycloudflare.com,.example.com npm run dev
    allowedHosts: (process.env.VITE_ALLOWED_HOSTS ?? '')
      .split(',')
      .map((host) => host.trim())
      .filter(Boolean),
    proxy: apiProxy(),
  },
  // The e2e suite runs against `vite preview` rather than the dev server.
  // React.StrictMode double-invokes effects in dev, which makes the 3D scene
  // build twice per mount; the resulting frame timings would not describe what a
  // user actually gets, and the stall gate would measure the wrong thing.
  preview: {
    port: 3100,
    host: '0.0.0.0',
    proxy: apiProxy(),
  },
});
