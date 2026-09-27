import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Globe, RefreshCw, ShieldCheck, MapPin, Boxes, Info, LogOut, UserRound, Database, CheckCircle2, XCircle } from 'lucide-react';
import { resetHeroScenario, fetchDemoAccounts, type DemoAccount } from '../../services/api';
import { useApp } from '../../context/AppContext';
import { useTranslation, LANGUAGE_OPTIONS } from '../../i18n/LanguageContext';
import { Card, Button, Badge, DemoHint } from '../../components/ui';
import { cn } from '../../lib/cn';
import { ROLE_BADGE_CLASSES, ROLE_BADGE_FALLBACK, type RoleColor } from '../../lib/roleBadge';
import {
  fetchSourceStatus,
  fetchDilrmpAlignment,
  type SourceCapability,
  type SourceDescriptor,
  type SourceStatus,
  type DilrmpAlignment,
  type DilrmpAlignmentRow,
} from '../../services/api';

/**
 * What the platform can actually answer, read from the API rather than
 * asserted here.
 *
 * The panel deliberately leads with the gaps. A list of the things that work,
 * with the missing ones in a footnote, is what makes a prototype read as a
 * product; the same list with "no title source exists" sitting beside it is
 * what makes it read as a prototype. Unavailable capabilities are interleaved
 * in order and each carries the reason, so no row can be read without its
 * neighbour.
 */
const STATE_STYLE: Record<DilrmpAlignmentRow['state'], { label: string; className: string }> = {
  implemented: { label: 'In prototype', className: 'text-emerald-700 bg-emerald-50 border-emerald-200' },
  partial: { label: 'Partial', className: 'text-amber-700 bg-amber-50 border-amber-200' },
  not_implemented: { label: 'Not implemented', className: 'text-ink-soft bg-ink-soft/5 border-ink-soft/20' },
  out_of_scope: { label: 'Out of scope', className: 'text-ink-soft bg-ink-soft/5 border-ink-soft/20' },
};

/**
 * DILRMP: the programme is real, the alignment is ours.
 *
 * The badge says "In prototype", never "Compliant", because the code path being
 * present is not the same as a statutory requirement being met — and that
 * distinction is stated on the panel rather than left to the reader. The
 * programme's own numbers carry their source and retrieval date, and the
 * accreditation fields are shown as explicitly not held.
 */
const DilrmpCard: React.FC = () => {
  const [data, setData] = useState<DilrmpAlignment | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    fetchDilrmpAlignment()
      .then((d) => {
        setData(d);
        setFailed(false);
      })
      .catch(() => setFailed(true));
  }, []);

  if (failed || !data) {
    return (
      <Card className="p-5">
        <div className="flex items-center gap-2 text-sm font-bold text-ink mb-1">
          <ShieldCheck className="w-4 h-4 text-ink-soft" /> DILRMP alignment
        </div>
        <p className="text-xs text-ink-soft">
          {failed
            ? 'Could not read the alignment statement. Nothing is shown in its place.'
            : 'Reading alignment statement…'}
        </p>
      </Card>
    );
  }

  const p = data.programme;

  return (
    <Card className="p-5">
      <div className="flex items-center gap-2 text-sm font-bold text-ink mb-1">
        <ShieldCheck className="w-4 h-4 text-emerald-600" /> DILRMP alignment
      </div>
      <p className="text-xs text-ink-soft mb-3">
        {p.programme} &middot; {p.period} &middot; ₹{p.outlay_inr_crore.toLocaleString('en-IN')} crore
      </p>

      <div className="rounded-lg border border-ink-soft/20 bg-ink-soft/5 p-3 mb-3">
        <div className="text-xs font-bold text-ink">Not a participant. Not certified.</div>
        <p className="text-xs text-ink-soft mt-1">{data.disclaimer}</p>
      </div>

      <div className="text-[11px] font-bold uppercase tracking-wide text-ink-soft mb-2">
        Capability alignment
      </div>
      <ul className="flex flex-col gap-2 mb-3">
        {data.rows.map((row) => {
          const style = STATE_STYLE[row.state];
          return (
            <li key={`${row.area}-${row.capability}`} className="flex flex-col gap-1">
              <div className="flex items-start justify-between gap-2">
                <span className="text-xs font-semibold text-ink">{row.capability}</span>
                <span
                  className={cn(
                    'shrink-0 text-[10px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded border',
                    style.className
                  )}
                >
                  {style.label}
                </span>
              </div>
              <span className="text-[11px] text-ink-soft">{row.limitation}</span>
            </li>
          );
        })}
      </ul>

      <p className="text-[11px] text-ink-soft/90 mb-2">{data.summary.implemented_means}</p>
      <p className="text-[11px] text-ink-soft/80">{data.component_mapping.reason}</p>

      <div className="mt-3 pt-3 border-t border-ink-soft/15">
        <a
          href={p.source_url}
          target="_blank"
          rel="noreferrer noopener"
          className="text-[11px] text-accent-strong underline underline-offset-2"
        >
          Programme source: {p.publisher}
        </a>
        <p className="text-[11px] text-ink-soft/75 mt-1">
          Verified {p.verified_on}. {p.verification_method}
        </p>
      </div>
    </Card>
  );
};

/**
 * What the platform can actually answer, read from the API rather than
 * asserted here.
 *
 * The panel deliberately leads with the gaps. A list of the things that work,
 * with the missing ones in a footnote, is what makes a prototype read as a
 * product; the same list with "no title source exists" sitting beside it is
 * what makes it read as a prototype. Unavailable capabilities are interleaved
 * in order and each carries the reason, so no row can be read without its
 * neighbour.
 */
const SourceStatusCard: React.FC = () => {
  const [status, setStatus] = useState<SourceStatus | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    fetchSourceStatus()
      .then((s) => {
        setStatus(s);
        setFailed(false);
      })
      .catch(() => setFailed(true));
  }, []);

  if (failed) {
    return (
      <Card className="p-5">
        <div className="flex items-center gap-2 text-sm font-bold text-ink mb-1">
          <Database className="w-4 h-4 text-ink-soft" /> Data sources
        </div>
        <p className="text-xs text-ink-soft">
          Could not read source status. The panel below is omitted rather than
          filled from a cached or assumed list.
        </p>
      </Card>
    );
  }

  if (!status) {
    return (
      <Card className="p-5">
        <div className="flex items-center gap-2 text-sm font-bold text-ink mb-1">
          <Database className="w-4 h-4 text-ink-soft" /> Data sources
        </div>
        <p className="text-xs text-ink-soft">Reading source status…</p>
      </Card>
    );
  }

  const configured = status.sources.filter((s) => s.configured);
  const dormant = status.sources.filter((s) => !s.configured);

  return (
    <Card className="p-5">
      <div className="flex items-center gap-2 text-sm font-bold text-ink mb-1">
        <Database className="w-4 h-4 text-emerald-600" /> Data sources
      </div>
      <p className="text-xs text-ink-soft mb-4">
        Live configuration and real coverage. Generated demo data is never counted as a source.
      </p>

      <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 mb-4">
        <div className="text-xs font-bold text-amber-900">No authoritative cadastral source</div>
        <p className="text-xs text-amber-900/85 mt-1">{status.summary.authoritative_cadastral_note}</p>
      </div>

      <div className="text-[11px] font-bold uppercase tracking-wide text-ink-soft mb-2">
        What the platform can answer
      </div>
      <ul className="flex flex-col gap-1.5 mb-4">
        {status.capabilities.map((cap: SourceCapability) => (
          <li key={cap.key} className="flex items-start gap-2 text-xs">
            {cap.available ? (
              <CheckCircle2 className="w-3.5 h-3.5 mt-px text-emerald-600 shrink-0" />
            ) : (
              <XCircle className="w-3.5 h-3.5 mt-px text-ink-soft/60 shrink-0" />
            )}
            <span className={cap.available ? 'text-ink' : 'text-ink-soft'}>
              <span className="font-semibold">{cap.label}</span>
              {' — '}
              {cap.available ? (
                <>
                  {cap.basis}
                  {cap.authoritative && (
                    <span className="ml-1 text-emerald-700"> (official for this)</span>
                  )}
                </>
              ) : (
                <span className="text-ink-soft/90">{cap.basis}</span>
              )}
            </span>
          </li>
        ))}
      </ul>

      <div className="text-[11px] font-bold uppercase tracking-wide text-ink-soft mb-2">
        Configured ({configured.length})
      </div>
      <ul className="flex flex-col gap-1 mb-3">
        {configured.map((s: SourceDescriptor) => (
          <li key={s.id} className="text-xs text-ink">
            <span className="font-semibold">{s.label}</span>
            <span className="text-ink-soft"> — {s.detail}</span>
          </li>
        ))}
      </ul>

      <div className="text-[11px] font-bold uppercase tracking-wide text-ink-soft mb-2">
        Dormant ({dormant.length})
      </div>
      <ul className="flex flex-col gap-1">
        {dormant.map((s: SourceDescriptor) => (
          <li key={s.id} className="text-xs text-ink-soft">
            <span className="font-semibold">{s.label}</span>
            <span> — {s.detail}</span>
          </li>
        ))}
      </ul>
      <p className="text-[11px] text-ink-soft/80 mt-3">
        {status.summary.generated_data_policy}
      </p>
    </Card>
  );
};

export const SettingsPage: React.FC = () => {
  const { user, login, logout, showToast, permissions } = useApp();
  const [demoAccounts, setDemoAccounts] = useState<DemoAccount[]>([]);
  const { language, setLanguage } = useTranslation();
  const [resetting, setResetting] = useState(false);

  const handleReset = async () => {
    setResetting(true);
    try {
      const res = await resetHeroScenario();
      showToast(res.message || 'Demo scenario reset');
      window.setTimeout(() => window.location.reload(), 700);
    } catch {
      showToast('Could not reset demo');
      setResetting(false);
    }
  };

  useEffect(() => {
    fetchDemoAccounts()
      .then(setDemoAccounts)
      .catch(() => setDemoAccounts([]));
  }, []);

  const handleSignIn = async (username: string, password: string) => {
    try {
      const u = await login(username, password);
      showToast(`Signed in as ${u.full_name.split(' ')[0]}`);
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Sign-in failed');
    }
  };

  return (
    <div className="flex flex-col gap-6 animate-rise-in max-w-4xl">
      <div>
        <div className="flex items-center gap-2 annotation text-accent-strong">
          <span className="text-accent-strong">Admin</span><span>/</span><span>Settings</span>
        </div>
        <h1 className="text-2xl font-black text-ink font-display tracking-tight mt-1">Workspace Settings</h1>
        <p className="text-sm text-ink-soft mt-1">Role controls what you can see and do across the platform.</p>
      </div>

      <Card className="p-5">
        <div className="flex items-center gap-2 text-sm font-bold text-ink mb-4">
          <ShieldCheck className="w-4 h-4 text-accent-strong" /> Account &amp; role access
        </div>

        {user ? (
          <div className="flex items-center gap-3 border-2 border-ink rounded-none bg-canvas px-3.5 py-3">
            <div className="w-9 h-9 rounded-none bg-accent-faint text-accent-strong flex items-center justify-center shrink-0">
              <UserRound className="w-5 h-5" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-bold text-ink truncate">{user.full_name}</div>
              <div className="text-[11px] font-mono text-ink-soft truncate">{user.username}</div>
              <div className="mt-1">
                <span className={`text-[10px] font-bold px-2 py-0.5 rounded-none border-2 inline-flex items-center gap-1.5 ${ROLE_BADGE_CLASSES[permissions.color as RoleColor] ?? ROLE_BADGE_FALLBACK}`}>
                  <span className="w-1.5 h-1.5 rounded-none bg-current"></span> {permissions.label}
                </span>
              </div>
            </div>
            <Button variant="danger" size="sm" onClick={logout}>
              <LogOut className="w-3.5 h-3.5" />
              Sign out
            </Button>
          </div>
        ) : (
          <div className="flex items-center gap-2.5 border-2 border-dashed border-ink rounded-none px-3.5 py-3">
            <div className="w-9 h-9 rounded-none bg-canvas text-ink-soft flex items-center justify-center shrink-0">
              <UserRound className="w-5 h-5" />
            </div>
            <div className="flex-1">
              <div className="text-sm font-bold text-ink">Public guest</div>
              <div className="text-[11px] text-ink-soft">Browse as the anonymous Public role. Sign in with a role account to unlock workspace views.</div>
            </div>
          </div>
        )}

        <div className="mt-4">
          <div className="text-[10px] font-bold text-ink-soft uppercase tracking-widest mb-2">
            Demo accounts — one-click sign-in
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {demoAccounts.map((acc) => {
              const active = user?.role_name === acc.role;
              return (
                <button
                  key={acc.username}
                  onClick={() => handleSignIn(acc.username, 'demo')}
                  disabled={active}
                  className={cn(
                    'text-left px-3.5 py-2.5 rounded-none border-2 text-xs transition disabled:opacity-60 disabled:pointer-events-none',
                    active ? 'border-ink bg-accent-faint' : 'border-ink hover:bg-canvas'
                  )}
                >
                  <span className="font-mono font-bold text-ink">{acc.username}</span>
                  <span className="block text-[11px] text-ink-soft truncate">{acc.full_name}</span>
                  <span className="block text-[10px] text-ink-mut mt-0.5">{active ? 'Active session' : 'Any password (demo)'}</span>
                </button>
              );
            })}
          </div>
        </div>
      </Card>

      <Card className="p-5">
        <div className="flex items-center gap-2 text-sm font-bold text-ink mb-4">
          <Globe className="w-4 h-4 text-accent-strong" /> Interface language
        </div>
        <div className="flex gap-2">
          {LANGUAGE_OPTIONS.map((option) => (
            <button
              key={option.code}
              onClick={() => setLanguage(option.code)}
              lang={option.code}
              className={cn(
                'px-4 py-2 rounded-none text-xs font-bold border-2 transition',
                language === option.code ? 'bg-accent text-ink border-ink' : 'bg-chalk text-ink-soft border-ink hover:bg-canvas'
              )}
            >
              {option.label}
            </button>
          ))}
        </div>
        <p className="mt-2 text-[11px] text-ink-soft">
          Language preferences are applied to shared chrome; data and identifiers remain in English originals.
        </p>
      </Card>

      <Card className="p-5">
        <div className="flex items-center gap-2 text-sm font-bold text-ink mb-1">
          <RefreshCw className="w-4 h-4 text-emerald-600" /> Demo scenario
        </div>
        <p className="text-xs text-ink-soft mb-4">
          Resets Building B-17 to its epoch-01 baseline and clears verification decisions. Synthetic loads are deterministic.
        </p>
        <div className="flex items-center gap-2">
          <Button variant="success" onClick={handleReset} disabled={resetting} size="sm">
            <RefreshCw className={cn('w-3.5 h-3.5', resetting && 'animate-spin')} />
            {resetting ? 'Resetting…' : 'Reset scenario'}
          </Button>
          <DemoHint />
        </div>
      </Card>

      <SourceStatusCard />
      <DilrmpCard />

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card className="p-4">
          <div className="flex items-center gap-2 text-sm font-bold text-ink mb-2">
            <Boxes className="w-4 h-4 text-accent-strong" /> Platform scope
          </div>
          <p className="text-xs text-ink-soft leading-relaxed">
            Bhu-Drishti 3D is a demonstration prototype for Smart India Hackathon
            (SIH 26011). This pilot mirrors Airoli Sector 8, Navi Mumbai.
          </p>
        </Card>
        <Card className="p-4">
          <div className="flex items-center gap-2 text-sm font-bold text-ink mb-2">
            <MapPin className="w-4 h-4 text-accent-strong" /> Reference standards
          </div>
          <div className="flex flex-wrap gap-1.5">
            <Badge tone="slate">ULPIN 14-digit</Badge>
            <Badge tone="slate">EPSG:7755</Badge>
            <Badge tone="slate">CityJSON 1.1</Badge>
            <Badge tone="slate">OGC</Badge>
            <Badge tone="slate">ISO/IEC 7064</Badge>
            <Badge tone="slate">Ed25519</Badge>
          </div>
        </Card>
      </div>

      <div className="text-[11px] text-ink-mut flex items-center gap-2">
        <Info className="w-3.5 h-3.5" />
        <Link to="/" className="text-accent-strong font-bold hover:underline">Back to marketing site →</Link>
      </div>
    </div>
  );
};