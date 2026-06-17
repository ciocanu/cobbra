import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import LanguageDetector from 'i18next-browser-languagedetector'

import en from './locales/en.json'
import pt from './locales/pt.json'

export const SUPPORTED_LANGUAGES = [
  { code: 'en', label: 'English' },
  { code: 'pt', label: 'Português' },
]

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      en: { translation: en },
      pt: { translation: pt },
    },
    fallbackLng: 'en',
    supportedLngs: SUPPORTED_LANGUAGES.map(l => l.code),
    // pt.json ships with empty string values for now — treat "" as missing so
    // every key falls back to English until the Portuguese copy is filled in.
    returnEmptyString: false,
    detection: {
      // Remembered choice wins; otherwise sniff the browser. Persisted to
      // localStorage so the selection survives reloads.
      order: ['localStorage', 'navigator'],
      lookupLocalStorage: 'cobbra_lang',
      caches: ['localStorage'],
    },
    interpolation: {
      escapeValue: false, // React already escapes
    },
    react: {
      useSuspense: false, // resources are bundled synchronously
    },
  })

export default i18n
