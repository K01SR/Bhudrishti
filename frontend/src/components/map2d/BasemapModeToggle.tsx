import React from 'react';
import { Sun, Moon, MapPin, MapPinOff } from 'lucide-react';

import type { BasemapPref } from '../../services/cartoBasemap';

interface Props {
  pref: BasemapPref;
  onChange: (next: BasemapPref) => void;
  /** Compact variant for the open-twin overlay, where chrome must stay thin. */
  compact?: boolean;
  theme?: 'dark' | 'light';
}

/**
 * Light/dark + labels control for the two MapLibre views.
 *
 * The basemap can be changed without rebuilding the map style object, which is
 * why this is a small shared component rather than a per-view dropdown: both
 * views do the same three-line dance, and having one copy means a fix to the
 * tile URL or the ARIA wiring lands in both.
 */
export const BasemapModeToggle: React.FC<Props> = ({ pref, onChange, compact = false, theme = 'dark' }) => {
  const isDark = theme === 'dark';
  const btn = compact
    ? 'w-7 h-7 flex items-center justify-center transition-colors'
    : 'w-8 h-8 flex items-center justify-center transition-colors';
  const activeCls = isDark
    ? 'bg-cyan-500/20 text-cyan-300'
    : 'bg-amber-500/20 text-amber-700';
  const idleCls = isDark
    ? 'text-slate-400 hover:text-slate-200 hover:bg-white/10'
    : 'text-slate-500 hover:text-slate-800 hover:bg-black/5';

  const group = isDark
    ? 'flex items-center gap-0.5 rounded-md bg-slate-900/85 border border-white/10 backdrop-blur-sm'
    : 'flex items-center gap-0.5 rounded-md bg-white/90 border border-slate-300 backdrop-blur-sm';

  return (
    <div
      className={group}
      role="group"
      aria-label="Basemap display options"
      data-testid="basemap-mode-toggle"
    >
      <button
        type="button"
        className={`${btn} rounded ${pref.theme === 'dark' ? activeCls : idleCls}`}
        onClick={() => onChange({ ...pref, theme: 'dark' })}
        aria-pressed={pref.theme === 'dark'}
        title="Dark basemap"
        aria-label="Dark basemap"
      >
        <Moon className={compact ? 'w-3.5 h-3.5' : 'w-4 h-4'} />
      </button>
      <button
        type="button"
        className={`${btn} rounded ${pref.theme === 'light' ? activeCls : idleCls}`}
        onClick={() => onChange({ ...pref, theme: 'light' })}
        aria-pressed={pref.theme === 'light'}
        title="Light basemap"
        aria-label="Light basemap"
      >
        <Sun className={compact ? 'w-3.5 h-3.5' : 'w-4 h-4'} />
      </button>
      <span
        className={isDark ? 'w-px h-4 bg-white/15 mx-0.5' : 'w-px h-4 bg-slate-300 mx-0.5'}
        aria-hidden="true"
      />
      <button
        type="button"
        className={`${btn} rounded ${pref.labels ? activeCls : idleCls}`}
        onClick={() => onChange({ ...pref, labels: !pref.labels })}
        aria-pressed={pref.labels}
        title={pref.labels ? 'Hide place labels' : 'Show place labels'}
        aria-label={pref.labels ? 'Hide place labels' : 'Show place labels'}
      >
        {pref.labels ? (
          <MapPin className={compact ? 'w-3.5 h-3.5' : 'w-4 h-4'} />
        ) : (
          <MapPinOff className={compact ? 'w-3.5 h-3.5' : 'w-4 h-4'} />
        )}
      </button>
    </div>
  );
};
