import React, { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { cn } from '../../lib/cn';
import { AlertTriangle, ShieldAlert, Database, CircleDot, Info, X, Wrench } from 'lucide-react';
import { useDeployment } from '../../services/deployment';

/* ------------------------------------------------------------------ */
/* Button                                                              */
/* ------------------------------------------------------------------ */

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'success' | 'dark';
type ButtonSize = 'sm' | 'md' | 'lg';

/* Brutalist light, matching the landing: solid black fill, 2px black border-2,
   hard offset shadow, no radius, uppercase. The signature interaction is the
   press — the block moves down-right by the shadow's own offset and the shadow
   drops to nothing, so border-2 and shadow read as one physical object rather
   than decoration. Hover swaps the fill to electric green with black text,
   which is the landing's own hover treatment. */
const buttonVariants: Record<ButtonVariant, string> = {
  primary: 'bg-ink hover:bg-accent text-white hover:text-ink border-2 border-ink shadow-brutal hover:shadow-none hover:translate-x-[3px] hover:translate-y-[3px]',
  secondary: 'bg-chalk hover:bg-canvas text-ink border-2 border-ink shadow-brutal hover:shadow-none hover:translate-x-[3px] hover:translate-y-[3px]',
  ghost: 'bg-transparent hover:bg-accent text-ink hover:text-ink border-2 border-ink hover:border-ink',
  danger: 'bg-crimson-600 hover:bg-crimson-700 text-white border-2 border-ink shadow-brutal hover:shadow-none hover:translate-x-[3px] hover:translate-y-[3px]',
  success: 'bg-emerald-600 hover:bg-emerald-700 text-ink border-2 border-ink shadow-brutal hover:shadow-none hover:translate-x-[3px] hover:translate-y-[3px]',
  dark: 'bg-ink hover:bg-ink-soft text-white border-2 border-ink shadow-brutal hover:shadow-none hover:translate-x-[3px] hover:translate-y-[3px]',
};

const buttonSizes: Record<ButtonSize, string> = {
  sm: 'px-2.5 py-1.5 text-[10px] gap-1.5',
  md: 'px-4 py-2 text-xs gap-2',
  lg: 'px-6 py-3 text-sm gap-2',
};

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  to?: string;
}

export const Button: React.FC<ButtonProps> = ({
  variant = 'primary',
  size = 'md',
  className,
  to,
  children,
  ...rest
}) => {
  const base = cn(
    'inline-flex items-center justify-center font-black uppercase tracking-wide transition-all outline-none',
    'focus-visible:ring-2 focus-visible:ring-ink focus-visible:ring-offset-2 focus-visible:ring-offset-canvas',
    'disabled:opacity-50 disabled:pointer-events-none',
    buttonVariants[variant],
    buttonSizes[size],
    className
  );

  if (to) {
    return (
      <Link to={to} className={base}>
        {children}
      </Link>
    );
  }
  return (
    <button className={base} {...rest}>
      {children}
    </button>
  );
};

/* ------------------------------------------------------------------ */
/* Badges                                                              */
/* ------------------------------------------------------------------ */

type BadgeTone = 'blue' | 'green' | 'amber' | 'red' | 'slate' | 'purple' | 'sky';

/* The key names are load-bearing: `blue` marks a role/owner, `sky` marks a
   model or asset, and `purple` marks a ledger or standard reference. They
   used to differ only by hue; with the cool hues gone from the app they are
   separated by weight instead, so the distinction survives. */
/* Semantic status tones (green/amber/red) keep their hue — pass, warning and
 * violation must stay separable at a glance — but every tone is now a hard
 * 2px black border-2 with no radius and black text, as the landing does. */
const badgeTones: Record<BadgeTone, string> = {
  blue: 'bg-accent text-ink border-ink',
  green: 'bg-emerald-500 text-black border-ink',
  amber: 'bg-amber-400 text-black border-ink',
  red: 'bg-crimson-600 text-white border-ink',
  slate: 'bg-chalk text-ink border-ink',
  purple: 'bg-ink text-white border-ink',
  sky: 'bg-canvas text-ink border-ink',
};

interface BadgeProps {
  tone?: BadgeTone;
  className?: string;
  children: React.ReactNode;
  dot?: boolean;
}

export const Badge: React.FC<BadgeProps> = ({ tone = 'slate', className, children, dot = false }) => (
  <span
    className={cn(
      'inline-flex items-center gap-1 px-2 py-0.5 rounded-none text-[10px] font-black uppercase tracking-widest border-2',
      badgeTones[tone],
      className
    )}
  >
    {dot && <span className="w-1.5 h-1.5 rounded-none bg-ink" />}
    {children}
  </span>
);

/** Maps domain status strings to a badge tone. Unknown statuses fall back to slate.
 *  `status` is optional because these values come off the API, where a field can
 *  be absent; a missing value renders as UNSPECIFIED rather than crashing the
 *  page or inventing a state. */
export const StatusBadge: React.FC<{ status?: string | null; className?: string }> = ({ status, className }) => {
  const s = (status ?? '').toUpperCase();
  let tone: BadgeTone = 'slate';
  if (/APPROVED|VERIF|OFFICIAL|PASSED|ACTIVE|VERIFIED|SUCCESS/.test(s)) tone = 'green';
  else if (/REJECT|FAILED|CLASH|CRITICAL|ERROR|REDACTED/.test(s)) tone = 'red';
  else if (/REVIEW|PENDING|WARNING|CHANGE|SUBMIT|PROCESS|NEEDS/.test(s)) tone = 'amber';
  else if (/APPRAISAL|INFO|%.*/.test(s)) tone = 'blue';
  return <Badge tone={tone} className={className}>{status || 'UNSPECIFIED'}</Badge>;
};

/** Honest data-ownership marker: REAL / DEMO / SYSTEM / AI / OFFICIAL. */
export const ProvenanceTag: React.FC<{ kind?: string; className?: string }> = ({ kind, className }) => {
  const k = (kind || '').toUpperCase();
  let tone: BadgeTone = 'slate';
  let label = k || 'DEMO';
  if (/OFFICIAL|VERIFIED|AUTHORIT/.test(k)) tone = 'green';
  else if (/AI|MODEL|SYNTHES|SIMUL/.test(k)) tone = 'purple';
  else if (/SYSTEM|ENGINE|AUTO/.test(k)) tone = 'sky';
  else if (/REAL|FIELD|GNSS|LIDAR|GES|SURVEY/.test(k)) tone = 'blue';
  else if (/DEMO|SAMPLE/.test(k) || k === '') tone = 'amber';
  return <Badge tone={tone} className={className} dot>{(label || 'DEMO')}</Badge>;
};

/* ------------------------------------------------------------------ */
/* Card / Panel                                                        */
/* ------------------------------------------------------------------ */

export const Card: React.FC<{ className?: string; children: React.ReactNode }> = ({ className, children }) => (
  <div className={cn('bg-chalk border-2 border-ink rounded-none shadow-brutal', className)}>{children}</div>
);

export const Panel: React.FC<{
  title?: React.ReactNode;
  icon?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
  bodyClassName?: string;
  children: React.ReactNode;
}> = ({ title, icon, action, className, bodyClassName, children }) => (
  <Card className={cn(className)}>
    {(title || action) && (
      <div className="flex items-center justify-between gap-3 px-4 py-3 border-b-2 border-ink bg-canvas">
        <div className="flex items-center gap-2 text-xs font-black text-ink uppercase tracking-widest font-mono">
          {icon}
          {title}
        </div>
        {action}
      </div>
    )}
    <div className={cn('p-4', bodyClassName)}>{children}</div>
  </Card>
);

/* ------------------------------------------------------------------ */
/* Tabs                                                               */
/* ------------------------------------------------------------------ */

export interface TabItem {
  id: string;
  label: React.ReactNode;
  icon?: React.ReactNode;
  count?: number;
}

export const Tabs: React.FC<{
  tabs: TabItem[];
  active: string;
  onChange: (id: string) => void;
  className?: string;
  color?: string;
}> = ({ tabs, active, onChange, className, color = 'blue' }) => {
  /* The active tab is a solid block with a hard shadow, so selection survives
     without relying on a coloured underline. `color` still picks the fill. */
  const activeFill =
    color === 'red'
      ? 'bg-crimson-600 text-white'
      : color === 'green'
        ? 'bg-emerald-500 text-black'
        : color === 'amber'
          ? 'bg-amber-400 text-black'
          : 'bg-ink text-white';

  return (
    <div className={cn('flex border-b-2 border-ink bg-canvas text-xs overflow-x-auto', className)} role="tablist">
      {tabs.map((t) => {
        const isActive = t.id === active;
        return (
          <button
            key={t.id}
            role="tab"
            aria-selected={isActive}
            onClick={() => onChange(t.id)}
            className={cn(
              'flex items-center gap-1.5 px-3 py-2.5 text-center font-black uppercase tracking-wide border-r-2 border-ink transition whitespace-nowrap outline-none focus-visible:ring-2 focus-visible:ring-ink focus-visible:ring-offset-1',
              isActive
                ? cn(activeFill, 'shadow-brutal-sm translate-x-[2px] translate-y-[2px] mb-[-2px]')
                : 'bg-transparent text-ink hover:bg-accent hover:text-ink'
            )}
          >
            {t.icon}
            {t.label}
            {t.count !== undefined && (
              <span className="font-mono text-[10px] px-1.5 py-0.5 border-2 border-current">
                {t.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
};

/* ------------------------------------------------------------------ */
/* Modal                                                               */
/* ------------------------------------------------------------------ */

export const Modal: React.FC<{
  isOpen: boolean;
  onClose: () => void;
  title?: React.ReactNode;
  icon?: React.ReactNode;
  size?: 'sm' | 'md' | 'lg' | 'xl';
  footer?: React.ReactNode;
  children: React.ReactNode;
}> = ({ isOpen, onClose, title, icon, size = 'md', footer, children }) => {
  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = '';
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const sizes = { sm: 'max-w-md', md: 'max-w-2xl', lg: 'max-w-4xl', xl: 'max-w-6xl' };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink/60"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
      role="dialog"
      aria-modal="true"
    >
      <div className={cn('w-full bg-chalk rounded-none shadow-brutal-lg border-2 border-ink max-h-[90vh] flex flex-col animate-in fade-in-zoom-95 duration-200', sizes[size])}>
        {title && (
          <div className="flex items-center justify-between gap-3 px-5 py-4 border-b-2 border-ink bg-canvas">
            <div className="flex items-center gap-2.5 text-xs font-black text-ink uppercase tracking-widest font-mono">
              {icon}
              {title}
            </div>
            <button
              onClick={onClose}
              className="p-1.5 rounded-none border-2 border-ink bg-chalk text-ink hover:bg-accent transition outline-none focus-visible:ring-2 focus-visible:ring-ink"
              aria-label="Close dialog"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        )}
        <div className="flex-1 overflow-y-auto px-5 py-4">{children}</div>
        {footer && <div className="px-5 py-3.5 border-t-2 border-ink bg-canvas flex justify-end gap-2">{footer}</div>}
      </div>
    </div>
  );
};

/* ------------------------------------------------------------------ */
/* Form Field                                                          */
/* ------------------------------------------------------------------ */

interface FieldProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'prefix'> {
  label?: string;
  hint?: string;
  error?: string;
  prefix?: React.ReactNode;
}

export const Field: React.FC<FieldProps> = ({ label, hint, error, prefix, className, ...rest }) => (
  <label className="block">
    {label && (
      <span className="block text-[10px] font-black uppercase tracking-widest text-ink mb-1.5">{label}</span>
    )}
    <div className="relative">
      {prefix && (
        <span className="absolute left-3 top-1/2 -translate-y-1/2 flex items-center text-ink-soft pointer-events-none">
          {prefix}
        </span>
      )}
      <input
        className={cn(
          'w-full px-3 py-2.5 text-sm bg-chalk border-2 border-ink rounded-none text-ink',
          'placeholder:text-ink-mut outline-none transition',
          'focus:bg-accent-faint',
          prefix && 'pl-9',
          error && 'border-ink bg-crimson-50',
          className
        )}
        {...rest}
      />
    </div>
    {error && <span className="block text-[11px] font-bold text-crimson-600 mt-1">{error}</span>}
    {!error && hint && <span className="block text-[11px] text-ink-soft mt-1">{hint}</span>}
  </label>
);

/* ------------------------------------------------------------------ */
/* Empty / Error / Skeleton states                                     */
/* ------------------------------------------------------------------ */

export const EmptyState: React.FC<{
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}> = ({ icon, title, description, action, className }) => (
  <div className={cn('flex flex-col items-center justify-center text-center px-6 py-12', className)}>
    {icon && (
      <div className="w-12 h-12 rounded-none bg-canvas border-2 border-ink flex items-center justify-center text-ink mb-3">
        {icon}
      </div>
    )}
    <h4 className="text-sm font-bold text-ink font-display">{title}</h4>
    {description && <p className="text-xs text-ink-soft mt-1.5 max-w-sm leading-relaxed">{description}</p>}
    {action && <div className="mt-4">{action}</div>}
  </div>
);

export const ErrorState: React.FC<{
  title?: string;
  message?: string;
  onRetry?: () => void;
  errorType?: string;
}> = ({ title = 'Something went wrong', message, onRetry, errorType }) => (
  <div className="flex flex-col items-center justify-center text-center px-6 py-12">
    <div className="w-12 h-12 rounded-none bg-crimson-600 border-2 border-ink flex items-center justify-center text-white mb-3">
      <AlertTriangle className="w-6 h-6" />
    </div>
    <h4 className="text-sm font-bold text-ink font-display">{title}</h4>
    <p className="text-xs text-ink-soft mt-1.5 max-w-sm leading-relaxed">{message || 'The application could not complete the request. Please try again.'}</p>
    {errorType === 'map' && (
      <p className="text-[11px] font-mono text-ink-mut mt-1.5">Map service unavailable • Spatial context rendering may be offline.</p>
    )}
    {onRetry && (
      <Button variant="secondary" size="sm" className="mt-4" onClick={onRetry}>
        Try again
      </Button>
    )}
  </div>
);

export const Skeleton: React.FC<{ className?: string }> = ({ className }) => (
  <div className={cn('animate-pulse rounded-none bg-canvas', className)} />
);

export const SkeletonList: React.FC<{ rows?: number }> = ({ rows = 5 }) => (
  <div className="space-y-3 p-4">
    {Array.from({ length: rows }).map((_, i) => (
      <div key={i} className="flex items-center gap-3">
        <Skeleton className="w-8 h-8 rounded-none" />
        <div className="flex-1 space-y-1.5">
          <Skeleton className="h-3 w-2/3" />
          <Skeleton className="h-2.5 w-1/3" />
        </div>
      </div>
    ))}
  </div>
);

/* ------------------------------------------------------------------ */
/* Section heading / misc                                              */
/* ------------------------------------------------------------------ */

export const SectionHeading: React.FC<{
  eyebrow?: string;
  title: React.ReactNode;
  description?: React.ReactNode;
  align?: 'left' | 'center';
  className?: string;
}> = ({ eyebrow, title, description, align = 'left', className }) => (
  <div className={cn(align === 'center' && 'text-center mx-auto', 'max-w-2xl', className)}>
    {eyebrow && (
      <div className={cn('font-mono text-[10px] font-black uppercase tracking-widest text-accent-strong mb-3', align === 'center' && 'flex justify-center')}>
        {eyebrow}
      </div>
    )}
    <h2 className="text-2xl sm:text-3xl font-black text-ink font-display tracking-tighter uppercase leading-[1.05]">{title}</h2>
    {description && <p className={cn('mt-3 text-sm sm:text-base text-ink-soft leading-relaxed', align === 'center' && 'mx-auto')}>{description}</p>}
  </div>
);

export const MonoChip: React.FC<{ children: React.ReactNode; className?: string }> = ({ children, className }) => (
  <span className={cn('font-mono text-[10px] font-black uppercase text-ink bg-canvas border-2 border-ink px-2 py-1 rounded-none', className)}>
    {children}
  </span>
);

export const Tooltip: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <span className="relative group inline-flex">
    {children}
    <span className="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-2 whitespace-nowrap rounded-none bg-ink text-chalk text-[10px] font-black uppercase tracking-wide px-2.5 py-1.5 opacity-0 group-hover:opacity-100 transition z-30 border-2 border-ink">
      {label}
    </span>
  </span>
);

/**
 * Demonstration-data marker, rendered only when the deployment is actually
 * serving generated data.
 *
 * This used to be an unconditional badge. Ten call sites rendered it from a
 * hardcoded string with no connection to the ENABLE_DEMO_MODE gate behind the
 * API, so it appeared on deployments serving no synthetic data at all, where
 * a marker that is always present tells the reader nothing. It now waits for
 * the real flag and renders nothing when the gate is shut or unknown.
 */
export const DemoHint: React.FC<{ text?: string; className?: string }> = ({ text = 'Demo dataset', className }) => {
  const { demo_mode: isDemo } = useDeployment();
  if (!isDemo) return null;
  return (
    <span className={cn('inline-flex items-center gap-1 text-[10px] font-black uppercase tracking-wide text-black bg-amber-400 border-2 border-ink rounded-none px-2 py-0.5', className)}>
      <Database className="w-3 h-3" />
      {text}
    </span>
  );
};

export const LevelBadge: React.FC<{ level?: string | null; className?: string }> = ({ level, className }) => {
  const lvl = (level ?? '').toUpperCase();
  if (!lvl) return <Badge tone="slate" className={className}>UNSPECIFIED</Badge>;
  const tone: BadgeTone = lvl.startsWith('B') ? 'red' : lvl === 'G' ? 'green' : lvl.startsWith('R') ? 'sky' : 'blue';
  const label = lvl === 'G' ? 'Ground' : lvl.startsWith('B') ? `Basement ${lvl.slice(1) || ''}`.trim() : lvl.startsWith('R') ? 'Rooftop' : `Floor ${lvl.replace('L0', '').replace('L', '')}`;
  return <Badge tone={tone} className={className}>{label}</Badge>;
};

export const SeverityBadge: React.FC<{ severity?: string | null }> = ({ severity }) => {
  const s = (severity ?? '').toUpperCase();
  const tone: BadgeTone = s === 'CRITICAL' || s === 'HIGH' ? 'red' : s === 'MEDIUM' ? 'amber' : 'slate';
  return <Badge tone={tone}>{severity || 'UNSPECIFIED'}</Badge>;
};

/* ------------------------------------------------------------------ */
/* StatCard                                                           */
/* ------------------------------------------------------------------ */

export interface StatCardProps {
  label: string;
  value: React.ReactNode;
  subtitle?: string;
  trend?: { value: string; positive?: boolean };
  icon?: React.ReactNode;
  className?: string;
  onClick?: () => void;
}

export const StatCard: React.FC<StatCardProps> = ({
  label,
  value,
  subtitle,
  trend,
  icon,
  className,
  onClick,
}) => (
  <div
    className={cn(
      'p-4 bg-chalk rounded-none border-2 border-ink shadow-brutal transition-all duration-100',
      onClick && 'cursor-pointer hover:bg-accent hover:shadow-none hover:translate-x-[3px] hover:translate-y-[3px]',
      className
    )}
    onClick={onClick}
  >
    <div className="flex items-start justify-between">
      <span className="text-[10px] uppercase tracking-widest font-black text-ink font-mono">{label}</span>
      {icon && <span className="text-ink text-base">{icon}</span>}
    </div>
    <div className="mt-2 flex items-baseline gap-2">
      <span className="text-2xl font-black text-ink font-display tracking-tighter font-mono">{value}</span>
      {trend && (
        <span
          className={cn(
            'text-[10px] font-black uppercase px-1.5 py-0.5 border-2 border-ink',
            trend.positive ? 'bg-emerald-500 text-black' : 'bg-crimson-600 text-white'
          )}
        >
          {trend.positive ? '↑' : '↓'} {trend.value}
        </span>
      )}
    </div>
    {subtitle && <p className="mt-1 text-xs text-ink-soft">{subtitle}</p>}
  </div>
);

export { ShieldAlert, CircleDot, Info, Wrench };