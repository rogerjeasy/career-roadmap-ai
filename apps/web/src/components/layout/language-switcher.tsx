"use client";

import { useI18n } from "@/lib/i18n";
import { LOCALES, LOCALE_LABELS, type Locale } from "@/lib/i18n/dictionaries";

export interface LanguageSwitcherProps {
  className?: string;
}

export function LanguageSwitcher({ className }: LanguageSwitcherProps): React.ReactElement {
  const { locale, setLocale, t } = useI18n();

  return (
    <label className={className}>
      <span className="sr-only">{t("Language")}</span>
      <select
        value={locale}
        onChange={(e) => setLocale(e.target.value as Locale)}
        aria-label={t("Language")}
        className="w-full rounded-[6px] border border-rule bg-bg px-2.5 py-1.5 text-[12px] text-ink-2 transition-colors hover:border-rule-strong focus:border-green focus:outline-none"
      >
        {LOCALES.map((l) => (
          <option key={l} value={l}>
            {LOCALE_LABELS[l]}
          </option>
        ))}
      </select>
    </label>
  );
}
