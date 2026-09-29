/**
 * Theme-aware text tints for the landing surface.
 *
 * The 600 steps of Tailwind's palette sit around 3.2-4.0:1 on white, which is
 * below WCAG AA for the small caption sizes used here, while the same steps are
 * far too dark on the near-black dark surface. So each tint needs a different
 * step per mode: dark enough to read on paper, bright enough to read on ink.
 *
 * Every variant is spelled out as a complete literal because Tailwind only
 * emits classes it can see verbatim - a template like `text-${name}-700` would
 * be silently dropped from the build.
 */

const ON_LIGHT = {
  amber: 'text-amber-800',
  emerald: 'text-emerald-800',
  cyan: 'text-cyan-800',
  blue: 'text-blue-800',
  green: 'text-green-800',
  violet: 'text-violet-800',
  purple: 'text-purple-800',
  red: 'text-red-800',
  rose: 'text-rose-800',
} as const;

const ON_DARK = {
  amber: 'text-amber-300',
  emerald: 'text-emerald-300',
  cyan: 'text-cyan-300',
  blue: 'text-blue-300',
  green: 'text-green-300',
  violet: 'text-violet-300',
  purple: 'text-purple-300',
  red: 'text-red-300',
  rose: 'text-rose-300',
} as const;

export type TintName = keyof typeof ON_LIGHT;

/** Picks the readable step of `name` for the active landing theme. */
export const tint = (isLight: boolean, name: TintName): string =>
  isLight ? ON_LIGHT[name] : ON_DARK[name];
