/**
 * The demonstration parcel identifier.
 *
 * This is not a ULPIN. A ULPIN is a 14-character unique property identifier
 * issued by the state registry, and no registry has issued this string. It
 * belongs to a synthetic fixture generated for the Airoli Sector 8 showcase, and
 * the backend refuses to serve it unless ENABLE_DEMO_MODE is set.
 *
 * It used to be copied as a bare literal into nineteen files, so the number was
 * impossible to reason about: a reader could not tell an invented showcase
 * identifier from a registry record without opening each call site, and
 * replacing it meant finding thirty-nine sites. It is defined once here and
 * imported everywhere.
 */
export const DEMO_ULPIN = '12345678901234';

/**
 * Landing-only alias, kept because LandingPage.tsx imports it and the landing
 * page is frozen. New code should use DEMO_ULPIN, which says what the value
 * is.
 */
export const HERO_ULPIN = DEMO_ULPIN;
