import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { getGoals, setGoal, deleteGoal, getWeeklyStats, getYearStats } from '../services/api'
import { Target, Trash2, Flame, TrendingUp, TrendingDown, Plus } from 'lucide-react'
import Alert from './Alert'

const GOAL_TYPES = [
  { value: 'weekly_distance_km',  labelKey: 'goals.goalTypes.weekly_distance_km',  unit: 'km',    period: 'week',  field: 'distance_km', placeholder: '150' },
  { value: 'weekly_rides',        labelKey: 'goals.goalTypes.weekly_rides',         unit: 'rides', period: 'week',  field: 'rides',       placeholder: '4' },
  { value: 'weekly_elevation_m',  labelKey: 'goals.goalTypes.weekly_elevation_m',   unit: 'm',     period: 'week',  field: 'elevation_m', placeholder: '1500' },
  { value: 'monthly_distance_km', labelKey: 'goals.goalTypes.monthly_distance_km',  unit: 'km',    period: 'month', field: 'distance_km', placeholder: '600' },
  { value: 'monthly_elevation_m', labelKey: 'goals.goalTypes.monthly_elevation_m',  unit: 'm',     period: 'month', field: 'elevation_m', placeholder: '5000' },
  { value: 'annual_distance_km',  labelKey: 'goals.goalTypes.annual_distance_km',   unit: 'km',    period: 'year',  field: 'distance_km', placeholder: '5000' },
]

function daysLeftInWeek() {
  const day = new Date().getDay()
  const daysFromMonday = day === 0 ? 6 : day - 1
  return 6 - daysFromMonday
}

function daysLeftInMonth() {
  const now = new Date()
  return new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate() - now.getDate()
}

function daysLeftInYear() {
  const now = new Date()
  return Math.round((new Date(now.getFullYear(), 11, 31) - now) / 86400000)
}

function fmtVal(v, unit) {
  if (unit === 'km') return v.toFixed(1)
  if (unit === 'm') return Math.round(v).toLocaleString()
  return Math.round(v)
}

export default function Goals() {
  const { t } = useTranslation()
  const [goals, setGoals] = useState([])
  const [weeklyStats, setWeeklyStats] = useState([])
  const [yearStats, setYearStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [showAdd, setShowAdd] = useState(false)
  const [selectedType, setSelectedType] = useState(GOAL_TYPES[0].value)
  const [target, setTarget] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    Promise.all([getGoals(), getWeeklyStats(16), getYearStats()])
      .then(([g, w, y]) => {
        setGoals(g.data)
        setWeeklyStats(w.data)
        setYearStats(y.data)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const computeProgress = (goal) => {
    const meta = GOAL_TYPES.find(tp => tp.value === goal.goal_type)
    if (!meta) return { current: 0, pct: 0 }
    let current = 0
    if (meta.period === 'week' && weeklyStats.length > 0) {
      current = weeklyStats[weeklyStats.length - 1][meta.field] || 0
    } else if (meta.period === 'month' && yearStats) {
      const mo = yearStats.monthly[new Date().getMonth()]
      current = mo ? (mo[meta.field] || 0) : 0
    } else if (meta.period === 'year' && yearStats) {
      current = yearStats.current[meta.field] || 0
    }
    return { current, pct: (current / goal.target) * 100 }
  }

  const computeStreak = (goal) => {
    const meta = GOAL_TYPES.find(tp => tp.value === goal.goal_type)
    if (!meta) return 0
    if (meta.period === 'week' && weeklyStats.length > 1) {
      const completed = weeklyStats.slice(0, -1)
      let streak = 0
      for (let i = completed.length - 1; i >= 0; i--) {
        if ((completed[i][meta.field] || 0) >= goal.target) streak++
        else break
      }
      return streak
    }
    if (meta.period === 'month' && yearStats) {
      const currentMonthNum = new Date().getMonth() + 1
      const completed = yearStats.monthly.filter(m => m.month_num < currentMonthNum)
      let streak = 0
      for (let i = completed.length - 1; i >= 0; i--) {
        if ((completed[i][meta.field] || 0) >= goal.target) streak++
        else break
      }
      return streak
    }
    return 0
  }

  const computePacing = (goal) => {
    if (!yearStats) return null
    const meta = GOAL_TYPES.find(tp => tp.value === goal.goal_type)
    if (meta?.period !== 'year') return null
    const now = new Date()
    const startOfYear = new Date(now.getFullYear(), 0, 1)
    const endOfYear = new Date(now.getFullYear(), 11, 31)
    const totalDays = (endOfYear - startOfYear) / 86400000
    const daysPassed = (now - startOfYear) / 86400000
    const expectedFraction = daysPassed / totalDays
    const { current } = computeProgress(goal)
    const pace = expectedFraction > 0 ? Math.round(current / expectedFraction) : 0
    const delta = Math.round(current - goal.target * expectedFraction)
    return { pace, delta }
  }

  const daysLeft = (period) => {
    if (period === 'week') return daysLeftInWeek()
    if (period === 'month') return daysLeftInMonth()
    return daysLeftInYear()
  }

  const handleSave = async () => {
    if (!target || Number(target) <= 0) { setError(t('goals.errorInvalidTarget')); return }
    setError('')
    setSaving(true)
    try {
      const res = await setGoal(selectedType, Number(target))
      setGoals(prev => {
        const exists = prev.find(g => g.goal_type === selectedType)
        return exists ? prev.map(g => g.goal_type === selectedType ? res.data : g) : [...prev, res.data]
      })
      setTarget('')
      setShowAdd(false)
    } catch (e) {
      setError(e.response?.data?.detail || t('goals.errorFailedSave'))
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (id) => {
    await deleteGoal(id)
    setGoals(prev => prev.filter(g => g.id !== id))
  }

  if (loading) return <div className="loading-center"><div className="spinner" /></div>

  const availableTypes = GOAL_TYPES.filter(tp => !goals.find(g => g.goal_type === tp.value))

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1 className="page-title">
            <Target size={22} style={{ display: 'inline', marginRight: 8, color: 'var(--accent)' }} />
            {t('goals.title')}
          </h1>
          <p className="page-subtitle">{t('goals.subtitle')}</p>
        </div>
        {availableTypes.length > 0 && !showAdd && (
          <button className="btn btn-primary" onClick={() => setShowAdd(true)}>
            <Plus size={13} /> {t('goals.addGoal')}
          </button>
        )}
      </div>

      {showAdd && (
        <div className="card" style={{ marginBottom: 24 }}>
          <div style={{ fontWeight: 700, fontSize: 15, marginBottom: 16 }}>{t('goals.addAGoal')}</div>
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end' }}>
            <div>
              <label htmlFor="goal-metric" style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>{t('goals.metricLabel')}</label>
              <select
                id="goal-metric"
                className="filter-input"
                value={selectedType}
                onChange={e => { setSelectedType(e.target.value); setTarget('') }}
                style={{ minWidth: 210 }}
              >
                {availableTypes.map(tp => (
                  <option key={tp.value} value={tp.value}>{t(tp.labelKey)}</option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="goal-target" style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>
                {t('goals.targetLabel', { unit: GOAL_TYPES.find(tp => tp.value === selectedType)?.unit })}
              </label>
              <input
                id="goal-target"
                type="number"
                className="filter-input"
                placeholder={GOAL_TYPES.find(tp => tp.value === selectedType)?.placeholder}
                value={target}
                onChange={e => setTarget(e.target.value)}
                style={{ width: 130 }}
                min="1"
              />
            </div>
            <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
              {saving ? t('goals.saving') : t('goals.save')}
            </button>
            <button className="btn btn-ghost" onClick={() => { setShowAdd(false); setError('') }}>{t('goals.cancel')}</button>
          </div>
          {error && <Alert variant="error" style={{ fontSize: 13, marginTop: 8 }}>{error}</Alert>}
        </div>
      )}

      {goals.length === 0 && !showAdd ? (
        <div className="empty-state">
          <div className="empty-state-icon"><Target size={48} /></div>
          <h3>{t('goals.emptyTitle')}</h3>
          <p>{t('goals.emptyDesc')}</p>
          <button className="btn btn-primary" style={{ marginTop: 16 }} onClick={() => setShowAdd(true)}>
            <Plus size={13} /> {t('goals.addFirstGoal')}
          </button>
        </div>
      ) : (
        <div className="goals-grid">
          {goals.map(goal => {
            const meta = GOAL_TYPES.find(tp => tp.value === goal.goal_type)
            if (!meta) return null
            const { current, pct } = computeProgress(goal)
            const streak = computeStreak(goal)
            const pacing = computePacing(goal)
            const done = pct >= 100
            const dl = daysLeft(meta.period)
            const barColor = done
              ? 'var(--accent)'
              : pct > 66 ? 'var(--speed)'
              : pct > 33 ? 'var(--cadence)'
              : 'var(--text-muted)'

            return (
              <div key={goal.id} className="goal-card-v2">
                <div className="goal-card-header">
                  <div>
                    <div className="goal-card-period">{meta.period.toUpperCase()}</div>
                    <div className="goal-card-title">{t(meta.labelKey)}</div>
                  </div>
                  <button
                    className="btn btn-ghost"
                    style={{ padding: '4px 8px', opacity: 0.5 }}
                    aria-label={t('goals.deleteAriaLabel', { label: t(meta.labelKey) })}
                    onClick={() => handleDelete(goal.id)}
                  >
                    <Trash2 size={13} />
                  </button>
                </div>

                <div className="goal-card-values">
                  <span className="goal-card-current" style={{ color: done ? 'var(--accent)' : 'var(--text-primary)' }}>
                    {fmtVal(current, meta.unit)}
                  </span>
                  <span className="goal-card-target">
                    {' '}/ {fmtVal(goal.target, meta.unit)} {meta.unit}
                  </span>
                </div>

                <div className="goal-bar-wrap" style={{ marginBottom: 12 }}>
                  <div
                    className="goal-bar"
                    style={{ transform: `scaleX(${Math.min(1, pct / 100)})`, transformOrigin: 'left center', width: '100%', background: barColor, transition: 'transform 0.6s cubic-bezier(0.23, 1, 0.32, 1)' }}
                  />
                </div>

                <div className="goal-card-footer">
                  <span className="goal-pct" style={{ color: done ? 'var(--accent)' : 'var(--text-secondary)' }}>
                    {Math.round(pct)}%
                  </span>
                  <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                    {streak > 0 && (
                      <span className="goal-streak">
                        <Flame size={11} style={{ color: 'var(--heart)' }} />
                        {streak !== 1
                          ? t('goals.streakLabelPlural', { count: streak, periods: meta.period + 's' })
                          : t('goals.streakLabel', { count: streak, period: meta.period })}
                      </span>
                    )}
                    {!done && dl > 0 && (
                      <span className="goal-days-left">{t('goals.daysLeft', { count: dl })}</span>
                    )}
                    {done && (
                      <span style={{ fontSize: 11, color: 'var(--accent)', fontWeight: 700 }}>{t('goals.goalHit')}</span>
                    )}
                  </div>
                </div>

                {pacing && (
                  <div className="goal-pacing">
                    {pacing.delta >= 0 ? (
                      <>
                        <TrendingUp size={12} style={{ color: 'var(--accent)' }} />
                        <span style={{ color: 'var(--accent)' }}>{t('goals.onPaceFor', { pace: pacing.pace.toLocaleString(), unit: meta.unit })}</span>
                        <span style={{ color: 'var(--text-muted)' }}>{t('goals.ahead', { count: Math.abs(pacing.delta).toLocaleString() })}</span>
                      </>
                    ) : (
                      <>
                        <TrendingDown size={12} style={{ color: 'var(--heart)' }} />
                        <span style={{ color: 'var(--heart)' }}>{t('goals.onPaceFor', { pace: pacing.pace.toLocaleString(), unit: meta.unit })}</span>
                        <span style={{ color: 'var(--text-muted)' }}>{t('goals.behindPace', { count: Math.abs(pacing.delta).toLocaleString() })}</span>
                      </>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
