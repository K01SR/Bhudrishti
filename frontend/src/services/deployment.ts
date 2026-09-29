/**
 * What this deployment actually serves, fetched once from the backend.
 *
 * The UI used to render "Demo dataset" markers from a hardcoded string with no
 * connection to the ENABLE_DEMO_MODE gate behind the API, so the badge showed
 * on deployments serving no generated data at all. That is worse than showing
 * nothing: a marker that is always present carries no information.
 *
 * The flag is read from the backend rather than baked in at build time because
 * the gate is a runtime environment variable, and a build-time value would
 * drift from it the moment the same image is deployed with the gate open.
 *
 * Everything here fails closed. Until the fetch resolves, and if it fails, the
 * deployment is treated as not-demo, so a marker is withheld rather than shown
 * on a deployment that may not be one.
 */
import { useEffect, useState } from 'react';

export interface DeploymentFacts {
  environment: string;
  demo_mode: boolean;
  synthetic_data_served: boolean;
  signing_key: string;
  note: string;
}

/** The state used before the fetch resolves and if it fails. */
export const UNKNOWN_DEPLOYMENT: DeploymentFacts = {
  environment: 'unknown',
  demo_mode: false,
  synthetic_data_served: false,
  signing_key: 'unknown',
  note: 'Deployment facts unavailable; demonstration markers are withheld.',
};

const API_BASE = (import.meta as any).env?.VITE_API_URL || '/api/v1';

let inflight: Promise<DeploymentFacts> | null = null;
let cached: DeploymentFacts | null = null;

async function requestFacts(): Promise<DeploymentFacts> {
  const res = await fetch(`${API_BASE}/system/deployment`, {
    headers: { Accept: 'application/json' },
  });
  if (!res.ok) throw new Error(`deployment facts unavailable: ${res.status}`);
  const body = (await res.json()) as Partial<DeploymentFacts>;
  // Coerce rather than trust: a missing or mistyped field must not become a
  // truthy demo_mode and light up every marker in the app.
  return {
    environment: typeof body.environment === 'string' ? body.environment : 'unknown',
    demo_mode: body.demo_mode === true,
    synthetic_data_served: body.synthetic_data_served === true,
    signing_key: typeof body.signing_key === 'string' ? body.signing_key : 'unknown',
    note: typeof body.note === 'string' ? body.note : UNKNOWN_DEPLOYMENT.note,
  };
}

/** Fetches once per page load; concurrent callers share the same request. */
export function fetchDeploymentFacts(): Promise<DeploymentFacts> {
  if (!inflight) {
    inflight = requestFacts()
      .then((facts) => {
        cached = facts;
        return facts;
      })
      .catch((err) => {
        console.warn('[deployment] falling back to fail-closed facts:', err);
        inflight = null; // allow a later retry
        return UNKNOWN_DEPLOYMENT;
      });
  }
  return inflight;
}

/** Synchronous read for code paths that already hold the facts. */
export function deploymentFacts(): DeploymentFacts {
  return cached ?? UNKNOWN_DEPLOYMENT;
}

export function isDemoDeployment(): boolean {
  return (cached ?? UNKNOWN_DEPLOYMENT).demo_mode;
}

/** Resolves the real deployment facts and re-renders when they change. */
export function useDeployment(): DeploymentFacts {
  const [facts, setFacts] = useState<DeploymentFacts>(cached ?? UNKNOWN_DEPLOYMENT);
  useEffect(() => {
    let live = true;
    fetchDeploymentFacts().then((next) => {
      if (live) setFacts(next);
    });
    return () => {
      live = false;
    };
  }, []);
  return facts;
}
