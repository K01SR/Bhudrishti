import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Boxes, MapPin, ArrowUpRight, Box, Building2, SlidersHorizontal } from 'lucide-react';
import { fetchParcels, fetchHeroProperty } from '../../services/api';
import { ParcelSummary, HeroProperty } from '../../types/cadastre';
import { Card, Badge, StatusBadge, Button, Skeleton, EmptyState, DemoHint } from '../../components/ui';
import { cn } from '../../lib/cn';
import { DEMO_ULPIN } from '../../constants';

export const PropertyRegistry: React.FC = () => {
  const navigate = useNavigate();
  const [parcels, setParcels] = useState<ParcelSummary[]>([]);
  const [hero, setHero] = useState<HeroProperty | null>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<'ALL' | 'WITH_3D'>('ALL');

  useEffect(() => {
    let active = true;
    Promise.all([fetchParcels(), fetchHeroProperty()])
      .then(([p, h]) => {
        if (!active) return;
        setParcels(p);
        setHero(h);
      })
      .catch((err) => console.error('Registry load failed', err))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, []);

  const heroUlpin = DEMO_ULPIN;
  const filtered = filter === 'WITH_3D' ? parcels.filter((p) => p.has_3d) : parcels;
  const twinCount = parcels.filter((p) => p.has_3d).length;
  const verifiedCount = parcels.filter((p) => p.status === 'VERIFIED').length;

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex items-center gap-3">
          <span className="w-1 h-9 bg-accent" />
          <div>
            <div className="flex items-center gap-2 annotation text-accent-strong">
              <span>Prototype</span><span className="text-ink-mut">/</span><span className="text-ink-soft">Properties</span>
            </div>
            <h1 className="text-3xl font-black text-ink font-display tracking-tight mt-1">Property Registry</h1>
            <p className="text-sm text-ink-soft mt-1.5">
              Every parcel in the demo precinct. Some carry a full 3D twin; the rest are shallow records with no
              vertical model. This is a synthetic dataset, not a government land record.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Badge tone="blue" dot>Airoli S8</Badge>
          <DemoHint />
        </div>
      </div>

      {/* Coverage summary */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-px bg-canvas border-2 border-ink rounded-none overflow-hidden">
        <div className="bg-chalk p-4">
          <div className="annotation text-ink-mut">Parcels</div>
          <div className="mt-1.5 text-2xl font-black font-mono text-ink">{parcels.length || '—'}</div>
        </div>
        <div className="bg-chalk p-4">
          <div className="annotation text-ink-mut">3D twins</div>
          <div className="mt-1.5 text-2xl font-black font-mono text-accent-strong">{parcels.length ? twinCount : '—'}</div>
          <div className="text-[11px] text-ink-soft">of {parcels.length || '—'} parcels</div>
        </div>
        <div className="bg-chalk p-4">
          <div className="annotation text-ink-mut">Strata units</div>
          <div className="mt-1.5 text-2xl font-black font-mono text-emerald-700">{hero?.units.length ?? '—'}</div>
        </div>
        <div className="bg-chalk p-4">
          <div className="annotation text-ink-mut">Verified</div>
          <div className={cn('mt-1.5 text-2xl font-black font-mono', verifiedCount ? 'text-emerald-700' : 'text-ink')}>
            {parcels.length ? verifiedCount : '—'}
          </div>
          <div className="text-[11px] text-ink-soft">structures marked verified</div>
        </div>
      </div>

      {/* Filter bar */}
      <div className="flex items-center gap-2">
        <SlidersHorizontal className="w-3.5 h-3.5 text-ink-mut" />
        {(['ALL', 'WITH_3D'] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={cn(
              'px-3 py-1.5 rounded-none text-xs font-bold border-2 transition',
              filter === f ? 'bg-accent text-ink border-ink shadow-brutal-sm' : 'bg-chalk text-ink border-ink hover:bg-canvas'
            )}
          >
            {f === 'ALL' ? `All (${parcels.length})` : `With 3D twin (${twinCount})`}
          </button>
        ))}
      </div>

      {/* Registry rows */}
      {loading ? (
        <Card className="p-0 divide-y divide-ink/10">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="p-4 flex items-center gap-4">
              <Skeleton className="w-10 h-10 rounded-none" />
              <div className="flex-1 space-y-2">
                <Skeleton className="h-3.5 w-1/3" />
                <Skeleton className="h-2.5 w-1/4" />
              </div>
            </div>
          ))}
        </Card>
      ) : filtered.length === 0 ? (
        <Card>
          <EmptyState icon={<Boxes className="w-5 h-5" />} title="No parcels match" description="Try clearing the filter." />
        </Card>
      ) : (
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="annotation text-ink-mut border-b border-ink bg-canvas">
                  <th className="px-4 py-2.5">Parcel</th>
                  <th className="px-4 py-2.5">Survey</th>
                  <th className="px-4 py-2.5 hidden sm:table-cell">Area (m²)</th>
                  <th className="px-4 py-2.5">3D twin</th>
                  <th className="px-4 py-2.5 hidden md:table-cell">Status</th>
                  <th className="px-4 py-2.5 text-right">Open</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink/10">
                {filtered.map((p) => {
                  const isHero = p.ulpin === heroUlpin;
                  return (
                    <tr
                      key={p.ulpin}
                      onClick={() => navigate(`/app/properties/${p.ulpin}`)}
                      className="group hover:bg-canvas cursor-pointer transition"
                    >
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-3">
                          <span className={cn('w-9 h-9 rounded-none border-2 flex items-center justify-center shrink-0', isHero ? 'bg-accent text-white border-ink' : 'bg-chalk text-ink-soft border-ink group-hover:border-ink')}>
                            {isHero ? <Building2 className="w-4 h-4" /> : <MapPin className="w-4 h-4" />}
                          </span>
                          <div>
                            <div className="font-mono text-xs font-bold text-ink">{p.ulpin}</div>
                            <div className="text-[11px] text-ink-soft">
                              {isHero ? hero?.structure?.name || 'Demo structure' : p.has_3d ? (p.building?.name || 'Demo structure') : `Demo parcel CTS-${p.survey_number}`}
                            </div>
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-3 font-mono text-xs text-ink">{p.survey_number}</td>
                      <td className="px-4 py-3 hidden sm:table-cell font-mono text-xs text-ink">{p.calculated_area_m2 ?? p.document_area_m2}</td>
                      <td className="px-4 py-3">
                        {p.has_3d ? <Badge tone="sky">Full</Badge> : <Badge tone="slate">None</Badge>}
                      </td>
                      <td className="px-4 py-3 hidden md:table-cell">
                        <StatusBadge status={p.status || 'UNSPECIFIED'} className="text-[9px]" />
                      </td>
                      <td className="px-4 py-3 text-right">
                        <ArrowUpRight className="w-4 h-4 text-ink-mut group-hover:text-accent-strong group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition inline" />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      <div className="flex items-center justify-between">
        <div className="text-[11px] text-ink-soft flex items-center gap-2">
          <Box className="w-3.5 h-3.5 text-ink-mut" />
          Non-hero records are intentionally shallow: the demo dataset carries a full vertical model for Building B-17 only.
        </div>
        <Button variant="secondary" size="sm" to="/app/map">
          <Boxes className="w-3.5 h-3.5" /> View on map
        </Button>
      </div>
    </div>
  );
};