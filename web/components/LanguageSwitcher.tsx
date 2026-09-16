"use client";

import { LOCALE_CODES, LOCALES, type LocaleCode } from "@/lib/registry";

/**
 * Two independent axes, per the original design: someone may read the
 * interface in English but want a Punjabi explanation to play for a parent.
 * `contentLocale` follows `uiLocale` until the user changes it, then stops
 * following -- sticky, one-directional.
 *
 * Options show endonyms only. A person who needs the Punjabi UI cannot
 * necessarily read the word "Punjabi".
 */
export function LanguageSwitcher({
  uiLocale,
  contentLocale,
  contentFollows,
  onUiChange,
  onContentChange,
  t,
}: {
  uiLocale: LocaleCode;
  contentLocale: LocaleCode;
  contentFollows: boolean;
  onUiChange: (locale: LocaleCode) => void;
  onContentChange: (locale: LocaleCode) => void;
  t: (key: string) => string;
}) {
  return (
    <div className="langbar">
      <div className="langrow">
        <label id="ui-lang-label">{t("language.ui")}</label>
        <div className="chips" role="group" aria-labelledby="ui-lang-label">
          {LOCALE_CODES.map((code) => (
            <button
              key={code}
              type="button"
              className="chip"
              lang={code}
              aria-pressed={uiLocale === code}
              onClick={() => onUiChange(code)}
            >
              {LOCALES[code].endonym}
            </button>
          ))}
        </div>
      </div>

      <div className="langrow">
        <label id="content-lang-label">
          {t("language.content")}
          {contentFollows ? ` · ${t("language.follows")}` : ""}
        </label>
        <div className="chips" role="group" aria-labelledby="content-lang-label">
          {LOCALE_CODES.map((code) => (
            <button
              key={code}
              type="button"
              className="chip"
              lang={code}
              aria-pressed={contentLocale === code}
              onClick={() => onContentChange(code)}
            >
              {LOCALES[code].endonym}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
