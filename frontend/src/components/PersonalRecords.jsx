import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getRecords } from '../services/api'
import { format, formatDistanceToNow } from 'date-fns'
import { Trophy, ArrowRight, TrendingUp, RefreshCw } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import Alert from './Alert'

const SPEED_PRS = [
  { type: 'fastest_400m',  label: '400 m',  distKm: 0.4  },
  { type: 'fastest_1km',   label: '1 km',   distKm: 1    },
  { type: 'fastest_5km',   label: '5 km',   distKm: 5    },
  { type: 'fastest_10km',  label: '10 km',  distKm: 10   },
  { type: 'fastest_20km',  label: '20 km',  distKm: 20   },
  { type: 'fastest_40km',  label: '40 km',  distKm: 40   },
]

function fmtTime(seconds) {
  const s = Math.round(seconds)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
  return `${m}:${String(sec).padStart(2, '0')}`
}

function avgSpeed(distKm, seconds) {
  return (distKm / (seconds / 3600)).toFixed(1)
}

export default function PersonalRecords() {
  const { t } = useTranslation()
  const [records, setRecords] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [retryKey, setRetryKey] = useState(0)
  const navigate = useNavigate()

  const BEST_PRS = [
    { type: 'longest_ride',   label: t('personalRecords.prLabelLongestRide'),   unit: 'km',   fmt: v => `${v.toFixed(1)} km`,   color: 'var(--speed)'   },
    { type: 'best_avg_speed', label: t('personalRecords.prLabelBestAvgSpeed'),  unit: 'km/h', fmt: v => `${v.toFixed(1)} km/h`, color: 'var(--cadence)' },
    { type: 'most_elevation', label: t('personalRecords.prLabelMostElevation'), unit: 'm',    fmt: v => `${Math.round(v).toLocaleString()} m`, color: 'var(--accent)' },
  ]

  useEffect(() => {
    setLoading(true)
    setError(null)
    getRecords()
      .then(r => setRecords(r.data))
      .catch(e => { console.error(e); setError(e) })
      .finally(() => setLoading(false))
  }, [retryKey])

  if (loading) return <div className="loading-center"><div className="spinner" /></div>
  if (error) return (
    <div className="empty-state">
      <Alert variant="error" style={{ marginBottom: 16 }}>{t('common.errorLoad')}</Alert>
      <button className="btn btn-ghost" onClick={() => setRetryKey(k => k + 1)}>
        <RefreshCw size={14} /> {t('common.retry')}
      </button>
    </div>
  )

  const byType = Object.fromEntries(records.map(r => [r.pr_type, r]))

  // Compute speeds for all set time PRs to find the max (for bar scaling)
  const speeds = SPEED_PRS
    .map(p => byType[p.type] ? parseFloat(avgSpeed(p.distKm, byType[p.type].value)) : 0)
  const maxSpeed = Math.max(...speeds, 1)

  const hasAny = records.length > 0
  const hasSpeedPRs = SPEED_PRS.some(p => byType[p.type])
  const hasBestPRs = BEST_PRS.some(p => byType[p.type])

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">
          <Trophy size={22} style={{ display: 'inline', marginRight: 8, color: 'var(--accent)' }} />
          {t('personalRecords.title')}
        </h1>
        <p className="page-subtitle">{t('personalRecords.subtitle')}</p>
      </div>

      {!hasAny ? (
        <div className="empty-state">
          <div className="empty-state-icon"><Trophy size={48} /></div>
          <h3>{t('personalRecords.noRecordsTitle')}</h3>
          <p>{t('personalRecords.noRecordsBody')}</p>
        </div>
      ) : (
        <>
          {/* ── Speed Curve ──────────────────────────────────────────── */}
          {hasSpeedPRs && (
            <div className="card" style={{ marginBottom: 28, padding: 0, overflow: 'hidden' }}>
              <div style={{ padding: '18px 22px 14px', borderBottom: '1px solid var(--border)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <TrendingUp size={15} style={{ color: 'var(--accent)' }} />
                  <span style={{ fontWeight: 700, fontSize: 13, letterSpacing: '0.04em', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>
                    {t('personalRecords.speedCurveLabel')}
                  </span>
                  <span style={{ fontSize: 12, color: 'var(--text-muted)', marginLeft: 4 }}>
                    {t('personalRecords.speedCurveDescription')}
                  </span>
                </div>
              </div>

              <div>
                {SPEED_PRS.map((p, i) => {
                  const pr = byType[p.type]
                  const speed = pr ? parseFloat(avgSpeed(p.distKm, pr.value)) : 0
                  const barPct = pr ? (speed / maxSpeed) * 100 : 0
                  const isLast = i === SPEED_PRS.length - 1

                  return (
                    <div
                      key={p.type}
                      className="pr-speed-row"
                      style={{
                        borderBottom: isLast ? 'none' : '1px solid var(--border)',
                        cursor: pr?.activity_id ? 'pointer' : 'default',
                        opacity: pr ? 1 : 0.4,
                        transition: 'opacity 200ms cubic-bezier(0.23, 1, 0.32, 1)',
                      }}
                      onClick={() => pr?.activity_id && navigate(`/activities/${pr.activity_id}`)}
                      tabIndex={pr?.activity_id ? 0 : undefined}
                      role={pr?.activity_id ? 'button' : undefined}
                      aria-label={pr?.activity_id ? t('personalRecords.speedPrAriaLabel', { label: p.label, time: fmtTime(pr.value), speed }) : undefined}
                      onKeyDown={e => { if (pr?.activity_id && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); navigate(`/activities/${pr.activity_id}`) } }}
                    >
                      {/* Distance label */}
                      <div className="pr-speed-dist">{p.label}</div>

                      {/* Time */}
                      <div className="pr-speed-time">
                        {pr ? fmtTime(pr.value) : '—'}
                      </div>

                      {/* Bar */}
                      <div className="pr-speed-bar-wrap">
                        {pr && (
                          <div
                            className="pr-speed-bar"
                            style={{ transform: `scaleX(${barPct / 100})`, transformOrigin: 'left center', width: '100%' }}
                          />
                        )}
                        {!pr && (
                          <div style={{ fontSize: 11, color: 'var(--text-muted)', fontStyle: 'italic' }}>
                            {t('personalRecords.notSetYet')}
                          </div>
                        )}
                      </div>

                      {/* Speed */}
                      <div className="pr-speed-kmh">
                        {pr ? <><span style={{ color: 'var(--accent)', fontWeight: 600 }}>{speed}</span> km/h</> : ''}
                      </div>

                      {/* Meta */}
                      {pr && (
                        <div className="pr-speed-meta">
                          <span>{format(new Date(pr.set_at), 'dd MMM yyyy')}</span>
                          {pr.activity_name && (
                            <span style={{ color: 'var(--text-secondary)' }}>
                              · {pr.activity_name}
                              <ArrowRight size={11} style={{ marginLeft: 3, verticalAlign: 'middle' }} />
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* ── All-time Bests ───────────────────────────────────────── */}
          {hasBestPRs && (
            <>
              <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 14 }}>
                {t('personalRecords.allTimeBests')}
              </div>
              <div className="pr-bests-grid">
                {BEST_PRS.map(meta => {
                  const pr = byType[meta.type]
                  if (!pr) return null
                  return (
                    <div
                      key={meta.type}
                      className="pr-best-card"
                      onClick={() => pr.activity_id && navigate(`/activities/${pr.activity_id}`)}
                      style={{ cursor: pr.activity_id ? 'pointer' : 'default' }}
                      tabIndex={pr.activity_id ? 0 : undefined}
                      role={pr.activity_id ? 'button' : undefined}
                      aria-label={pr.activity_id
                        ? (pr.activity_name
                          ? t('personalRecords.bestPrAriaLabelWithActivity', { label: meta.label, value: meta.fmt(pr.value), activity: pr.activity_name })
                          : t('personalRecords.bestPrAriaLabel', { label: meta.label, value: meta.fmt(pr.value) }))
                        : undefined}
                      onKeyDown={e => { if (pr.activity_id && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); navigate(`/activities/${pr.activity_id}`) } }}
                    >
                      <div className="pr-best-label">{meta.label}</div>
                      <div className="pr-best-value" style={{ color: meta.color }}>
                        {meta.fmt(pr.value)}
                      </div>
                      {pr.activity_name && (
                        <div className="pr-best-activity">
                          {pr.activity_name}
                          {pr.activity_id && <ArrowRight size={11} style={{ marginLeft: 4, verticalAlign: 'middle', opacity: 0.5 }} />}
                        </div>
                      )}
                      <div className="pr-best-date">
                        {format(new Date(pr.set_at), 'dd MMM yyyy')}
                        <span style={{ marginLeft: 6, opacity: 0.6 }}>
                          · {formatDistanceToNow(new Date(pr.set_at), { addSuffix: true })}
                        </span>
                      </div>
                    </div>
                  )
                })}
              </div>
            </>
          )}
        </>
      )}
    </div>
  )
}
