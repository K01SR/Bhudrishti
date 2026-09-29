import React, { useState, useEffect } from 'react';
import { Search, Sparkles, CornerDownLeft, Map as MapIcon } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { askTheMap } from '../../services/api';
import { useApp } from '../../context/AppContext';
import { Modal, Button, Badge } from '../ui';

interface Props {
  isOpen: boolean;
  onClose: () => void;
}

type AskResult = {
  intent_category?: string;
  matched_entity_ids?: string[];
  /**
   * The 3D studio's local scene focus point and highlight colour. Both are
   * needed to place the pointer on the 2D map views: the scene point is not a
   * longitude, so it has to be run through the local-to-geo transform before
   * either 2D map can fly to it.
   */
  highlight_3d?: { mode?: string; focus_point?: number[]; highlight_color?: string };
  human_explanation?: string;
  execution_time_ms?: number;
  /** How many dataset records actually matched. Zero means nothing was found. */
  match_count?: number;
  /** Where the answer was read from, e.g. a dataset field or helper function. */
  data_source?: string;
  /**
   * The exact predicate that ran against the store, e.g.
   * {dataset_field: "units", unit_type: "RESIDENTIAL"}. Rendered verbatim so a
   * reader can tell which records were in scope without reading the prose.
   */
  matched_filter?: Record<string, unknown>;
  synthetic?: boolean;
  /** Why this answer must not be read as a real-world finding. */
  limitations?: string[];
  disclaimer?: string;
};

export const AskTheMapModal: React.FC<Props> = ({ isOpen, onClose }) => {
  const [query, setQuery] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState<AskResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { applyHighlight, showToast } = useApp();
  const navigate = useNavigate();

  // Wording matters here: the dataset records a difference between two
  // synthetic epochs but makes no determination that any change was
  // unauthorised, so the suggestions do not claim one.
  const suggestions = [
    'Show underground clashes',
    'Show recorded mortgages and encumbrances',
    'Show changes between the two epochs',
    'Show records awaiting a decision',
  ];

  const handleSearch = async (textToSearch?: string) => {
    const q = (textToSearch || query).trim();
    if (!q) return;
    setIsLoading(true);
    setResult(null);
    setError(null);
    try {
      const data = await askTheMap(q);
      setResult(data);
      // Only claim a highlight when the scan actually matched something, so an
      // empty result never tells the user a highlight was applied.
      if (data.highlight_3d && (data.match_count ?? 0) > 0) {
        const fp = Array.isArray(data.highlight_3d.focus_point)
          ? data.highlight_3d.focus_point
          : null;
        applyHighlight({
          category: data.intent_category || 'query',
          ids: data.matched_entity_ids || [],
          mode: data.highlight_3d.mode || 'default',
          label: q,
          // Only the x/y matter here; the scene z (a basement depth or a floor
          // level) has no meaning on a 2D map, and feeding it to the transform
          // would corrupt the latitude.
          focusPoint: fp && fp.length >= 2 ? [Number(fp[0]), Number(fp[1])] : undefined,
          color: data.highlight_3d.highlight_color,
        });
        showToast('Highlight applied to the 3D view');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Query failed');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (!isOpen) {
      setQuery('');
      setResult(null);
      setError(null);
    }
  }, [isOpen]);

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={
        <span className="flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-accent-strong" />
          Ask the Map
        </span>
      }
      size="sm"
    >
      <div className="space-y-4">
        <p className="text-xs text-ink-soft -mt-1">
          Natural-language spatial queries run against the synthetic demo precinct. Highlights are applied to the
          3D building view.
        </p>
        <div className="relative">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            placeholder="e.g. Show underground clashes…"
            className="w-full bg-canvas border-2 border-ink rounded-none pl-10 pr-11 py-3 text-sm text-ink placeholder-slate-400 focus:outline-none focus:border-ink focus:bg-chalk shadow-brutal-sm transition font-bold"
            autoFocus
          />
          <Search className="w-4 h-4 text-ink-mut absolute left-3.5 top-3.5" />
          <button
            onClick={() => handleSearch()}
            disabled={isLoading || !query.trim()}
            className="absolute right-2 top-2 p-2 rounded-none bg-accent hover:bg-accent-strong text-ink disabled:opacity-50 transition shadow-brutal-sm"
            aria-label="Run query"
          >
            <CornerDownLeft className="w-4 h-4" />
          </button>
        </div>

        <div className="flex flex-wrap gap-2">
          {suggestions.map((s) => (
            <button
              key={s}
              onClick={() => {
                setQuery(s);
                handleSearch(s);
              }}
              className="text-[11px] bg-canvas hover:bg-canvas text-ink font-bold px-2.5 py-1.5 rounded-none transition text-left"
            >
              {s}
            </button>
          ))}
        </div>

        {isLoading && (
          <div className="flex items-center gap-2 text-xs text-ink-soft">
            <span className="w-3.5 h-3.5 border-2 border-ink border-t-transparent rounded-none animate-spin" />
            Parsing query…
          </div>
        )}

        {result && (
          <div className="p-4 rounded-none bg-accent/80 border-2 border-ink space-y-2 text-xs animate-rise-in">
            <div className="flex items-center justify-between gap-2">
              <Badge tone="blue">{result.intent_category}</Badge>
              <span className="font-mono text-[10px] text-ink-soft font-bold">
                {result.execution_time_ms} ms
              </span>
            </div>

            {/*
              The workings, shown before the prose. "Underground clash search ->
              0 rows in store" is a claim the reader can check; a sentence of
              generated English is not. Rendering the category, the filter that
              ran and the row count makes the answer auditable, and it makes the
              zero-result case legible rather than looking like a failure.
            */}
            <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-[11px]">
              <dt className="font-black uppercase tracking-wide text-ink-soft">Intent</dt>
              <dd className="font-mono text-ink">{result.intent_category || '—'}</dd>

              <dt className="font-black uppercase tracking-wide text-ink-soft">Filter</dt>
              <dd className="font-mono text-ink break-all">
                {result.matched_filter && Object.keys(result.matched_filter).length
                  ? Object.entries(result.matched_filter)
                      .map(([k, v]) => `${k}=${typeof v === 'object' ? JSON.stringify(v) : String(v)}`)
                      .join(' · ')
                  : '—'}
              </dd>

              <dt className="font-black uppercase tracking-wide text-ink-soft">Rows</dt>
              <dd className="font-mono text-ink">
                {result.match_count ?? 0} in store
                {(result.match_count ?? 0) === 0 ? ' — no match' : ''}
              </dd>
            </dl>

            <p className="text-sm font-bold text-ink leading-relaxed">{result.human_explanation}</p>

            {/*
              The answer is a read of invented demo data, so it says where it
              came from and what it cannot be used to conclude. Without this the
              result reads like a survey finding.
            */}
            <div className="pt-2 border-t border-accent/80 text-[11px] text-ink-soft space-y-1">
              {result.data_source && (
                <div>
                  Source: <span className="font-mono text-ink">{result.data_source}</span>
                </div>
              )}
              {result.match_count === 0 && (
                <div className="font-bold text-ink">No records matched, so nothing was highlighted.</div>
              )}
              {result.limitations?.map((limitation, i) => (
                <div key={i} className="flex gap-1">
                  <span aria-hidden="true">&bull;</span>
                  <span>{limitation}</span>
                </div>
              ))}
              {result.disclaimer && <div className="font-mono text-[10px]">{result.disclaimer}</div>}
            </div>

            <div className="pt-2 border-t border-accent/80 flex flex-wrap gap-2 items-center justify-between">
              <span className="text-[11px] text-ink-soft">
                Matched: <strong className="font-mono text-ink">{result.matched_entity_ids?.join(', ') || '—'}</strong>
              </span>
              <div className="flex items-center gap-1.5">
                {(result.match_count ?? 0) === 0 ? null : (<>
                {/*
                  These jump straight to a 2D view with the pointer already
                  placed. Landing on the default view instead would have left
                  the camera wherever it was, with nothing marking the match --
                  the highlight state was set but only the 3D view acted on it.
                */}
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => { onClose(); navigate('/app/map?view=open_twin'); }}
                  title="Show this highlight on the 3D open-twin map"
                >
                  View on 3D
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => { onClose(); navigate('/app/map?view=cadastre'); }}
                  title="Show this highlight on the 2D cadastral map"
                >
                  <MapIcon className="w-3.5 h-3.5" />
                  View on map
                </Button>
                </>)}
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className="p-3 rounded-none bg-crimson-50 border-2 border-ink text-xs font-bold text-crimson-700">
            {error}
          </div>
        )}
      </div>
    </Modal>
  );
};