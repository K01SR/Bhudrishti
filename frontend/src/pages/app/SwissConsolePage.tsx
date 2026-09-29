import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Masthead,
  SectionLabel,
  Stat,
  Row,
  Bar,
  Cell,
  SwissGrid,
  UnverifiedNote,
  SWISS,
} from '../../components/swiss/Swiss';
import { Skeleton } from '../../components/ui';

const API = (import.meta as any).env?.VITE_API_URL || '/api/v1';

/**
 * What `/osm/summary` computes, versus what it asserts.
 *
 * The handler builds `total_roads_km`, `streetlights_installed`,
 * `shade_trees_planted` and `total_pois` by counting and measuring the actual
 * OSM arrays it returns. Everything else in the response — the road-class
 * breakdown, every civic count, and the whole `geospatial_accuracy` block — is a
 * literal in the handler. In particular it reports
 * `dgps_rtk_closure_error_mm: 2.4`, `elevation_datum: "Survey of India GTS
 * Benchmark"` and `horizontal_tolerance_m: "< 0.02m (Survey Grade)"`. Those are
 * claims of survey-grade government certification. Nothing in this system has
 * been surveyed to that tolerance, so they are read, counted, and then
 * deliberately not displayed.
 *
 * Keeping the split explicit here means adding a real measurement to the
 * backend later is a one-line change to COMPUTED, rather than a hunt through a
 * page wondering which fields were ever honest.
 */
const COMPUTED_FABRIC = ['total_roads_km', 'streetlights_installed', 'shade_trees_planted'] as const;
const COMPUTED_AMENITIES = ['total_pois'] as const;

type Panel = { ok: true; data: any } | { ok: false; reason: string };

function usePanel(path: string | null, deps: unknown[] = []): Panel | null {
  const [panel, setPanel] = useState<Panel | null>(null);
  useEffect(() => {
    if (!path) return;
    let active = true;
    setPanel(null);
    fetch(`${API}${path}`)
      .then(async (r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data) => active && setPanel({ ok: true, data }))
      .catch((e) => active && setPanel({ ok: false, reason: e?.message || 'request failed' }));
    return () => {
      active = false;
    };
  }, [path, ...deps]);
  return panel;
}

/** Renders a figure, or '--' plus the reason it is absent. */
function figure(v: unknown, unit = ''): { text: string; sub?: string } {
  if (v === null || v === undefined || Number.isNaN(v)) return { text: '--', sub: 'not reported by this endpoint' };
  return { text: `${v}${unit}` };
}

export const SwissConsolePage: React.FC = () => {
  const stats = usePanel('/opendata/stats');
  const benchmarks = usePanel('/system/benchmarks');
  const fabric = usePanel('/osm/summary');
  const validation = usePanel('/validation/run');

  const loading = stats === null || benchmarks === null;

  return (
    <div className="flex flex-col gap-8 animate-rise-in">
      <Masthead
        eyebrow="Bhu-Drishti / Operations"
        title="System Console"
        lede="Measured state of the platform. Every figure on this page is computed at request time from data this deployment actually holds. Fields the backend returns but does not compute are listed as unmeasured rather than shown, because a number that was typed into a handler is not an observation."
        right={
          <Link
            to="/app"
            className="annotation uppercase tracking-[0.18em] border-2 border-ink px-3 py-1.5 text-ink hover:bg-ink hover:text-chalk transition-colors"
          >
            Back to app
          </Link>
        }
      />

      {loading && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Skeleton className="h-28" />
          <Skeleton className="h-28" />
          <Skeleton className="h-28" />
        </div>
      )}

      {/* ---------------------------------------------------------------- */}
      {/* Open-data inventory                                               */}
      {/* ---------------------------------------------------------------- */}
      {stats?.ok && (
        <section>
          <SectionLabel note="/opendata/stats">Open-data inventory</SectionLabel>
          <SwissGrid>
            <Cell span={8}>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-5">
                <Stat label="Buildings held" value={figure(stats.data.total_buildings).text} />
                <Stat label="Regions cached" value={figure(stats.data.regions_cached).text} />
                <Stat label="Cache entries" value={figure(stats.data.cache).text} />
                <Stat
                  label="Authoritative regions"
                  value={figure(stats.data.authoritative_regions).text}
                  sub="regions with a government-graded source"
                  emphasis={stats.data.authoritative_regions === 0}
                />
              </div>
              <UnverifiedNote>
                An authoritative region means the underlying record comes from a government-graded
                source. This deployment holds none, so every figure elsewhere in the product is
                OSM- or GlobalML-derived and is labelled as such.
              </UnverifiedNote>
            </Cell>
            <Cell span={4}>
              <div className="annotation text-ink-mut uppercase tracking-[0.14em] mb-2">Providers</div>
              <div className="space-y-3">
                <div>
                  <div className="text-xs text-ink-soft mb-1">Configured</div>
                  <div className="flex flex-wrap gap-1.5">
                    {(stats.data.providers_configured ?? []).map((p: string) => (
                      <span key={p} className="font-mono text-[11px] border border-ink px-1.5 py-0.5 text-ink">
                        {p}
                      </span>
                    ))}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-ink-soft mb-1">Not configured</div>
                  <div className="flex flex-wrap gap-1.5">
                    {(stats.data.providers_unconfigured ?? []).map((p: string) => (
                      <span
                        key={p}
                        className="font-mono text-[11px] border px-1.5 py-0.5"
                        style={{ borderColor: SWISS.rule, color: 'var(--ink-mut, #64748b)' }}
                      >
                        {p}
                      </span>
                    ))}
                  </div>
                </div>
                <div className="pt-1">
                  <Row k="Fetch calls" v={figure(stats.data.fetch).text} />
                  <Row k="Failed calls" v={figure(stats.data.fail).text} />
                </div>
              </div>
            </Cell>
          </SwissGrid>
        </section>
      )}
      {stats && !stats.ok && (
        <section>
          <SectionLabel>Open-data inventory</SectionLabel>
          <p className="text-sm text-ink-soft">
            Unavailable: <span className="font-mono">{stats.reason}</span>
          </p>
        </section>
      )}

      {/* ---------------------------------------------------------------- */}
      {/* Pipeline benchmarks                                               */}
      {/* ---------------------------------------------------------------- */}
      {benchmarks?.ok && benchmarks.data.ground_profile && (
        <section>
          <SectionLabel note="/system/benchmarks">Ground-profile pipeline</SectionLabel>
          <SwissGrid>
            <Cell span={7}>
              <div className="annotation text-ink-mut uppercase tracking-[0.14em] mb-3">
                {benchmarks.data.pipeline}
              </div>
              <Bar
                pct={100}
                label="Python (numpy reference)"
                note={`${benchmarks.data.ground_profile.python_ms?.toFixed?.(1) ?? '--'} ms`}
              />
              <Bar
                pct={100 * (benchmarks.data.ground_profile.rust_ms / benchmarks.data.ground_profile.python_ms)}
                label="Rust native"
                note={`${benchmarks.data.ground_profile.rust_ms?.toFixed?.(1) ?? '--'} ms · ${benchmarks.data.ground_profile.speedup_rust_vs_python ?? '--'}`}
              />
              <Bar
                pct={100 * (benchmarks.data.ground_profile.cpp_ms / benchmarks.data.ground_profile.python_ms)}
                label="C++ native (in-process)"
                note={`${benchmarks.data.ground_profile.cpp_ms?.toFixed?.(1) ?? '--'} ms · ${benchmarks.data.ground_profile.speedup_cpp_vs_python ?? '--'}`}
              />
              <p className="mt-3 text-[11px] text-ink-mut leading-relaxed">{benchmarks.data.ground_profile.note}</p>
            </Cell>
            <Cell span={5}>
              <Row k="Workload" v={<span className="text-ink-soft">{benchmarks.data.ground_profile.workload ?? '--'}</span>} mono={false} />
              <Row k="Rust available" v={String(benchmarks.data.rust_available ?? '--')} />
              <Row k="Binary checked" v={String(benchmarks.data.binary_checked ?? '--')} />
              <Row k="Total (bulk)" v={`${benchmarks.data.total_ms?.toFixed?.(1) ?? '--'} ms`} />
            </Cell>
          </SwissGrid>
        </section>
      )}

      {/* ---------------------------------------------------------------- */}
      {/* Precinct fabric — computed fields only                            */}
      {/* ---------------------------------------------------------------- */}
      {fabric?.ok && (
        <section>
          <SectionLabel note="/osm/summary">Precinct fabric</SectionLabel>
          <SwissGrid>
            <Cell span={4}>
              <div className="annotation text-ink-mut uppercase tracking-[0.14em] mb-3">{fabric.data.precinct}</div>
              <Row k="District" v={fabric.data.district ?? '--'} mono={false} />
              <Row k="Corporation" v={fabric.data.municipal_corporation ?? '--'} mono={false} />
              <Row k="CRS" v={fabric.data.crs ?? '--'} />
            </Cell>
            <Cell span={4}>
              <div className="annotation text-ink-mut uppercase tracking-[0.14em] mb-3">Urban fabric</div>
              {COMPUTED_FABRIC.map((k) => {
                const v = fabric.data.urban_fabric?.[k];
                return <Row key={k} k={k.replace(/_/g, ' ')} v={figure(v, k === 'total_roads_km' ? ' km' : '').text} />;
              })}
            </Cell>
            <Cell span={4}>
              <div className="annotation text-ink-mut uppercase tracking-[0.14em] mb-3">Civic amenities</div>
              {COMPUTED_AMENITIES.map((k) => (
                <Row key={k} k={k.replace(/_/g, ' ')} v={figure(fabric.data.civic_amenities?.[k]).text} />
              ))}
              <UnverifiedNote>
                The endpoint also returns parks, ward offices, clinics, police posts, EV hubs,
                substations and transit shelters — each hardcoded to <span className="font-mono">1</span> —
                plus a <span className="font-mono">geospatial_accuracy</span> block asserting RTK-grade
                closure error against a Survey of India datum at survey-grade tolerance. None of it
                is measured, so none of it is shown, and its figures are not restated here.
              </UnverifiedNote>
            </Cell>
          </SwissGrid>
        </section>
      )}

      {/* ---------------------------------------------------------------- */}
      {/* Validation                                                        */}
      {/* ---------------------------------------------------------------- */}
      {validation && (
        <section>
          <SectionLabel note="/validation/run">Validation</SectionLabel>
          {validation.ok ? (
            <Cell span={12}>
              <pre className="font-mono text-[11px] text-ink-soft overflow-x-auto whitespace-pre-wrap">
                {JSON.stringify(validation.data, null, 2).slice(0, 1200)}
              </pre>
            </Cell>
          ) : (
            <Cell span={12}>
              <p className="text-sm text-ink-soft">
                Unavailable: <span className="font-mono">{validation.reason}</span>
              </p>
            </Cell>
          )}
        </section>
      )}

      <footer className="border-t-2 border-ink pt-4 pb-2">
        <p className="text-[11px] text-ink-mut leading-relaxed max-w-3xl">
          Design: Swiss International Style, applied inside the application rather than imported from the
          marketing surface. The landing page renders theme variants of the same idiom alongside invented
          registry statistics; those figures are not reproduced here, and the landing files remain
          untouched under their byte-identical protection.
        </p>
      </footer>
    </div>
  );
};
