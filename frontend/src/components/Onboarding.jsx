import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { getSettings, updateSettings } from '../services/api'
import { useInvalidate } from '../services/queries'
import { Bike, HeartPulse } from 'lucide-react'
import Alert from './Alert'

const BIKE_TYPES = [
  { value: 'road',   labelKey: 'onboarding.bikeTypes.road' },
  { value: 'gravel', labelKey: 'onboarding.bikeTypes.gravel' },
  { value: 'mtb',    labelKey: 'onboarding.bikeTypes.mtb' },
  { value: 'tt',     labelKey: 'onboarding.bikeTypes.tt' },
  { value: 'ebike',  labelKey: 'onboarding.bikeTypes.ebike' },
  { value: 'other',  labelKey: 'onboarding.bikeTypes.other' },
]

const EXPERIENCE_LEVELS = [
  { value: 'beginner',     labelKey: 'onboarding.experienceLevels.beginner',     descKey: 'onboarding.experienceLevels.beginnerDesc' },
  { value: 'intermediate', labelKey: 'onboarding.experienceLevels.intermediate', descKey: 'onboarding.experienceLevels.intermediateDesc' },
  { value: 'advanced',     labelKey: 'onboarding.experienceLevels.advanced',     descKey: 'onboarding.experienceLevels.advancedDesc' },
]

// Mirrors backend utils.estimate_max_hr_tanaka — used only for the live preview;
// the backend computes and persists the authoritative value on save.
function estimateMaxHrTanaka(age) {
  return Math.round(208 - 0.7 * age)
}

export default function Onboarding() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const invalidate = useInvalidate()
  const [age, setAge] = useState('')
  const [weightKg, setWeightKg] = useState('')
  const [restingHr, setRestingHr] = useState('')
  const [ftp, setFtp] = useState('')
  const [experienceLevel, setExperienceLevel] = useState('')
  const [bikeType, setBikeType] = useState('')
  const [knowsMaxHr, setKnowsMaxHr] = useState(false)
  const [maxHr, setMaxHr] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    getSettings().then(r => {
      const s = r.data
      if (s.age != null) setAge(String(s.age))
      if (s.weight_kg != null) setWeightKg(String(s.weight_kg))
      if (s.resting_hr != null) setRestingHr(String(s.resting_hr))
      if (s.ftp != null) setFtp(String(s.ftp))
      if (s.experience_level) setExperienceLevel(s.experience_level)
      if (s.bike_type) setBikeType(s.bike_type)
      if (s.max_hr != null && s.max_hr_source === 'user') {
        setKnowsMaxHr(true)
        setMaxHr(String(s.max_hr))
      }
    }).catch(() => {})
  }, [])

  const ageNum = parseFloat(age)
  const previewMaxHr = ageNum >= 10 && ageNum <= 100 ? estimateMaxHrTanaka(ageNum) : null

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')

    if (!age || !weightKg || !experienceLevel || !bikeType) {
      setError(t('onboarding.errorRequired'))
      return
    }
    if (knowsMaxHr && !maxHr) {
      setError(t('onboarding.errorMaxHr'))
      return
    }

    setSaving(true)
    try {
      const payload = {
        age: parseFloat(age),
        weight_kg: parseFloat(weightKg),
        experience_level: experienceLevel,
        bike_type: bikeType,
      }
      if (restingHr) payload.resting_hr = parseFloat(restingHr)
      if (ftp) payload.ftp = parseFloat(ftp)
      if (knowsMaxHr) payload.max_hr = parseFloat(maxHr)
      await updateSettings(payload)
      // Refresh the shared settings cache so Layout's onboarding gate sees the
      // now-complete profile instead of redirecting straight back here.
      invalidate.settings()
      navigate('/dashboard', { replace: true })
    } catch (e) {
      setError(e.response?.data?.detail || t('onboarding.errorSaveFailed'))
    } finally {
      setSaving(false)
    }
  }

  const handleSkip = () => navigate('/dashboard', { replace: true })

  return (
    <div className="login-page">
      <div className="login-box" style={{ maxWidth: 520 }}>
        <div className="login-logo">
          <div className="sidebar-logo-icon"><Bike size={18} strokeWidth={2.5} /></div>
          <span className="sidebar-logo-text" style={{ fontSize: 22 }}>COBBRA</span>
        </div>

        <div className="login-title">{t('onboarding.title')}</div>
        <p className="login-sub">{t('onboarding.subtitle')}</p>

        {error && <Alert variant="error" style={{ marginBottom: 16 }}>{error}</Alert>}

        <form onSubmit={handleSubmit} className="login-form">
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
            <div className="login-field">
              <label htmlFor="ob-age">{t('onboarding.ageLabel')}</label>
              <input id="ob-age" type="number" min={10} max={100} step={1}
                value={age} onChange={e => setAge(e.target.value)} placeholder={t('onboarding.agePlaceholder')} required />
            </div>
            <div className="login-field">
              <label htmlFor="ob-weight">{t('onboarding.weightLabel')}</label>
              <input id="ob-weight" type="number" min={30} max={250} step={0.1}
                value={weightKg} onChange={e => setWeightKg(e.target.value)} placeholder={t('onboarding.weightPlaceholder')} required />
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
            <div className="login-field">
              <label htmlFor="ob-resting-hr">{t('onboarding.restingHrLabel')}</label>
              <input id="ob-resting-hr" type="number" min={30} max={100} step={1}
                value={restingHr} onChange={e => setRestingHr(e.target.value)} placeholder={t('onboarding.restingHrPlaceholder')} />
              <span className="login-hint">{t('onboarding.restingHrHint')}</span>
            </div>
            <div className="login-field">
              <label htmlFor="ob-ftp">{t('onboarding.ftpLabel')}</label>
              <input id="ob-ftp" type="number" min={50} max={600} step={1}
                value={ftp} onChange={e => setFtp(e.target.value)} placeholder={t('onboarding.ftpPlaceholder')} />
              <span className="login-hint">{t('onboarding.ftpHint')}</span>
            </div>
          </div>

          <div className="login-field">
            <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <HeartPulse size={13} /> {t('onboarding.maxHrLabel')}
            </label>
            <div role="group" aria-label={t('onboarding.maxHrGroupLabel')} style={{ display: 'flex', gap: 8, marginBottom: knowsMaxHr ? 8 : 0 }}>
              <button type="button" onClick={() => setKnowsMaxHr(false)} aria-pressed={!knowsMaxHr}
                style={{ flex: 1, padding: '8px 10px', borderRadius: 8, cursor: 'pointer', fontSize: 12, fontWeight: 600,
                  border: !knowsMaxHr ? '1px solid color-mix(in srgb, var(--accent) 30%, transparent)' : '1px solid var(--border)',
                  background: !knowsMaxHr ? 'color-mix(in srgb, var(--accent) 8%, transparent)' : 'var(--bg-secondary)',
                  color: !knowsMaxHr ? 'var(--accent)' : 'var(--text-muted)' }}>
                {t('onboarding.estimateForMe')}
              </button>
              <button type="button" onClick={() => setKnowsMaxHr(true)} aria-pressed={knowsMaxHr}
                style={{ flex: 1, padding: '8px 10px', borderRadius: 8, cursor: 'pointer', fontSize: 12, fontWeight: 600,
                  border: knowsMaxHr ? '1px solid color-mix(in srgb, var(--accent) 30%, transparent)' : '1px solid var(--border)',
                  background: knowsMaxHr ? 'color-mix(in srgb, var(--accent) 8%, transparent)' : 'var(--bg-secondary)',
                  color: knowsMaxHr ? 'var(--accent)' : 'var(--text-muted)' }}>
                {t('onboarding.knowMyMaxHr')}
              </button>
            </div>
            {knowsMaxHr ? (
              <input type="number" min={100} max={250} step={1} value={maxHr}
                onChange={e => setMaxHr(e.target.value)} placeholder="185"
                style={{ marginTop: 8 }} />
            ) : (
              <span className="login-hint">
                {previewMaxHr
                  ? t('onboarding.maxHrEstimate', { bpm: previewMaxHr })
                  : t('onboarding.maxHrEnterAge')}
              </span>
            )}
          </div>

          <div className="login-field">
            <label>{t('onboarding.bikeTypeLabel')}</label>
            <div role="group" aria-label={t('onboarding.bikeTypeGroupLabel')} style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(80px, 1fr))', gap: 8 }}>
              {BIKE_TYPES.map(opt => (
                <button key={opt.value} type="button" onClick={() => setBikeType(opt.value)} aria-pressed={bikeType === opt.value}
                  style={{ padding: '8px 4px', borderRadius: 8, cursor: 'pointer', textAlign: 'center', fontSize: 12, fontWeight: 600,
                    border: bikeType === opt.value ? '1px solid color-mix(in srgb, var(--accent) 30%, transparent)' : '1px solid var(--border)',
                    background: bikeType === opt.value ? 'color-mix(in srgb, var(--accent) 8%, transparent)' : 'var(--bg-secondary)',
                    color: bikeType === opt.value ? 'var(--accent)' : 'var(--text-muted)' }}>
                  {t(opt.labelKey)}
                </button>
              ))}
            </div>
          </div>

          <div className="login-field">
            <label>{t('onboarding.experienceLevelLabel')}</label>
            <div role="group" aria-label={t('onboarding.experienceLevelGroupLabel')} style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {EXPERIENCE_LEVELS.map(opt => (
                <button key={opt.value} type="button" onClick={() => setExperienceLevel(opt.value)} aria-pressed={experienceLevel === opt.value}
                  style={{ display: 'flex', flexDirection: 'column', gap: 1, padding: '10px 14px', borderRadius: 8, cursor: 'pointer', textAlign: 'left',
                    border: experienceLevel === opt.value ? '1px solid color-mix(in srgb, var(--accent) 25%, transparent)' : '1px solid var(--border)',
                    background: experienceLevel === opt.value ? 'color-mix(in srgb, var(--accent) 6%, transparent)' : 'var(--bg-secondary)' }}>
                  <span style={{ fontSize: 13, fontWeight: 600, color: experienceLevel === opt.value ? 'var(--accent)' : 'var(--text-primary)' }}>{t(opt.labelKey)}</span>
                  <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{t(opt.descKey)}</span>
                </button>
              ))}
            </div>
          </div>

          <button type="submit" className="btn btn-primary login-btn" disabled={saving}>
            {saving
              ? <span className="spinner" style={{ width: 16, height: 16, borderWidth: 2 }} />
              : t('onboarding.saveBtn')}
          </button>
          <button type="button" className="btn btn-ghost" style={{ justifyContent: 'center' }} onClick={handleSkip} disabled={saving}>
            {t('onboarding.skipBtn')}
          </button>
        </form>
      </div>
    </div>
  )
}
