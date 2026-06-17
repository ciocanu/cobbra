import { useTranslation } from 'react-i18next'
import { Languages } from 'lucide-react'
import { SUPPORTED_LANGUAGES } from '../i18n'

/**
 * Compact language selector. Persists the choice via i18next's
 * languageDetector (localStorage key "cobbra_lang"). Until pt.json is
 * filled in, selecting Português falls back to English transparently.
 */
export default function LanguageSwitcher() {
  const { t, i18n } = useTranslation()
  const current = (i18n.resolvedLanguage || i18n.language || 'en').split('-')[0]

  return (
    <label
      style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px', color: 'var(--text-muted)', fontSize: 12 }}
    >
      <Languages size={13} aria-hidden="true" />
      <select
        value={current}
        onChange={e => i18n.changeLanguage(e.target.value)}
        aria-label={t('languageSwitcher.label')}
        className="nav-label"
        style={{
          flex: 1, background: 'transparent', color: 'var(--text-secondary)',
          border: '1px solid var(--border)', borderRadius: 5, padding: '3px 6px',
          fontSize: 12, cursor: 'pointer',
        }}
      >
        {SUPPORTED_LANGUAGES.map(({ code, label }) => (
          <option key={code} value={code} style={{ background: 'var(--bg-secondary)' }}>{label}</option>
        ))}
      </select>
    </label>
  )
}
