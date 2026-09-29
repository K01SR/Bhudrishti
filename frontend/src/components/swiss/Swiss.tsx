/**
 * Swiss International Style primitives for the system console.
 *
 * The console deliberately does not reuse the landing page's theme components.
 * Two reasons:
 *
 * 1. `src/components/landing/` is under a byte-identical protection, so the
 *    Swiss variants there (brutalist / swiss / kinetic / neo / botanical) are
 *    a showcase surface, not the application's. A console that imports from it
 *    would inherit a theme switch that means nothing in an operator tool.
 * 2. Those components render invented figures — a "State-wide District
 *    Registry" with fabricated parcel counts, twin counts and concordance
 *    percentages, and a ULPIN check-digit calculator that returns a constant.
 *    None of that can move into the application.
 *
 * Style is the part worth keeping: a strict 12-column grid, hairline rules
 * instead of borders-and-shadows, one accent, uppercase mono annotation at a
 * fixed small size, and tabular figures so columns of numbers align. That is
 * the Swiss idiom; the data is where it had to be replaced rather than moved.
 *
 * Everything is expressed with the same tokens the rest of the app uses
 * (chalk/canvas/ink/accent) so the console does not read as a bolted-on
 * foreign surface when opened next to the map.
 */

export const SWISS = {
  /** The single accent. One per screen, used for state, never decoration. */
  accent: '#E11D2E',
  rule: 'rgba(15, 23, 42, 0.18)',
  hairline: '1px solid rgba(15, 23, 42, 0.12)',
} as const;

/** 12-column grid. Gutters collapse to a single column on small screens. */
export function SwissGrid({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return <div className={`grid grid-cols-1 md:grid-cols-12 gap-px ${className}`}>{children}</div>;
}

/**
 * Grid spans, written out in full.
 *
 * These are literal class strings rather than `md:col-span-${span}` on purpose:
 * Tailwind scans source text for complete class names, so an interpolated
 * class is not in the generated CSS and the span silently does nothing. A
 * static map keeps every span visible to the scanner.
 */
const SPAN: Record<number, string> = {
  3: 'md:col-span-3',
  4: 'md:col-span-4',
  5: 'md:col-span-5',
  6: 'md:col-span-6',
  7: 'md:col-span-7',
  8: 'md:col-span-8',
  9: 'md:col-span-9',
  12: 'md:col-span-12',
};

/** A grid cell spanning `span` of 12 columns. */
export function Cell({ span, children, className = '' }: { span: number; children: React.ReactNode; className?: string }) {
  const spanClass = SPAN[span] ?? SPAN[6];
  return <div className={`${spanClass} bg-chalk p-5 ${className}`}>{children}</div>;
}

/** Masthead: oversized tight-tracked title over a heavy rule. */
export function Masthead({
  eyebrow,
  title,
  lede,
  right,
}: {
  eyebrow: string;
  title: string;
  lede: string;
  right?: React.ReactNode;
}) {
  return (
    <header className="border-b-2 border-ink pb-4">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="annotation text-ink-mut uppercase tracking-[0.2em]">{eyebrow}</div>
          <h1 className="mt-1 font-display text-4xl md:text-5xl font-black tracking-[-0.03em] leading-[0.95] text-ink uppercase">
            {title}
          </h1>
        </div>
        {right}
      </div>
      <p className="mt-3 max-w-3xl text-sm text-ink-soft leading-relaxed">{lede}</p>
    </header>
  );
}

/** Section label. Small, uppercase, mono, sitting on a rule. */
export function SectionLabel({ children, note }: { children: React.ReactNode; note?: string }) {
  return (
    <div className="flex items-baseline justify-between border-b border-ink/20 pb-1.5 mb-4">
      <h2 className="annotation uppercase tracking-[0.18em] text-ink">{children}</h2>
      {note ? <span className="text-[10px] font-mono text-ink-mut">{note}</span> : null}
    </div>
  );
}

/**
 * A figure with its label. `value` is already a string so the caller has to
 * decide what an absent value looks like — the console passes '--' with a
 * reason rather than letting a null render as "0" or an empty cell.
 */
export function Stat({
  label,
  value,
  sub,
  emphasis = false,
}: {
  label: string;
  value: string;
  sub?: string;
  emphasis?: boolean;
}) {
  return (
    <div className="border-l-2 pl-3" style={{ borderLeftColor: emphasis ? SWISS.accent : 'rgba(15,23,42,0.25)' }}>
      <div className="annotation text-ink-mut uppercase tracking-[0.14em]">{label}</div>
      <div
        className="mt-1 font-mono text-2xl font-bold tabular-nums text-ink"
        style={emphasis ? { color: SWISS.accent } : undefined}
      >
        {value}
      </div>
      {sub ? <div className="mt-0.5 text-[11px] text-ink-mut leading-snug">{sub}</div> : null}
    </div>
  );
}

/** Key/value row, for endpoint and dataset inventories. */
export function Row({ k, v, mono = true }: { k: string; v: React.ReactNode; mono?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-1.5 border-b border-ink/10 last:border-0">
      <span className="text-xs text-ink-soft">{k}</span>
      <span className={`text-xs text-right ${mono ? 'font-mono tabular-nums' : ''} text-ink`}>{v}</span>
    </div>
  );
}

/**
 * Marks a figure the backend reports but does not actually compute.
 *
 * `/osm/summary` returns civic counts (parks, ward offices, clinics) and a
 * `geospatial_accuracy` block asserting survey-grade closure error and a Survey
 * of India datum. Those are literals in the handler, not measurements. Showing
 * them as figures would be presenting an invention as an observation, so they
 * are excluded here and the exclusion is stated on screen instead of being
 * silently dropped.
 */
export function UnverifiedNote({ children }: { children: React.ReactNode }) {
  return (
    <div
      data-testid="swiss-unverified-note"
      className="mt-3 border-l-2 pl-3 py-1 text-[11px] leading-relaxed"
      style={{ borderLeftColor: SWISS.accent }}
    >
      <span className="font-mono font-bold uppercase tracking-[0.14em]" style={{ color: SWISS.accent }}>
        Not measured&nbsp;·&nbsp;
      </span>
      <span className="text-ink-soft">{children}</span>
    </div>
  );
}

/** Determinate bar. Width is a number the caller has already validated. */
export function Bar({ pct, label, note }: { pct: number; label: string; note?: string }) {
  const w = Math.max(0, Math.min(100, Number.isFinite(pct) ? pct : 0));
  return (
    <div className="py-2">
      <div className="flex items-baseline justify-between">
        <span className="text-xs text-ink">{label}</span>
        <span className="font-mono text-xs tabular-nums text-ink-soft">{note}</span>
      </div>
      <div className="mt-1.5 h-[3px] w-full bg-ink/10">
        <div className="h-full" style={{ width: `${w}%`, background: SWISS.accent }} />
      </div>
    </div>
  );
}
