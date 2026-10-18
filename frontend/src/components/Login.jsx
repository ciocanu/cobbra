import { useState } from 'react'
import { useNavigate, useLocation, Link } from 'react-router-dom'
import { login, register } from '../services/api'
import { markLoggedIn } from '../services/auth'
import Alert from './Alert'
import DemoButton from './DemoButton'
import CobbraLogo from './CobbraLogo'
import { useTranslation } from 'react-i18next'

export default function Login() {
  const { t } = useTranslation()
  const location = useLocation()
  const [mode, setMode] = useState(location.pathname === '/register' ? 'register' : 'login')   // 'login' | 'register'
  const [username, setUsername] = useState('')
  const [email,    setEmail]    = useState('')
  const [password, setPassword] = useState('')
  const [honeypot, setHoneypot] = useState('')
  const [agreedTerms, setAgreedTerms] = useState(false)
  const [agreedAge,   setAgreedAge]   = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  const switchMode = (m) => {
    setMode(m)
    setError('')
    setUsername('')
    setEmail('')
    setPassword('')
    setAgreedTerms(false)
    setAgreedAge(false)
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    if (mode === 'register') {
      if (!agreedAge)   { setError(t('login.errorAgeRequired')); return }
      if (!agreedTerms) { setError(t('login.errorTermsRequired')); return }
    }
    setLoading(true)
    try {
      const fn = mode === 'register'
        ? () => register(username, email, password, honeypot)
        : () => login(username, password)
      await fn()
      markLoggedIn()
      navigate('/dashboard')
    } catch (err) {
      setError(err.response?.data?.detail || t('login.errorFallback'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-page">
      <div className="login-box">
        <div className="login-logo">
          <CobbraLogo height={32} />
        </div>

        <div className="login-tabs">
          <button
            className={`login-tab${mode === 'login' ? ' active' : ''}`}
            onClick={() => switchMode('login')}
          >
            {t('login.tabSignIn')}
          </button>
          <button
            className={`login-tab${mode === 'register' ? ' active' : ''}`}
            onClick={() => switchMode('register')}
          >
            {t('login.tabRegister')}
          </button>
        </div>

        <p className="login-sub">
          {mode === 'register' ? t('login.subRegister') : t('login.subSignIn')}
        </p>

        {error && <Alert variant="error" style={{ marginBottom: 16 }}>{error}</Alert>}

        <form onSubmit={handleSubmit} className="login-form">
          <div className="login-field">
            <label htmlFor="login-username">{t('login.usernameLabel')}</label>
            <input
              id="login-username"
              type="text"
              value={username}
              onChange={e => setUsername(e.target.value)}
              autoFocus
              autoComplete="username"
              required
            />
          </div>
          {mode === 'register' && (
            <div className="login-field">
              <label htmlFor="login-email">{t('login.emailLabel')}</label>
              <input
                id="login-email"
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                autoComplete="email"
                required
              />
            </div>
          )}
          <div className="login-field">
            <label htmlFor="login-password">{t('login.passwordLabel')}</label>
            <input
              id="login-password"
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              autoComplete={mode === 'register' ? 'new-password' : 'current-password'}
              required
            />
            {mode === 'register' && <span className="login-hint">{t('login.passwordHint')}</span>}
          </div>
          {/* Honeypot — hidden from real users, bots fill it in */}
          <input
            type="text"
            name="website"
            value={honeypot}
            onChange={e => setHoneypot(e.target.value)}
            tabIndex={-1}
            autoComplete="off"
            aria-hidden="true"
            style={{ position: 'absolute', left: '-9999px', width: 1, height: 1, opacity: 0 }}
          />
          {mode === 'register' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, margin: '4px 0' }}>
              <label style={{ display: 'flex', alignItems: 'flex-start', gap: 10, cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={agreedAge}
                  onChange={e => { setAgreedAge(e.target.checked); setError('') }}
                  style={{ marginTop: 2, accentColor: 'var(--accent)', flexShrink: 0 }}
                />
                <span style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.5 }}>
                  {t('login.ageCheckbox')}
                </span>
              </label>
              <label style={{ display: 'flex', alignItems: 'flex-start', gap: 10, cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={agreedTerms}
                  onChange={e => { setAgreedTerms(e.target.checked); setError('') }}
                  style={{ marginTop: 2, accentColor: 'var(--accent)', flexShrink: 0 }}
                />
                <span style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.5 }}>
                  {t('login.termsCheckboxPre')}{' '}
                  <Link to="/terms"   target="_blank" style={{ color: 'var(--accent)', textDecoration: 'none' }}>{t('login.termsLink')}</Link>
                  {' '}{t('login.termsAnd')}{' '}
                  <Link to="/privacy" target="_blank" style={{ color: 'var(--accent)', textDecoration: 'none' }}>{t('login.privacyLink')}</Link>.
                </span>
              </label>
            </div>
          )}
          <button type="submit" className="btn btn-primary login-btn" disabled={loading}>
            {loading
              ? <span className="spinner" style={{ width: 16, height: 16, borderWidth: 2 }} />
              : mode === 'register' ? t('login.submitRegister') : t('login.submitSignIn')
            }
          </button>
        </form>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 12 }}>
          <DemoButton className="btn btn-ghost login-btn">{t('login.tryDemo')}</DemoButton>
        </div>

        <p style={{ marginTop: 20, fontSize: 11, color: 'var(--text-muted)', textAlign: 'center', lineHeight: 1.6 }}>
          {t('login.cookieNotice')}
        </p>
      </div>
    </div>
  )
}
