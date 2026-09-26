/// <reference types="vite/client" />
/**
 * CARTO basemap key handling, and the basemap variants the two map views
 * share.
 *
 * CARTO basemaps are no longer keyless. Until recently the raster endpoints
 * served OpenStreetMap-derived tiles to anyone; they now require a key, and
 * without one they return a flat grey placeholder rather than failing. That
 * failure mode is worth stating plainly because it is silent: the requests
 * still return HTTP 200, the map still renders, and every tile is the same
 * picture. Verified against this project's own tile coordinates -- the keyless
 * response is byte-identical across z13 and z14 and across adjacent x values,
 * while keyed responses differ per coordinate and carry real map detail.
 *
 * So this is not a cosmetic watermark to be tidied away. Before the key was
 * added, both the open-twin and 2D cadastral basemaps were drawing one flat
 * grey tile stretched over the viewport.
 *
 * The key is read from VITE_CARTO_API_KEY, which Vite inlines into the client
 * bundle at build time. That is inherent to raster basemap keys and is why
 * CARTO treats them as publishable rather than secret: anyone can read it from
 * devtools regardless. The meaningful control is a domain restriction on the
 * key in CARTO's dashboard, not secrecy. The value is therefore kept in
 * frontend/.env, which is gitignored, and never in a tracked file.
 */

/** Empty when no key is configured, so tiles fall back to the placeholder. */
export const CARTO_KEY_PARAM: string = (() => {
  const raw = import.meta.env?.VITE_CARTO_API_KEY;
  const key = typeof raw === 'string' ? raw.trim() : '';
  return key ? `?key=${encodeURIComponent(key)}` : '';
})();

export const CARTO_KEY_CONFIGURED = CARTO_KEY_PARAM !== '';

/**
 * Appends the key to a CARTO raster tile template.
 *
 * Takes the whole template rather than a style name because the two callers
 * use different suffixes -- one uses `@2x`, the other MapLibre's `{r}`
 * placeholder -- and rebuilding the URL shape here would be a larger change
 * than the fix warrants.
 */
export function cartoTile(template: string): string {
  return `${template}${CARTO_KEY_PARAM}`;
}

/* ------------------------------------------------------------------ *
 * Basemap variants: light/dark, labels on/off
 * ------------------------------------------------------------------ */

export type BasemapTheme = 'dark' | 'light';

/**
 * CARTO publishes each basemap theme in three label states, and they are
 * separate raster styles rather than a layer you can switch off:
 *
 *   `<theme>_all           land, water, roads and place labels
 *   `<theme>_nolabels      the same cartography with the labels stripped out
 *   `<theme>_only_labels   transparent ground with the labels drawn on top
 *
 * Verified present on the rastertiles endpoint for both themes. `nolabels` is
 * what a user asking for "labels off" actually wants: dropping to
 * `only_labels` and stacking it over `all` looks identical on screen but
 * doubles the tile requests, which matters on the 5M/month CARTO allowance.
 */
export type BasemapStyle = `${BasemapTheme}_${'all' | 'nolabels' | 'only_labels'}`;

export const BASEMAP_STYLES: readonly BasemapStyle[] = [
  'dark_all',
  'dark_nolabels',
  'light_all',
  'light_nolabels',
];

export function isBasemapStyle(value: unknown): value is BasemapStyle {
  return typeof value === 'string' && (BASEMAP_STYLES as readonly string[]).includes(value);
}

/**
 * Builds a keyed CARTO raster tile URL for a style.
 *
 * `retina` selects the `@2x` variant. The two views disagree on this: the
 * open-twin studio hardcodes `@2x` in its template, while the cadastral atlas
 * relies on MapLibre's `{r}` placeholder, which resolves to `@2x` on a
 * high-DPI display and to nothing otherwise. Both are supported so each view
 * keeps the suffix it already shipped with.
 */
export function basemapTileUrl(
  style: BasemapStyle,
  opts: { subdomains?: readonly string[]; retina?: 'at2x' | 'maplibre' } = {},
): string[] {
  const { subdomains = ['a', 'b', 'c'], retina = 'at2x' } = opts;
  const suffix = retina === 'maplibre' ? '{r}' : '@2x';
  return subdomains.map((s) =>
    cartoTile(`https://${s}.basemaps.cartocdn.com/rastertiles/${style}/{z}/{x}/{y}${suffix}.png`),
  );
}

/* ------------------------------------------------------------------ *
 * Local storage
 * ------------------------------------------------------------------ */

const BASEMAP_STORAGE_KEY = 'bhudrishti.basemap';

/**
 * The open-twin studio is built dark -- its own chrome, the buildings, the
 * utility overlay and the attribution are all tuned for a dark ground -- so
 * dark is the default there. The cadastral atlas was authored against CARTO's
 * `light_all`, and its parcel fills and status colours are legible on white,
 * so light is the default there. Each view persists its own choice under its
 * own key, because flipping to light on one map should not silently restyle
 * the other.
 */
export type BasemapPref = { theme: BasemapTheme; labels: boolean };

export function loadBasemapPref(storageKey: string, fallback: BasemapPref): BasemapPref {
  try {
    if (typeof window === 'undefined') return fallback;
    const raw = window.localStorage.getItem(`${BASEMAP_STORAGE_KEY}.${storageKey}`);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw) as Partial<BasemapPref>;
    return {
      theme: parsed.theme === 'light' || parsed.theme === 'dark' ? parsed.theme : fallback.theme,
      labels: typeof parsed.labels === 'boolean' ? parsed.labels : fallback.labels,
    };
  } catch {
    return fallback;
  }
}

export function saveBasemapPref(storageKey: string, pref: BasemapPref): void {
  try {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem(`${BASEMAP_STORAGE_KEY}.${storageKey}`, JSON.stringify(pref));
  } catch {
    /* private browsing or storage disabled: the toggle still works for the session */
  }
}

export function basemapStyleFor(pref: BasemapPref): BasemapStyle {
  return `${pref.theme}_${pref.labels ? 'all' : 'nolabels'}` as BasemapStyle;
}
