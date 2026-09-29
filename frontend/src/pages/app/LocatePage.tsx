import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  MapPin, Search, Building2, ChevronDown, ChevronRight, Loader2,
  Landmark, Layers, Home, ArrowUpRight,
} from 'lucide-react';
import {
  fetchStates, fetchDistricts, fetchTalukas, fetchVillages,
  fetchParcelsByLocation,
  LocationNode, ParcelListItem,
} from '../../services/api';
import { Card, Button } from '../../components/ui';
import { cn } from '../../lib/cn';

const LabeledField: React.FC<{ label: string; className?: string; children: React.ReactNode }> = ({ label, className, children }) => (
  <label className={cn('block', className)}>
    <span className="block text-xs font-bold text-ink mb-1.5">{label}</span>
    {children}
  </label>
);

const selectCls =
  'w-full appearance-none rounded-none border-2 border-ink bg-chalk px-3.5 py-2.5 pr-9 text-sm font-bold text-ink shadow-brutal-sm outline-none transition focus:border-accent/50 focus:ring-2 focus:ring-accent/20 disabled:opacity-45';

export const LocatePage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const [states, setStates] = useState<LocationNode[]>([]);
  const [districts, setDistricts] = useState<LocationNode[]>([]);
  const [talukas, setTalukas] = useState<LocationNode[]>([]);
  const [villages, setVillages] = useState<LocationNode[]>([]);

  const [selState, setSelState] = useState(searchParams.get('s') ?? '');
  const [selDistrict, setSelDistrict] = useState(searchParams.get('d') ?? '');
  const [selTaluka, setSelTaluka] = useState(searchParams.get('t') ?? '');
  const [selVillage, setSelVillage] = useState(searchParams.get('v') ?? '');
  const [query, setQuery] = useState(searchParams.get('q') ?? '');

  const [results, setResults] = useState<ParcelListItem[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const breadcrumb = useMemo(() => {
    const name = (code: string, list: LocationNode[]) => list.find((x) => x.code === code)?.name ?? code;
    return [name(selState, states), name(selDistrict, districts), name(selTaluka, talukas), name(selVillage, villages)].filter(Boolean);
  }, [selState, selDistrict, selTaluka, selVillage, states, districts, talukas, villages]);

  const pushParcels = (opts: Record<string, string>) => {
    const params = new URLSearchParams();
    Object.entries(opts).forEach(([k, v]) => { if (v) params.set(k, v); });
    setSearchParams(params, { replace: true });
  };

  useEffect(() => { fetchStates().then(setStates).catch(() => setStates([])); }, []);

  useEffect(() => {
    if (!selState) { setDistricts([]); setTalukas([]); setVillages([]); return; }
    fetchDistricts(selState).then(setDistricts).catch(() => setDistricts([]));
  }, [selState]);

  useEffect(() => {
    if (!selState || !selDistrict) { setTalukas([]); setVillages([]); return; }
    fetchTalukas(selState, selDistrict).then(setTalukas).catch(() => setTalukas([]));
  }, [selState, selDistrict]);

  useEffect(() => {
    if (!selState || !selDistrict || !selTaluka) { setVillages([]); return; }
    fetchVillages(selState, selDistrict, selTaluka).then(setVillages).catch(() => setVillages([]));
  }, [selState, selDistrict, selTaluka]);

  const runSearch = async () => {
    if (!selState && !query) return;
    setLoading(true);
    setError(null);
    try {
      const rows = await fetchParcelsByLocation({
        state: selState || undefined,
        district: selDistrict || undefined,
        taluka: selTaluka || undefined,
        village: selVillage || undefined,
        q: query || undefined,
        limit: 250,
      });
      setResults(rows);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Search failed');
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  const selectChange = (key: 's' | 'd' | 't' | 'v', value: string) => {
    if (key === 's') { setSelState(value); setSelDistrict(''); setSelTaluka(''); setSelVillage(''); }
    if (key === 'd') { setSelDistrict(value); setSelTaluka(''); setSelVillage(''); }
    if (key === 't') { setSelTaluka(value); setSelVillage(''); }
    if (key === 'v') setSelVillage(value);
    pushParcels({ s: key === 's' ? value : selState, d: key === 'd' ? value : key === 't' || key === 'v' ? selDistrict : selDistrict, t: key === 't' ? value : key === 'v' ? selTaluka : selTaluka, v: key === 'v' ? value : selVillage });
  };

  return (
    <div className="flex flex-col gap-5 animate-rise-in">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 annotation text-accent-strong">
            <span className="text-accent-strong">Citizen / Builder</span><span>/</span><span>Locate property</span>
          </div>
          <h1 className="text-2xl font-black text-ink font-display tracking-tight mt-1">Locate by Place</h1>
          <p className="text-sm text-ink mt-1 max-w-xl">
            Search the demo dataset using its State → District → Taluka → Village list, or jump straight in with an identifier or survey number. The place list is a hardcoded seed covering the pilot area, not an official gazetteer.
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs bg-canvas border-2 border-ink rounded-none px-3.5 py-2 text-ink-mut font-mono">
          <Landmark className="w-3.5 h-3.5 text-accent-strong" />
          <span>CENTRAL REFERENCE: MH / THN / THN-THA / AIR-SEC08</span>
        </div>
      </div>

      <Card className="p-4 sm:p-5">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
          <LabeledField label="State">
            <div className="relative">
              <select className={selectCls} aria-label="State" value={selState} onChange={(e) => selectChange('s', e.target.value)}>
                <option value="">All states</option>
                {states.map((s) => <option key={s.code} value={s.code}>{s.name}</option>)}
              </select>
              <ChevronDown className="w-4 h-4 text-ink-mut absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none" />
            </div>
          </LabeledField>
          <LabeledField label="District">
            <div className="relative">
              <select className={selectCls} aria-label="District" value={selDistrict} disabled={!selState} onChange={(e) => selectChange('d', e.target.value)}>
                <option value="">All districts</option>
                {districts.map((d) => <option key={d.code} value={d.code}>{d.name}</option>)}
              </select>
              <ChevronDown className="w-4 h-4 text-ink-mut absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none" />
            </div>
          </LabeledField>
          <LabeledField label="Taluka">
            <div className="relative">
              <select className={selectCls} aria-label="Taluka" value={selTaluka} disabled={!selDistrict} onChange={(e) => selectChange('t', e.target.value)}>
                <option value="">All talukas</option>
                {talukas.map((tl) => <option key={tl.code} value={tl.code}>{tl.name}</option>)}
              </select>
              <ChevronDown className="w-4 h-4 text-ink-mut absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none" />
            </div>
          </LabeledField>
          <LabeledField label="Village / Ward">
            <div className="relative">
              <select className={selectCls} aria-label="Village" value={selVillage} disabled={!selTaluka} onChange={(e) => selectChange('v', e.target.value)}>
                <option value="">All villages</option>
                {villages.map((v) => <option key={v.code} value={v.code}>{v.name}</option>)}
              </select>
              <ChevronDown className="w-4 h-4 text-ink-mut absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none" />
            </div>
          </LabeledField>
          <div className="flex items-end gap-2">
            <LabeledField label="ULPIN / Survey #" className="flex-1">
              <div className="relative">
                <input
                  className="w-full rounded-none border-2 border-ink bg-chalk px-3.5 py-2.5 pr-9 text-sm font-mono font-bold text-ink shadow-brutal-sm outline-none transition focus:border-accent/50 focus:ring-2 focus:ring-accent/20"
                  placeholder="e.g. 12345…"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') runSearch(); }}
                />
                <Search className="w-4 h-4 text-ink-mut absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none" />
              </div>
            </LabeledField>
            <Button onClick={runSearch} disabled={loading || (!selState && !query)} className="h-[42px] shrink-0">
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />} Search
            </Button>
          </div>
        </div>

        {(breadcrumb.length > 0 || query) && (
          <div className="mt-4 flex items-center gap-1.5 flex-wrap text-xs">
            {breadcrumb.length > 0 ? (
              breadcrumb.map((crumb, i) => (
                <React.Fragment key={crumb + i}>
                  <span className={cn('font-mono font-bold', i === breadcrumb.length - 1 ? 'text-accent-strong' : 'text-ink')}>{crumb}</span>
                  {i < breadcrumb.length - 1 && <ChevronRight className="w-3 h-3 text-ink-mut" />}
                </React.Fragment>
              ))
            ) : (
              <span className="text-ink-mut font-mono">Free-text query active</span>
            )}
          </div>
        )}
      </Card>

      {error && (
        <div className="rounded-none border-2 border-ink bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="text-xs text-ink-mut font-mono flex items-center gap-2">
        <Search className="w-3.5 h-3.5" />
        <span>{results ? `${results.length} records shown` : 'No search yet — pick a place or type an ULPIN'}</span>
      </div>

      {results && results.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          {results.map((p) => (
            <button
              key={p.ulpin}
              onClick={() => navigate(`/app/properties/${p.ulpin}`)}
              className="group text-left bg-chalk border-2 border-ink rounded-none p-4 shadow-brutal-sm transition hover:-translate-y-0.5 hover:border-ink hover:shadow-peak"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-2 min-w-0">
                  {p.building ? <Building2 className="w-4 h-4 text-accent-strong shrink-0" /> : <Home className="w-4 h-4 text-ink-mut shrink-0" />}
                  <span className="font-mono font-bold text-ink truncate">{p.building?.name || p.building?.code || p.survey_number}</span>
                </div>
                {p.building?.has_3d ? (
                  <span className="text-[9px] font-bold uppercase tracking-widest text-emerald-700 bg-emerald-50 border-2 border-ink px-1.5 py-0.5 rounded-none shrink-0">
                    3D model available
                  </span>
                ) : (
                  <span className="text-[9px] font-bold uppercase tracking-widest text-ink-soft bg-canvas border-2 border-ink px-1.5 py-0.5 rounded-none shrink-0">
                    2D Cadastre
                  </span>
                )}
              </div>
              <div className="mt-2 font-mono text-[11px] text-ink-mut flex items-center justify-between">
                <span>{p.ulpin}</span>
                {p.survey_number && <span className="text-[10px] text-ink-soft">Survey {p.survey_number}</span>}
              </div>
              <div className="mt-2.5 flex items-center gap-1.5 text-xs text-ink">
                <MapPin className="w-3 h-3 text-accent-strong shrink-0" />
                <span className="truncate">{p.location.state} / {p.location.district} / {p.location.taluka} / {p.location.village_ward}</span>
              </div>
              <div className="mt-2 flex items-center justify-between text-[11px]">
                <span className="text-ink-mut font-mono">
                  {(p.document_area_m2 ?? p.calculated_area_m2 ?? 0) > 10000 
                    ? `${(((p.document_area_m2 ?? p.calculated_area_m2 ?? 0)) / 10000).toFixed(2)} ha` 
                    : `${(p.document_area_m2 ?? p.calculated_area_m2 ?? 0).toLocaleString()} m²`}
                  {p.building ? ` · ${p.building.floors}F · FSI ${p.building.fsi || 1.8}` : ''}
                </span>
                <span className="inline-flex items-center gap-1 text-accent-strong font-bold opacity-0 group-hover:opacity-100 transition">Open <ArrowUpRight className="w-3 h-3" /></span>
              </div>
            </button>
          ))}
        </div>
      )}

      {results && results.length === 0 && (
        <Card className="p-8 text-center">
          <Layers className="w-8 h-8 text-ink-mut mx-auto" />
          <div className="mt-3 text-sm font-bold text-ink">No parcels match this selection</div>
          <div className="mt-1 text-xs text-ink">Try widening the location, or clear the state filter to run a ULPIN survey-number search.</div>
        </Card>
      )}
    </div>
  );
};