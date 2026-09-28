/**
 * Shared role badge classes.
 *
 * Extracted from AppShell so the role chip in SettingsPage cannot drift from
 * the one in the top bar.
 */

/**
 * Role badge classes, written out in full for each role.
 *
 * These were previously assembled as
 *   `bg-${permissions.color}-100 text-${permissions.color}-700 border-${permissions.color}-200`
 * Tailwind extracts class names by scanning source text for complete literals,
 * so a template-interpolated name like `bg-${color}-100` is never matched and
 * those utilities are never generated. The badge therefore rendered with no
 * colour at all for the roles whose utilities happened to be unused
 * elsewhere: Taluka Verifier (sky) and Public (gray) had no bg or text class
 * in the built stylesheet, while purple, blue and amber appeared to work only
 * because some other file happened to use those exact utilities.
 *
 * Listing every combination literally is what makes Tailwind emit them. The
 * `Record` type keeps this exhaustive against `PERMISSIONS` in
 * context/AppContext.tsx, so adding a role without a colour is a type error
 * rather than a silently unstyled badge.
 *
 * The keys are retained for compatibility with `permissions.color`, but they no
 * longer describe a hue. Roles are separated by authority tier instead, which
 * is what the colour was standing in for: solid ink for the state admin, solid
 * accent for a district verifier (can approve), accent tint for a taluka
 * verifier (can approve, narrower remit), then progressively lighter neutrals
 * for submitter, objector and read-only.
 */
export type RoleColor = 'purple' | 'blue' | 'sky' | 'amber' | 'green' | 'gray';

export const ROLE_BADGE_CLASSES: Record<RoleColor, string> = {
  purple: 'bg-ink text-white border-ink',
  blue: 'bg-accent text-white border-ink',
  sky: 'bg-accent-faint text-accent-strong border-ink',
  amber: 'bg-canvas text-ink border-ink',
  green: 'bg-chalk text-ink-soft border-ink',
  gray: 'bg-canvas text-ink-mut border-ink',
};

/** Neutral fallback so an unrecognised role still renders legibly. */
export const ROLE_BADGE_FALLBACK = 'bg-canvas text-ink-mut border-ink';
