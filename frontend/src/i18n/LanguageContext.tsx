import React, { createContext, useContext, useState } from 'react';
import { Language, translations, TranslationDictionary, FALLBACK_LANGUAGE } from './translations';

const STORAGE_KEY = 'bhudrishti_lang';

export interface LanguageOption {
  code: Language;
  /** Name in the language itself, so the option is readable in the script it selects. */
  label: string;
}

export const LANGUAGE_OPTIONS: readonly LanguageOption[] = [
  { code: 'en', label: 'English' },
  { code: 'hi', label: 'हिन्दी (Hindi)' },
];

const isLanguage = (value: unknown): value is Language =>
  typeof value === 'string' && LANGUAGE_OPTIONS.some((option) => option.code === value);

/**
 * English is the source of truth and the fallback. A locale key that is absent,
 * blank, or not a string is resolved back to the English string rather than
 * rendering `undefined`, a literal brace, or a stray number in the UI.
 * Structural completeness is additionally enforced at compile time: every
 * locale is typed as TranslationDictionary, so a missing or misspelled key
 * fails the build.
 */
const isPlainObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const withFallback = (locale: unknown): TranslationDictionary => {
  const base = translations[FALLBACK_LANGUAGE];
  if (!isPlainObject(locale)) return base;

  const merge = (english: unknown, translated: unknown): unknown => {
    if (isPlainObject(english)) {
      const merged: Record<string, unknown> = { ...english };
      const source = isPlainObject(translated) ? translated : {};
      for (const key of Object.keys(english)) merged[key] = merge(english[key], source[key]);
      return merged;
    }
    return typeof translated === 'string' && translated.trim().length > 0 ? translated : english;
  };

  return merge(base, locale) as TranslationDictionary;
};

interface LanguageContextType {
  language: Language;
  setLanguage: (lang: Language) => void;
  t: TranslationDictionary;
}

const LanguageContext = createContext<LanguageContextType | undefined>(undefined);

export const LanguageProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  // A locale is honoured only if it is currently offered by LANGUAGE_OPTIONS.
  // A stale value from a previous session (an old 'mr', or garbage) falls back
  // to English instead of leaving the app blank or half-translated.
  const [language, setLanguageState] = useState<Language>(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    return isLanguage(saved) ? saved : FALLBACK_LANGUAGE;
  });

  const setLanguage = (lang: Language) => {
    setLanguageState(lang);
    localStorage.setItem(STORAGE_KEY, lang);
  };

  const t = withFallback(translations[language]);

  return (
    <LanguageContext.Provider value={{ language, setLanguage, t }}>
      {children}
    </LanguageContext.Provider>
  );
};

export const useTranslation = (): LanguageContextType => {
  const context = useContext(LanguageContext);
  if (!context) {
    throw new Error('useTranslation must be used within a LanguageProvider');
  }
  return context;
};
