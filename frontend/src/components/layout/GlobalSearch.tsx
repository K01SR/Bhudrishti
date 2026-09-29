import React, { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, MapPin, Building2, Box, Layers, Loader2, CornerDownLeft, Globe2 } from 'lucide-react';
import { searchProperties } from '../../services/api';
import { SearchResult, SearchMode } from '../../types/cadastre';
import { StatusBadge } from '../ui';
import { useApp } from '../../context/AppContext';

const KIND_ICON: Record<string, React.ReactNode> = {
  jurisdiction: <Globe2 className="w-3.5 h-3.5 text-accent-strong" />,
  village: <MapPin className="w-3.5 h-3.5 text-accent-strong" />,
  parcel: <MapPin className="w-3.5 h-3.5 text-accent-strong" />,
  structure: <Building2 className="w-3.5 h-3.5 text-accent-strong" />,
  unit: <Box className="w-3.5 h-3.5 text-emerald-600" />,
  subsurface: <Layers className="w-3.5 h-3.5 text-accent-strong" />,
  elevated: <Layers className="w-3.5 h-3.5 text-ink-soft" />,
};

export const GlobalSearch: React.FC<{ autoFocus?: boolean; onNavigate?: () => void }> = ({ autoFocus, onNavigate }) => {
  const [q, setQ] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [activeIdx, setActiveIdx] = useState(0);
  // Default to `all` for the existing behaviour, but let a user who wants to be
  // certain they are reading real places ask for the real places only.
  const [mode, setMode] = useState<SearchMode>('all');
  const navigate = useNavigate();
  const { setMapFocus } = useApp();
  const containerRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<number | null>(null);

  useEffect(() => {
    if (debounceRef.current) window.clearTimeout(debounceRef.current);
    if (q.trim().length === 0) {
      setResults([]);
      setOpen(false);
      return;
    }
    setLoading(true);
    debounceRef.current = window.setTimeout(async () => {
      try {
        const res = await searchProperties(q.trim(), mode);
        setResults(res.results || []);
        setActiveIdx(0);
        setOpen(true);
      } catch {
        setResults([]);
        setOpen(false);
      } finally {
        setLoading(false);
      }
    }, 200);
    return () => {
      if (debounceRef.current) window.clearTimeout(debounceRef.current);
    };
  }, [q]);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, []);

  const getFocusTarget = (r: SearchResult): string => {
    if (r.lng !== undefined && r.lat !== undefined) {
      return `geo:${r.lng},${r.lat},${r.zoom || 14}:${r.ulpin || r.id}`;
    }
    if (r.focus?.center && r.focus.center[0] > 50 && r.focus.center[0] < 100) {
      return `geo:${r.focus.center[0]},${r.focus.center[1]},${r.zoom || 14}:${r.ulpin || r.id}`;
    }
    return r.ulpin || r.id;
  };

  const goTo = async (r: SearchResult) => {
    let focusTarget = getFocusTarget(r);
    // If this is a real LGD village with no focus, locate it on the fly.
    if (r.kind === 'village' && !r.focus && r.village_code && r.has_3d) {
      try {
        const located = await (await import('../../services/api')).locateLgdVillage(r.village_code);
        if (located?.found) {
          focusTarget = `geo:${located.lon},${located.lat},${r.zoom || 14}:${r.village_code}`;
          setMapFocus(focusTarget);
          navigate('/app/map');
          setOpen(false);
          setQ('');
          onNavigate?.();
          return;
        }
      } catch {
        // ignore and fall back to map navigation
      }
    }
    setMapFocus(focusTarget);
    if (r.kind === 'jurisdiction' || r.kind === 'village') {
      navigate('/app/map');
    } else if (r.is_hero && r.ulpin) {
      navigate(`/app/properties/${r.ulpin}${r.kind === 'unit' && r.unit_number ? `?unit=${r.unit_number}` : ''}`);
    } else if (r.kind === 'parcel' || r.kind === 'structure') {
      navigate('/app/map');
    } else if (r.ulpin) {
      navigate(`/app/properties/${r.ulpin}`);
    } else {
      navigate('/app/map');
    }
    setOpen(false);
    setQ('');
    onNavigate?.();
  };

  const goToMap = (r: SearchResult) => {
    setMapFocus(getFocusTarget(r));
    setOpen(false);
    setQ('');
    navigate('/app/map');
    onNavigate?.();
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') setOpen(false);
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIdx((i) => Math.min(i + 1, results.length - 1));
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIdx((i) => Math.max(i - 1, 0));
    }
    if (e.key === 'Enter' && results[activeIdx]) {
      goTo(results[activeIdx]);
    }
  };

  return (
    <div ref={containerRef} className="relative w-full max-w-sm">
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-ink-mut pointer-events-none" />
        <input
          value={q}
          autoFocus={autoFocus}
          onChange={(e) => setQ(e.target.value)}
          onFocus={() => results.length > 0 && setOpen(true)}
          onKeyDown={onKeyDown}
          placeholder="Search village, ULPIN, building, survey no…"
          className="w-full pl-9 pr-8 py-2 rounded-none bg-canvas hover:bg-canvas border-2 border-ink text-sm text-ink placeholder:text-ink-mut outline-none transition focus:bg-chalk focus:border-ink focus:ring-2 focus:ring-accent/15 shadow-brutal-sm"
          aria-label="Search properties"
          role="combobox"
          aria-expanded={open}
        />
        {loading && <Loader2 className="absolute right-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-accent-strong animate-spin" />}
      </div>

      {open && results.length > 0 && (
        <div className="absolute top-full left-0 right-0 mt-2 bg-chalk border-2 border-ink rounded-none shadow-brutal z-50 max-h-[26rem] overflow-y-auto">
          <div className="flex items-center justify-between gap-2 px-3 py-2 text-[10px] font-mono font-bold uppercase tracking-widest text-ink-mut border-b border-ink bg-canvas">
            <span>
              {results.length} result{results.length !== 1 ? 's' : ''}
              {mode === 'places' ? ' • official LGD places only' : ' • mixed real + modelled'}
            </span>
            <span className="shrink-0 text-ink-soft normal-case tracking-normal">Enter to open</span>
          </div>
          <div className="flex border-b border-ink bg-canvas">
            {(['all', 'places', 'records'] as SearchMode[]).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setMode(m)}
                title={
                  m === 'places'
                    ? 'Official Local Government Directory places only'
                    : m === 'records'
                      ? 'Modelled parcels and generated land records only'
                      : 'Everything, each result labelled'
                }
                className={`flex-1 px-2 py-1.5 text-[10px] font-mono font-bold uppercase tracking-widest transition ${
                  mode === m ? 'bg-ink text-chalk' : 'text-ink-mut hover:bg-chalk'
                }`}
                aria-pressed={mode === m}
              >
                {m === 'all' ? 'All' : m === 'places' ? 'Places' : 'Records'}
              </button>
            ))}
          </div>
          {results.map((r, i) => (
            <button
              key={`${r.kind}-${r.id}-${i}`}
              onMouseEnter={() => setActiveIdx(i)}
              onClick={() => goTo(r)}
              className={`w-full text-left px-3 py-2.5 flex items-center gap-3 transition ${
                i === activeIdx ? 'bg-accent-faint' : 'hover:bg-canvas'
              }`}
            >
              <span className="w-8 h-8 rounded-none bg-canvas border-2 border-ink flex items-center justify-center shrink-0 shadow-brutal-sm">
                {KIND_ICON[r.kind]}
              </span>
              <span className="flex-1 min-w-0">
                <span className="block text-xs font-bold text-ink truncate">{r.title}</span>
                <span className="block text-[11px] font-mono text-ink-soft truncate">{r.subtitle}</span>
              </span>
              <span className="flex flex-col items-end gap-1 shrink-0">
                <StatusBadge status={r.status} className="text-[9px]" />
                {r.has_3d && <span className="text-[9px] font-mono uppercase text-accent-strong">3D</span>}
              </span>
            </button>
          ))}
          <div className="px-3 py-2 border-t border-ink bg-canvas flex items-center justify-between text-[10px] text-ink-mut">
            <span className="inline-flex items-center gap-1">
              <CornerDownLeft className="w-3 h-3" /> Open property
            </span>
            <button
              onClick={() => results[activeIdx] && goToMap(results[activeIdx])}
              className="text-accent-strong font-bold hover:underline"
            >
              View on map
            </button>
          </div>
        </div>
      )}

      {open && !loading && results.length === 0 && q.trim().length > 0 && (
        <div className="absolute top-full left-0 right-0 mt-2 bg-chalk border-2 border-ink rounded-none shadow-brutal z-50 p-5 text-center">
          <p className="text-sm font-bold text-ink">No matches for “{q}”</p>
          <p className="text-xs text-ink-soft mt-1">
            Try a 14-digit ULPIN, a building code like <span className="font-mono">B-17</span>, a flat number like{' '}
            <span className="font-mono">201</span>, or a survey number like <span className="font-mono">CTS-100</span>.
          </p>
        </div>
      )}
    </div>
  );
};