/**
 * Minimal message lookup. Deliberately not next-intl: the catalogs are flat
 * key -> string with {placeholder} interpolation, which is all this app
 * needs, and avoiding the dependency removes a version-compat surface
 * against Next 16 / React 19 for ~30 lines of code.
 *
 * The one rule that matters is enforced by the shape: a message is always
 * looked up whole, never assembled by concatenating fragments, because word
 * order is the translator's decision and not English's.
 */

import en from "@/messages/en.json";
import hi from "@/messages/hi.json";
import pa from "@/messages/pa.json";
import ta from "@/messages/ta.json";
import type { LocaleCode } from "./registry";

export type Messages = Record<string, string>;

const CATALOGS: Record<LocaleCode, Messages> = { en, hi, pa, ta };

export function messagesFor(locale: LocaleCode): Messages {
  return CATALOGS[locale] ?? CATALOGS.en;
}

/**
 * Falls back to English for a missing key rather than rendering the raw key
 * at someone -- a visible English string is a bug, but a visible
 * "citations.heading" is a worse one.
 */
export function translate(
  locale: LocaleCode,
  key: string,
  values?: Record<string, string | number>,
): string {
  const catalog = messagesFor(locale);
  let text = catalog[key] ?? CATALOGS.en[key] ?? key;
  if (values) {
    for (const [name, value] of Object.entries(values)) {
      text = text.replace(new RegExp(`\\{${name}\\}`, "g"), String(value));
    }
  }
  return text;
}

export function makeTranslator(locale: LocaleCode) {
  return (key: string, values?: Record<string, string | number>) =>
    translate(locale, key, values);
}

/** Every catalog must carry every key, or a locale silently leaks English. */
export function missingKeys(locale: LocaleCode): string[] {
  const base = Object.keys(CATALOGS.en);
  const catalog = messagesFor(locale);
  return base.filter((key) => !(key in catalog));
}

export { CATALOGS };
