import React, { useEffect, useState } from 'react';
import {
  BookOpen, KeyRound, ShieldCheck, Terminal, Map, Database, Cpu,
  CheckCircle2, XCircle, AlertTriangle, ExternalLink, Copy, Check,
} from 'lucide-react';

/* ------------------------------------------------------------------ *
 * Copy-to-clipboard
 * ------------------------------------------------------------------ */

const CopyButton: React.FC<{ text: string }> = ({ text }) => {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 1600);
        } catch {
          /* clipboard blocked; the code is selectable regardless */
        }
      }}
      className="shrink-0 flex items-center gap-1 px-1.5 py-1 border border-ink/30 hover:bg-ink hover:text-canvas transition text-[10px] font-bold uppercase tracking-wide"
      title="Copy to clipboard"
    >
      {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
      {copied ? 'Copied' : 'Copy'}
    </button>
  );
};

const Code: React.FC<{ children: string; lang?: string; copy?: boolean }> = ({ children, lang, copy }) => (
  <div className="relative border-2 border-ink bg-ink text-canvas p-3 overflow-x-auto">
    <div className="absolute top-1.5 right-2 flex items-center gap-2">
      {copy && <CopyButton text={children} />}
      {lang && (
        <span className="text-[9px] font-mono uppercase text-canvas/40">{lang}</span>
      )}
    </div>
    <pre className="text-[11px] font-mono leading-relaxed whitespace-pre pr-16">
      <code>{children}</code>
    </pre>
  </div>
);

/* ------------------------------------------------------------------ *
 * Key generation command
 * ------------------------------------------------------------------ */

const KEYGEN_CMD = `python3 -c "from cryptography.hazmat.primitives.asymmetric import ed25519 as e; \\
  k = e.Ed25519PrivateKey.generate(); \\
  print('ED25519_PRIVATE_KEY_HEX=' + k.private_bytes_raw().hex()); \\
  print('ED25519_PUBLIC_KEY_HEX=' + k.public_key().public_bytes_raw().hex())"`;

/* ------------------------------------------------------------------ *
 * Live key-readiness check
 * ------------------------------------------------------------------ */

interface KeyStatus {
  loaded: boolean;
  details: Record<string, unknown>;
}

const Check_ = ({ ok, warn, children }: { ok: boolean; warn?: boolean; children: React.ReactNode }) => (
  <li className="flex items-start gap-2 text-[12px] leading-relaxed">
    {warn ? (
      <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0 text-amber-600" />
    ) : ok ? (
      <CheckCircle2 className="w-3.5 h-3.5 mt-0.5 shrink-0 text-emerald-600" />
    ) : (
      <XCircle className="w-3.5 h-3.5 mt-0.5 shrink-0 text-red-600" />
    )}
    <span className={warn ? 'text-ink' : ok ? 'text-ink-soft' : 'text-ink'}>{children}</span>
  </li>
);

const KeyReadiness: React.FC = () => {
  const [status, setStatus] = useState<KeyStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch('/api/v1/precinct/verify-signature/config');
        const body = await res.json().catch(() => null);
        if (cancelled) return;
        if (body && typeof body === 'object' && 'uses_published_signing_key' in body) {
          setStatus({ loaded: true, details: body });
        } else {
          setError(`unexpected response (HTTP ${res.status})`);
        }
      } catch (e) {
        if (!cancelled) setError(String(e));
      }
    })();
    return () => { cancelled = true; };
  }, []);

  if (error) {
    return (
      <p className="text-[12px] text-ink-soft">
        Could not reach the verification endpoint (<code className="font-mono">{error}</code>).
        The backend is not responding, so key status cannot be read from here.
      </p>
    );
  }
  if (!status) {
    return <p className="text-[12px] text-ink-soft">Checking this deployment&rsquo;s key configuration&hellip;</p>;
  }

  return (
    <ul className="space-y-2">
      <Check_ ok={!status.details.demo_mode}>
        {status.details.demo_mode
          ? 'ENABLE_DEMO_MODE is on. Demo-only endpoints are reachable and the published demonstration signing key is in use.'
          : 'ENABLE_DEMO_MODE is off. No demo-only endpoint is exposed.'}
      </Check_>
      <Check_ ok={!status.details.uses_published_signing_key} warn={Boolean(status.details.uses_published_signing_key)}>
        {status.details.uses_published_signing_key
          ? 'This deployment is signing with the key published in the repository. Anyone with a copy of the code can produce a signature that verifies here, so the signature proves nothing about authorship. Set ED25519_PRIVATE_KEY_HEX and ED25519_PUBLIC_KEY_HEX.'
          : 'A private signing key is configured and is not the published repository key.'}
      </Check_>
      <Check_ ok={!status.details.uses_default_secret_key} warn={Boolean(status.details.uses_default_secret_key)}>
        {status.details.uses_default_secret_key
          ? 'SECRET_KEY is still the development default. Anyone can forge session tokens. Set it before serving traffic.'
          : 'SECRET_KEY is not the development default.'}
      </Check_>
    </ul>
  );
};

/* ------------------------------------------------------------------ *
 * Sections
 * ------------------------------------------------------------------ */

interface SectionProps {
  id: string;
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
}

const Section: React.FC<SectionProps> = ({ id, icon, title, children }) => (
  <section id={id} className="scroll-mt-6">
    <div className="flex items-center gap-2 mb-3 pb-2 border-b-2 border-ink">
      <span className="text-accent-strong">{icon}</span>
      <h2 className="font-black uppercase tracking-widest text-ink text-sm">{title}</h2>
    </div>
    {children}
  </section>
);

const Para: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <p className="text-[13px] leading-relaxed text-ink-soft mb-3">{children}</p>
);

const NAV = [
  { id: 'start', label: 'Getting started' },
  { id: 'maps', label: 'The three map views' },
  { id: 'keys', label: 'Keys & secrets' },
  { id: 'verify', label: 'Verifying a document' },
  { id: 'deploy', label: 'Deploying' },
  { id: 'truth', label: 'What this system is not' },
];

export const DocsPage: React.FC = () => {
  return (
    <div className="min-h-screen bg-chalk text-ink">
      {/* Masthead */}
      <header className="border-b-2 border-ink bg-ink text-canvas">
        <div className="max-w-5xl mx-auto px-5 py-8 sm:py-10">
          <div className="flex items-center gap-2 text-accent text-[10px] font-black uppercase tracking-[0.2em]">
            <BookOpen className="w-3.5 h-3.5" />
            Documentation
          </div>
          <h1 className="text-2xl sm:text-3xl font-black uppercase tracking-tight mt-2">
            How to use Bhudrishti
          </h1>
          <p className="text-[13px] text-canvas/70 mt-2 max-w-2xl leading-relaxed">
            What each screen does, what the keys are for, and what this system will
            not claim. Read the last section before showing this to anyone &mdash; it
            is the part that keeps the rest honest.
          </p>
        </div>
      </header>

      <div className="max-w-5xl mx-auto px-5 py-8 grid lg:grid-cols-[190px_1fr] gap-8">
        {/* Nav */}
        <nav className="lg:sticky lg:top-6 lg:self-start">
          <ul className="space-y-1">
            {NAV.map((n) => (
              <li key={n.id}>
                <a
                  href={`#${n.id}`}
                  className="block text-[12px] font-bold text-ink-soft hover:text-ink py-1 border-l-2 border-transparent hover:border-accent pl-2 transition"
                >
                  {n.label}
                </a>
              </li>
            ))}
          </ul>
        </nav>

        <div className="space-y-10 min-w-0">
          {/* Start here */}
          <Section id="start" icon={<Map className="w-4 h-4" />} title="Getting started">
            <Para>
              Sign in with one of the built-in roles from the header. The role
              decides which pages you can reach; there is no separate user system
              to set up. <code className="font-mono text-[12px]">state.admin</code>,{' '}
              <code className="font-mono text-[12px]">district.admin</code>,{' '}
              <code className="font-mono text-[12px]">taluka.verifier</code>,{' '}
              <code className="font-mono text-[12px]">builder.demo</code> and{' '}
              <code className="font-mono text-[12px]">citizen.demo</code> all use the
              demo password.
            </Para>
            <Para>
              Open <strong>Map</strong> and pick a view. Everything else in the app
              hangs off a property, so it helps to find a property first &mdash; the{' '}
              <strong>Locate</strong> page drills down State &rarr; District &rarr; Taluka
              &rarr; Village, and <strong>Properties</strong> lists the generated
              Airoli parcels.
            </Para>
          </Section>

          {/* Map views */}
          <Section id="maps" icon={<Map className="w-4 h-4" />} title="The three map views">
            <div className="space-y-3">
              {[
                {
                  name: 'open_twin',
                  url: '/app/map?view=open_twin',
                  body:
                    'A 3D studio. The Spatial Layers panel on the left toggles buildings, roads, civic amenities, labels, subsurface utilities, terrain relief and satellite imagery. Terrain Relief and Satellite Imagery are off by default because they sit over the basemap rather than under it. The derived utility network only appears in Underground mode, and it is derived from OSM road geometry, not surveyed.',
                },
                {
                  name: 'cadastre',
                  url: '/app/map?view=cadastre',
                  body:
                    'A 2D parcel map with the legal and topology overlays. This is the view where cadastral layers, rights and lineage actually resolve to data.',
                },
                {
                  name: '3d',
                  url: '/app/map?view=3d',
                  body:
                    'A lighter 3D city view. Building counts and place names come from OpenStreetMap via Overpass, and increase as you zoom in.',
                },
              ].map((v) => (
                <div key={v.name} className="border-2 border-ink p-3.5">
                  <div className="flex items-center justify-between gap-2 mb-1.5">
                    <code className="font-mono text-[12px] font-bold text-ink">{v.url}</code>
                    <a
                      href={v.url}
                      className="shrink-0 flex items-center gap-1 text-[10px] font-bold uppercase tracking-wide border border-ink px-1.5 py-1 hover:bg-ink hover:text-canvas transition"
                    >
                      Open <ExternalLink className="w-2.5 h-2.5" />
                    </a>
                  </div>
                  <p className="text-[12px] text-ink-soft leading-relaxed">{v.body}</p>
                </div>
              ))}
            </div>
            <div className="mt-3 border-l-2 border-accent pl-3">
              <p className="text-[12px] text-ink-soft leading-relaxed">
                The basemap is OpenStreetMap data served by CARTO. The credit line
                on the map is a licence condition, not decoration &mdash; if you
                restyle the map, keep it.
              </p>
            </div>
          </Section>

          {/* Keys */}
          <Section id="keys" icon={<KeyRound className="w-4 h-4" />} title="Keys and secrets">
            <Para>
              There are three secrets that matter before you put this on a server.
              None of them ship with a usable production value, and the app
              refuses to start in <code className="font-mono text-[12px]">production</code>{' '}
              mode if any of them is still a default.
            </Para>

            <div className="space-y-3 mb-4">
              <div className="border-2 border-ink p-3.5">
                <div className="font-black text-[11px] uppercase tracking-widest mb-1">SECRET_KEY</div>
                <p className="text-[12px] text-ink-soft leading-relaxed">
                  Signs session tokens. With the default value anyone can mint a
                  token for any role, so this is the one that matters most.
                </p>
                <div className="mt-2"><Code copy>python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))"</Code></div>
              </div>

              <div className="border-2 border-ink p-3.5">
                <div className="font-black text-[11px] uppercase tracking-widest mb-1">
                  Ed25519 signing keypair
                </div>
                <p className="text-[12px] text-ink-soft leading-relaxed mb-2">
                  Signs generated documents. The repository publishes a
                  demonstration key so the app runs out of the box &mdash; which
                  also means anyone who clones it can forge documents that verify.
                  Generate your own pair and set both halves.
                </p>
                <Code lang="bash" copy>{KEYGEN_CMD}</Code>
                <p className="text-[11px] text-ink-soft mt-2 leading-relaxed">
                  The private key must never be in the frontend bundle or in git.
                  Only the public half is safe to publish &mdash; that is the point
                  of a keypair.
                </p>
              </div>

              <div className="border-2 border-ink p-3.5">
                <div className="font-black text-[11px] uppercase tracking-widest mb-1">POSTGRES_PASSWORD</div>
                <p className="text-[12px] text-ink-soft leading-relaxed">
                  Also has a development default, also checked at startup.
                </p>
              </div>
            </div>

            <div className="border-2 border-ink bg-canvas p-3.5">
              <div className="font-black text-[11px] uppercase tracking-widest mb-2">
                This deployment right now
              </div>
              <KeyReadiness />
            </div>
          </Section>

          {/* Verification */}
          <Section id="verify" icon={<ShieldCheck className="w-4 h-4" />} title="Verifying a document">
            <Para>
              A generated demand notice carries a real Ed25519 signature over the
              SHA-256 fingerprint of the document. To check it, strip the{' '}
              <code className="font-mono text-[12px]">cryptographic_verification</code>{' '}
              field, recompute the fingerprint, and verify the signature against
              the public key. The endpoint does this for you:
            </Para>
            <Code lang="bash">{`curl -X POST http://localhost:8000/api/v1/precinct/verify-signature \\
  -H 'Content-Type: application/json' \\
  -d '{"document": { ...notice..., "cryptographic_verification": null },
       "ed25519_signature": "<hex>"}'`}</Code>
            <div className="mt-3 border-2 border-ink border-l-4 border-l-amber-500 p-3.5">
              <div className="font-black text-[11px] uppercase tracking-widest mb-1.5">
                What a valid signature means
              </div>
              <ul className="space-y-1.5 text-[12px] text-ink-soft leading-relaxed">
                <li><strong className="text-ink">It does mean:</strong> the exact bytes you submitted are the bytes this deployment signed. Change one character and verification fails.</li>
                <li><strong className="text-ink">It does not mean:</strong> that any government office created, reviewed or authorised the document. It is not a legal instrument, not a municipal record, and not evidence of anything about a real property.</li>
                <li><strong className="text-ink">It especially does not mean</strong> anything about authorship while the published demo key is in use.</li>
              </ul>
            </div>
          </Section>

          {/* Deploy */}
          <Section id="deploy" icon={<Terminal className="w-4 h-4" />} title="Deploying">
            <Para>
              The multi-service compose file is the recommended path for
              development and small deployments.
            </Para>
            <Code lang="bash">{`cp .env.example .env
# edit .env: set SECRET_KEY, POSTGRES_PASSWORD, ED25519_*_HEX
docker compose up -d --build`}</Code>
            <Para>
              A single-container image is also provided for hosts that only run
              one service. It bundles the frontend, API, Celery worker, PostGIS
              and Redis behind nginx on port 3000, and needs a persistent volume
              for the database:
            </Para>
            <Code lang="bash">{`docker build -f Dockerfile.all-in-one -t bhudrishti:all .
docker run -p 3000:3000 -v bhudrishti-pgdata:/var/lib/postgresql/data \\
  -e SECRET_KEY=... -e POSTGRES_PASSWORD=... \\
  -e ED25519_PRIVATE_KEY_HEX=... -e ED25519_PUBLIC_KEY_HEX=... \\
  bhudrishti:all`}</Code>
            <div className="border-l-2 border-accent pl-3">
              <p className="text-[12px] text-ink-soft leading-relaxed">
                Before any of this: set <code className="font-mono text-[12px]">ENVIRONMENT=production</code>.
                That switch turns on the startup checks, and the container will
                refuse to boot rather than run on the published defaults.
              </p>
            </div>
          </Section>

          {/* Truth */}
          <Section id="truth" icon={<Database className="w-4 h-4" />} title="What this system is not">
            <Para>
              This is a generated scenario. The parcels, buildings, violations and
              point clouds were produced by a seeded generator, and no survey,
              registry or municipal record was consulted to produce them. The
              following are not implemented and are not simulated as if they were:
            </Para>
            <div className="border-2 border-ink divide-y-2 divide-ink">
              {[
                ['Survey data', 'No UAV, LiDAR or GPR survey of any building here has been performed. The bundled point cloud is generated with a fixed seed.'],
                ['Authority', 'This deployment cannot issue a demand notice, grant a permission, or sign anything on behalf of any government office.'],
                ['Registries', 'CERSAI liens, MahaRERA registrations and bank mortgages are not looked up. Earlier versions asserted them from the building code; they are not asserted now.'],
                ['Subsurface utilities', 'The 3D pipe network is an offset along OSM road geometry with invented depths. It is not a GPR result and is labelled as prototype wherever it is drawn.'],
                ['Point clouds', 'Coverage figures describe the generated cloud, not any flown survey.'],
              ].map(([k, v]) => (
                <div key={k} className="p-3">
                  <div className="font-black text-[11px] uppercase tracking-widest">{k}</div>
                  <p className="text-[12px] text-ink-soft leading-relaxed mt-0.5">{v}</p>
                </div>
              ))}
            </div>
            <p className="text-[12px] text-ink-soft leading-relaxed mt-3">
              If a screen here would let someone believe a simulated number is a real
              measurement, that is a bug. Report it rather than working around it.
            </p>
          </Section>

          <div className="pt-4 border-t-2 border-ink flex items-center gap-2 text-[11px] text-ink-soft">
            <Cpu className="w-3.5 h-3.5" />
            Full system documentation lives in <code className="font-mono">docs/</code> in the repository.
          </div>
        </div>
      </div>
    </div>
  );
};

export default DocsPage;
