/**
 * Mirrors api/language/registry.py. A test asserts the two lists match --
 * a locale that exists on one side and not the other is a runtime English
 * leak in an otherwise Punjabi UI.
 */

export type LocaleCode = "en" | "hi" | "pa" | "ta";

export interface Locale {
  code: LocaleCode;
  bcp47: string;
  script: string;
  nameEn: string;
  /** Shown in the switcher. Never the English name -- someone who needs the
   *  Punjabi UI cannot necessarily read the word "Punjabi". */
  endonym: string;
  /** Tamil and Devanagari glyphs collide at Latin line-height. */
  lineHeight: number;
  direction: "ltr" | "rtl";
}

export const LOCALES: Record<LocaleCode, Locale> = {
  en: { code: "en", bcp47: "en-IN", script: "Latn", nameEn: "English",
        endonym: "English", lineHeight: 1.6, direction: "ltr" },
  hi: { code: "hi", bcp47: "hi-IN", script: "Deva", nameEn: "Hindi",
        endonym: "हिन्दी", lineHeight: 1.85, direction: "ltr" },
  pa: { code: "pa", bcp47: "pa-IN", script: "Guru", nameEn: "Punjabi",
        endonym: "ਪੰਜਾਬੀ", lineHeight: 1.85, direction: "ltr" },
  ta: { code: "ta", bcp47: "ta-IN", script: "Taml", nameEn: "Tamil",
        endonym: "தமிழ்", lineHeight: 1.95, direction: "ltr" },
};

export const LOCALE_CODES = Object.keys(LOCALES) as LocaleCode[];
export const DEFAULT_LOCALE: LocaleCode = "en";

export function resolveLocale(code: string | null | undefined): LocaleCode {
  if (!code) return DEFAULT_LOCALE;
  const primary = code.replace("_", "-").split("-")[0].toLowerCase();
  return (LOCALE_CODES as string[]).includes(primary)
    ? (primary as LocaleCode)
    : DEFAULT_LOCALE;
}

/**
 * Indian digit grouping: 2,00,000 -- not 200,000. Applied in one place so a
 * formatted number is never string-concatenated into a translated sentence.
 */
export function formatIndianNumber(value: number, locale: LocaleCode): string {
  return new Intl.NumberFormat(LOCALES[locale].bcp47).format(value);
}
