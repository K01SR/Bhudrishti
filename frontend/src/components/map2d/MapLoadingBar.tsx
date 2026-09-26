import React, { useEffect, useRef, useState } from 'react';
import maplibregl from 'maplibre-gl';
import { Loader2 } from 'lucide-react';
import { cn } from '../../lib/cn';
import './MapLoadingBar.css';

/**
 * A top-of-map progress bar for work the user cannot see progress on.
 *
 * The problem this solves: on both heavy views the first paint looks identical
 * whether the map is ready or still waiting on a tile server and an Overpass
 * round trip. With no signal, people pan and zoom while data is in flight, which
 * cancels the in-progress request and restarts it, which looks like the app
 * hanging. The bar plus the explicit "wait" copy ends that loop.
 *
 * Three states rather than a spinner, because they call for different behaviour:
 *  - `busy` immediately: something is in flight, show the bar and the wait text.
 *  - after SLOW_MS with still busy: the copy changes, because something is
 *    genuinely slow and the user deserves to know it is not their fault.
 *  - `idle`: hide after a short tail so the bar does not flicker on every pan.
 *
 * "Idle" is MapLibre's own definition -- no tiles in flight and nothing to load.
 * It is the right signal, but it is also true for a beat after a pan settles, so
 * the FADE_MS tail keeps the bar from strobing during a gesture.
 */
const SLOW_MS = 4000;
const FADE_MS = 350;

interface Props {
  map: maplibregl.Map | null;
  className?: string;
  /** Extra work in flight beyond tiles, e.g. an Overpass fetch. */
  extraLoading?: boolean;
  label?: string;
}

export const MapLoadingBar: React.FC<Props> = ({
  map,
  className,
  extraLoading = false,
  label = 'Loading map data',
}) => {
  const [slow, setSlow] = useState(false);
  const [visible, setVisible] = useState(false);
  const extraRef = useRef(extraLoading);
  extraRef.current = extraLoading;
  // Held in a ref so the `extraLoading` effect below can re-evaluate on demand.
  // `triggerRepaint` alone does not run `evaluate`; MapLibre only re-evaluates
  // on its own events, so without this the bar waited out the 2s poll to notice
  // that an external fetch had started.
  const evaluateRef = useRef<() => void>(() => {});

  useEffect(() => {
    if (!map) return;
    let slowTimer: ReturnType<typeof setTimeout> | null = null;
    let fadeTimer: ReturnType<typeof setTimeout> | null = null;

    const evaluate = () => {
      // A source MapLibre is still loading is counted as busy, as is an explicit
      // external fetch in flight.
      let pending = extraRef.current;
      if (!pending) {
        try {
          pending = !map.areTilesLoaded() || !map.isStyleLoaded();
        } catch {
          // The map can be mid-teardown. Treat that as not-busy rather than
          // throwing inside an event handler.
          pending = false;
        }
      }
      if (pending) {
        setVisible(true);
        if (slowTimer) clearTimeout(slowTimer);
        slowTimer = setTimeout(() => setSlow(true), SLOW_MS);
        if (fadeTimer) {
          clearTimeout(fadeTimer);
          fadeTimer = null;
        }
      } else {
        if (slowTimer) {
          clearTimeout(slowTimer);
          slowTimer = null;
        }
        setSlow(false);
        // Tail the bar out rather than cutting it, so a short reload does not
        // strobe.
        if (fadeTimer) clearTimeout(fadeTimer);
        fadeTimer = setTimeout(() => setVisible(false), FADE_MS);
      }
    };

    const events: Array<keyof maplibregl.MapEventType> = ['sourcedata', 'dataloading', 'idle', 'load'];
    evaluateRef.current = evaluate;
    events.forEach((e) => map.on(e, evaluate));
    // MapLibre fires no event when nothing at all is happening, so a slow
    // external fetch with no tile activity needs its own poll. Two seconds is
    // frequent enough to feel live and rare enough to cost nothing.
    const poll = setInterval(evaluate, 2000);
    evaluate();

    return () => {
      events.forEach((e) => map.off(e, evaluate));
      clearInterval(poll);
      if (slowTimer) clearTimeout(slowTimer);
      if (fadeTimer) clearTimeout(fadeTimer);
      // A newer map instance may already own this ref; do not clobber it.
      if (evaluateRef.current === evaluate) evaluateRef.current = () => {};
    };
  }, [map]);

  // Re-evaluate promptly when an external fetch starts or stops, so the bar
  // does not wait out the 2s poll to notice.
  useEffect(() => {
    if (!map) return;
    evaluateRef.current();
  }, [extraLoading, map]);

  return (
    <div
      className={cn(
        'absolute inset-x-0 top-0 z-30 pointer-events-none transition-opacity duration-300',
        visible ? 'opacity-100' : 'opacity-0',
        className,
      )}
      aria-hidden={!visible}
      role="status"
      data-testid="map-loading-bar"
      data-visible={visible ? 'true' : 'false'}
      data-slow={slow ? 'true' : 'false'}
    >
      <div className="relative h-1 w-full bg-ink/20 overflow-hidden">
        <div
          className={cn(
            'h-full bg-accent-strong',
            slow ? 'animate-pulse' : 'animate-progress-indeterminate',
          )}
          style={{ width: slow ? '100%' : '35%' }}
        />
      </div>
      <div className="flex items-center gap-1.5 px-2.5 py-1 bg-ink/90 text-canvas w-fit max-w-full">
        <Loader2 className="w-3 h-3 animate-spin flex-shrink-0" />
        <span className="text-[10px] font-mono uppercase tracking-wide truncate">
          {slow ? 'Still loading — please wait, do not pan' : `${label}…`}
        </span>
      </div>
    </div>
  );
};

export default MapLoadingBar;
