"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import { DICTIONARIES, LOCALES, type Locale } from "./dictionaries";

const STORAGE_KEY = "cra-locale";

interface I18nContextValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  /** Translate a source string; falls back to the source if untranslated. */
  t: (source: string) => string;
}

const I18nContext = createContext<I18nContextValue | null>(null);

function isLocale(value: string | null): value is Locale {
  return value !== null && (LOCALES as readonly string[]).includes(value);
}

// ── External "store" backed by localStorage ──────────────────────────────────
// useSyncExternalStore keeps the locale in sync without setState-in-effect, and
// returns "en" during SSR so server and first client render match (no hydration
// mismatch); the real value is adopted on the client's first commit.

const listeners = new Set<() => void>();

function emit(): void {
  listeners.forEach((l) => l());
}

function subscribe(callback: () => void): () => void {
  listeners.add(callback);
  const onStorage = (e: StorageEvent) => {
    if (e.key === STORAGE_KEY) callback();
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(callback);
    window.removeEventListener("storage", onStorage);
  };
}

function getClientLocale(): Locale {
  const stored = window.localStorage.getItem(STORAGE_KEY);
  if (isLocale(stored)) return stored;
  const nav = window.navigator.language?.slice(0, 2) ?? null;
  return isLocale(nav) ? (nav as Locale) : "en";
}

function getServerLocale(): Locale {
  return "en";
}

export interface LocaleProviderProps {
  children: ReactNode;
}

export function LocaleProvider({ children }: LocaleProviderProps) {
  const locale = useSyncExternalStore(subscribe, getClientLocale, getServerLocale);

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  const setLocale = useCallback((next: Locale) => {
    window.localStorage.setItem(STORAGE_KEY, next);
    emit();
  }, []);

  const t = useCallback(
    (source: string) => DICTIONARIES[locale]?.[source] ?? source,
    [locale],
  );

  const value = useMemo<I18nContextValue>(
    () => ({ locale, setLocale, t }),
    [locale, setLocale, t],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
  const ctx = useContext(I18nContext);
  if (ctx === null) {
    // Safe fallback so components work even outside the provider (e.g. tests).
    return { locale: "en", setLocale: () => undefined, t: (s) => s };
  }
  return ctx;
}

/** Convenience hook returning just the translate function. */
export function useT(): (source: string) => string {
  return useI18n().t;
}
