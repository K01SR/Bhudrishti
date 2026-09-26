import React, { useState, useEffect } from 'react';
import { Search, X, Loader2, MapPin, Sparkles } from 'lucide-react';
import { useOpenStudioStore } from '../../store/useOpenStudioStore';

const QUICK_PRESETS = [
  { label: 'Airoli Pilot (Navi Mumbai)', center: [72.9984, 19.1557] as [number, number], zoom: 16.5 },
  { label: 'BKC Business Dist (Mumbai)', center: [72.865, 19.065] as [number, number], zoom: 16.2 },
  { label: 'Connaught Place (Delhi)', center: [77.2167, 28.6315] as [number, number], zoom: 16.0 },
  { label: 'Whitefield (Bengaluru)', center: [77.7499, 12.9698] as [number, number], zoom: 16.0 },
  { label: 'Hinjawadi Tech Park (Pune)', center: [73.7289, 18.5913] as [number, number], zoom: 16.0 },
];

export const LocationSearch: React.FC<{ onFlyTo?: (lng: number, lat: number, zoom?: number) => void }> = ({ onFlyTo }) => {
  const [query, setQuery] = useState('');
  const [focused, setFocused] = useState(false);
  const [results, setResults] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const flyToLocation = useOpenStudioStore((s) => s.flyToLocation);

  useEffect(() => {
    if (query.trim().length < 3) {
      setResults([]);
      return;
    }

    const timer = setTimeout(async () => {
      setLoading(true);
      try {
        const url = `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(
          query
        )}&format=json&limit=5&countrycodes=in&addressdetails=1`;
        const res = await fetch(url, { headers: { 'Accept-Language': 'en' } });
        if (res.ok) {
          const data = await res.json();
          setResults(data);
        }
      } catch (err) {
        console.warn('Geocoding search failed:', err);
      } finally {
        setLoading(false);
      }
    }, 450);

    return () => clearTimeout(timer);
  }, [query]);

  const handleSelect = (lng: number, lat: number, zoom = 16.5) => {
    flyToLocation([lng, lat], zoom);
    onFlyTo?.(lng, lat, zoom);
    setQuery('');
    setFocused(false);
  };

  return (
    <div className="relative w-full max-w-md">
      <div
        className={`flex items-center gap-2 px-3 py-1.5 rounded-none border bg-slate-900/95 backdrop-blur-md transition-all shadow-brutal-lg ${
          focused
            ? 'border-ink ring-2 ring-accent/20'
            : 'border-slate-700/80 hover:border-slate-600'
        }`}
      >
        <Search className="w-4 h-4 text-slate-300 flex-shrink-0" />
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => setFocused(true)}
          onBlur={() => setTimeout(() => setFocused(false), 250)}
          placeholder="Search any city, road, or village in India..."
          className="bg-transparent text-xs text-white placeholder-slate-400 outline-none w-full min-w-0 font-sans"
        />
        {query && (
          <button
            onClick={() => setQuery('')}
            className="text-slate-300 hover:text-white transition flex-shrink-0"
          >
            {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin text-slate-300" /> : <X className="w-3.5 h-3.5" />}
          </button>
        )}
      </div>

      {/* Dropdown Suggestions */}
      {focused && (
        <div className="absolute top-full left-0 right-0 mt-2 bg-slate-900/98 border border-slate-700/90 rounded-none shadow-brutal-xl backdrop-blur-xl z-50 overflow-hidden divide-y divide-slate-800 animate-rise-in max-h-72 overflow-y-auto">
          {query.trim().length < 3 && (
            <div className="p-2 space-y-1">
              <span className="px-2 py-1 text-[10px] font-mono uppercase font-bold text-slate-300 flex items-center gap-1">
                <Sparkles className="w-3 h-3 text-slate-300" /> Quick Geo-Jumps:
              </span>
              {QUICK_PRESETS.map((p) => (
                <button
                  key={p.label}
                  onClick={() => handleSelect(p.center[0], p.center[1], p.zoom)}
                  className="w-full text-left px-3 py-1.5 text-xs text-slate-300 hover:text-white hover:bg-slate-800/80 rounded-none transition flex items-center gap-2"
                >
                  <MapPin className="w-3 h-3 text-slate-300 flex-shrink-0" />
                  <span>{p.label}</span>
                </button>
              ))}
            </div>
          )}

          {query.trim().length >= 3 && results.length === 0 && !loading && (
            <div className="px-4 py-3 text-xs text-slate-300 italic text-center">
              No matching Indian localities found for "{query}"
            </div>
          )}

          {results.map((r, idx) => (
            <button
              key={idx}
              onClick={() => handleSelect(parseFloat(r.lon), parseFloat(r.lat), 16.5)}
              className="w-full text-left px-3.5 py-2 text-xs text-slate-300 hover:text-white hover:bg-slate-800/90 transition flex items-start gap-2.5"
            >
              <MapPin className="w-3.5 h-3.5 text-slate-300 flex-shrink-0 mt-0.5" />
              <div className="min-w-0">
                <div className="font-bold text-white truncate">{r.name || r.display_name.split(',')[0]}</div>
                <div className="text-[11px] text-slate-300 truncate mt-0.5">{r.display_name}</div>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
};
