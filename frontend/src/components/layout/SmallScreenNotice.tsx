import React, { useEffect, useState } from 'react';
import { MonitorSmartphone, X } from 'lucide-react';

/**
 * Small-screen advisory.
 *
 * The 3D Command Center is the load-bearing surface here: vector-tile basemaps,
 * extruded footprints and a WebGL scene all compete for the same GPU that a
 * phone is already using for the browser compositor. On a handset the map
 * either arrives at 2-5 fps or falls back to a blank canvas, and the symptom
 * looks like a broken app rather than an underpowered one.
 *
 * Two deliberate choices:
 *
 * - Gated on a coarse pointer as well as width. A narrow window on a desktop
 *   browser is a legitimate layout, and nagging someone who resized their
 *   window is worse than not saying anything. Touch + narrow is the actual
 *   phone/tablet case.
 * - Dismissal persists. This is advice, not a modal; re-showing it on every
 *   route change would train people to ignore the whole top bar.
 */

const DISMISS_KEY = 'bhudrishti:small-screen-notice-dismissed';

// Tailwind's `lg` is 1024px, which is also where AppShell collapses its nav
// into a drawer. Matching that means the advisory appears exactly when the
// layout stops being the one this UI was drawn for.
const NARROW_QUERY = '(max-width: 1023px)';
const COARSE_QUERY = '(pointer: coarse)';

const isSmallTouchDevice = (): boolean => {
  if (typeof window === 'undefined' || !window.matchMedia) return false;
  return window.matchMedia(NARROW_QUERY).matches && window.matchMedia(COARSE_QUERY).matches;
};

export const SmallScreenNotice: React.FC = () => {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    let dismissed = false;
    try {
      dismissed = window.localStorage.getItem(DISMISS_KEY) === '1';
    } catch {
      // Private mode / blocked storage. Showing the notice is the safe default.
    }
    if (!dismissed && isSmallTouchDevice()) setVisible(true);
  }, []);

  const dismiss = () => {
    setVisible(false);
    try {
      window.localStorage.setItem(DISMISS_KEY, '1');
    } catch {
      // Nothing to do; it will reappear next reload.
    }
  };

  if (!visible) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      className="bg-accent text-ink border-b-2 border-ink shadow-brutal-sm px-4 py-2.5"
    >
      <div className="max-w-[1600px] mx-auto flex items-start gap-2.5">
        <MonitorSmartphone className="w-4 h-4 shrink-0 mt-0.5 text-accent-strong" />
        <p className="text-xs font-bold leading-relaxed flex-1">
          <span className="font-black uppercase tracking-wide">Best on a laptop or desktop.</span>{' '}
          The 3D Command Center needs more GPU memory than a phone browser gives it, so the map
          can render blank or crawl. Everything else still works, but rotate to landscape if the
          3D view is your priority.
        </p>
        <button
          onClick={dismiss}
          className="shrink-0 p-1 rounded-none border-2 border-transparent hover:border-ink transition"
          aria-label="Dismiss this notice"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
};
