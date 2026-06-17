import { useEffect, useState, useId } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  getActivities, getFitnessStats, getWeeklyStats,
  getDashboardFitnessInsight, getHeatProfile, getDurabilityTrend,
  getTrainingLoadComparison,
} from '../services/api'
import {
  ComposedChart, Bar, Cell, LineChart, Line, ReferenceLine,
  XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from 'recharts'
import { format } from 'date-fns'
import { Route, Droplets, TrendingUp } from 'lucide-react'
import InfoTip from './InfoTip'

function fmtDuration(seconds) {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  return h > 0 ? `${h}h ${m}m` : `${m}m`
}

// Plain-language verdict for the current TSB (form) value. Returns a stable
// key (resolved against dashboard.form_status.* at render) plus its colour.
function formStatus(tsb) {
  if (tsb >= 15)  return { key: 'veryFresh',    color: 'var(--status-good)' }
  if (tsb >= 5)   return { key: 'fresh',        color: 'var(--status-good)' }
  if (tsb >= -10) return { key: 'balanced',     color: 'var(--text-secondary)' }
  if (tsb >= -25) return { key: 'building',     color: 'var(--status-warn)' }
  return            { key: 'overreaching', color: 'var(--status-critical)' }
}

function CtlSparkline({ data }) {
  const gradId = useId()
  if (!data || data.length < 2) return null
  const vals = data.map(d => d.ctl)
  const min = Math.min(...vals)
  const max = Math.max(...vals)
  const range = max - min || 1
  const W = 200, H = 44
  const pts = vals.map((v, i) => {
    const x = (i / (vals.length - 1)) * W
    const y = H - 4 - ((v - min) / range) * (H - 8)
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
  return (
    <svg width={W} height={H} style={{ display: 'block' }} aria-hidden="true">
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--speed)" stopOpacity="0.22" />
          <stop offset="100%" stopColor="var(--speed)" stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon points={`0,${H} ${pts} ${W},${H}`} fill={`url(#${gradId})`} />
      <polyline points={pts} fill="none" stroke="var(--speed)" strokeWidth={1.5} strokeOpacity={0.85} />
    </svg>
  )
}

const WeeklyTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  return (
    <div style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-bright)', borderRadius: 6, padding: '10px 14px', fontSize: 13 }}>
      <div style={{ color: 'var(--text-muted)', marginBottom: 4 }}>{label}</div>
      {payload.map(p => (
        <div key={p.dataKey} style={{ color: p.fill || p.color, fontFamily: 'var(--font-display)', fontSize: 16 }}>
          {p.value} <span style={{ fontSize: 11, opacity: 0.7 }}>{p.name}</span>
        </div>
      ))}
    </div>
  )
}


export default function Dashboard() {
  const { t } = useTranslation()
  const [recentRides, setRecentRides]       = useState(null)
  const [weeklyData, setWeeklyData]         = useState(null)
  const [fitnessData, setFitnessData]       = useState(null)
  const [fitnessInsight, setFitnessInsight] = useState(null) // null=loading, false=failed
  const [heatProfile, setHeatProfile]       = useState(null)
  const [durabilityTrend, setDurabilityTrend] = useState(null)
  const [loadComparison, setLoadComparison]   = useState(null)
  const [showCorrected,  setShowCorrected]    = useState(false)
  const navigate = useNavigate()

  useEffect(() => {
    getActivities({ limit: 7 }).then(r => setRecentRides(r.data)).catch(() => setRecentRides([]))
    getWeeklyStats(16).then(r => setWeeklyData(r.data)).catch(() => setWeeklyData([]))
    getFitnessStats(60).then(r => setFitnessData(r.data)).catch(() => setFitnessData([]))
    getHeatProfile().then(r => setHeatProfile(r.data)).catch(() => {})
    getDurabilityTrend(12).then(r => setDurabilityTrend(r.data)).catch(() => {})
    getTrainingLoadComparison(60).then(r => setLoadComparison(r.data)).catch(() => {})
  }, [])

  // Fitness insight: fires once fitnessData is loaded and has actual training data
  useEffect(() => {
    if (fitnessData === null) return
    if (!fitnessData.some(d => d.load > 0)) { setFitnessInsight(false); return }

    const current  = fitnessData[fitnessData.length - 1]
    const sevenAgo = fitnessData.length >= 8 ? fitnessData[fitnessData.length - 8] : null

    getDashboardFitnessInsight({
      ctl: current.ctl,
      atl: current.atl,
      tsb: current.tsb,
      ctl_7d_ago: sevenAgo?.ctl ?? null,
      atl_7d_ago: sevenAgo?.atl ?? null,
    })
      .then(r => setFitnessInsight(r.data.insight))
      .catch(() => setFitnessInsight(false))
  }, [fitnessData])

  // Derived values
  const lastRide       = recentRides?.[0] ?? null
  const earlierRides   = recentRides?.slice(1) ?? []
  const currentWeek    = weeklyData?.length ? weeklyData[weeklyData.length - 1] : null
  const lastWeek       = weeklyData?.length >= 2 ? weeklyData[weeklyData.length - 2] : null
  const currentFitness = fitnessData?.length ? fitnessData[fitnessData.length - 1] : null
  const fitnessHistory = fitnessData?.slice(-42) ?? []

  const weekDeltaPct = currentWeek && lastWeek && lastWeek.distance_km > 0
    ? Math.round(((currentWeek.distance_km - lastWeek.distance_km) / lastWeek.distance_km) * 100)
    : null

  const ctlTrend = fitnessData?.length >= 8
    ? Math.sign(currentFitness.ctl - fitnessData[fitnessData.length - 8].ctl)
    : 0
  const atlTrend = fitnessData?.length >= 8
    ? Math.sign(currentFitness.atl - fitnessData[fitnessData.length - 8].atl)
    : 0
  const tsbTrend = fitnessData?.length >= 8
    ? Math.sign(currentFitness.tsb - fitnessData[fitnessData.length - 8].tsb)
    : 0

  // Indoor-corrected display values for the status hero
  const corrected = showCorrected && loadComparison?.corrected ? loadComparison.corrected : null
  const dispCtl = currentFitness ? (corrected ? Math.round(corrected.ctl ?? currentFitness.ctl) : currentFitness.ctl) : null
  const dispAtl = currentFitness ? (corrected ? Math.round(corrected.atl ?? currentFitness.atl) : currentFitness.atl) : null
  const dispTsb = currentFitness ? (corrected ? Math.round(corrected.tsb ?? currentFitness.tsb) : currentFitness.tsb) : null
  const deltaCtl = corrected && loadComparison.difference?.ctl_delta != null ? Math.round(loadComparison.difference.ctl_delta) : null
  const deltaAtl = corrected && loadComparison.difference?.atl_delta != null ? Math.round(loadComparison.difference.atl_delta) : null
  const status = dispTsb != null ? formStatus(dispTsb) : null
  const statusWord = status ? t(`dashboard.form_status.${status.key}`) : null
  const statusDesc = status ? t(`dashboard.form_status.${status.key}Desc`) : null

  const currentWeekKey = weeklyData?.length ? weeklyData[weeklyData.length - 1].week : null
  const weeklyDisplay  = weeklyData
    ? weeklyData
        .filter(w => w.distance_km > 0 || w.week === currentWeekKey)
        .slice(-12)
        .map(w => ({ ...w, label: w.week.slice(5) }))
    : []
  const hasWeeklyData  = weeklyDisplay.some(w => w.distance_km > 0)
  const hasTSSData     = weeklyDisplay.some(w => (w.tss ?? 0) > 0)
  const hasFitnessData = fitnessData?.some(d => d.load > 0)

  // Empty state
  if (recentRides !== null && recentRides.length === 0) {
    return (
      <div>
        <div className="page-header">
          <h1 className="page-title">{t('dashboard.title')}</h1>
        </div>
        <div className="empty-state">
          <div className="empty-state-icon"><Route size={48} /></div>
          <h3>{t('dashboard.emptyTitle')}</h3>
          <p>{t('dashboard.emptyDesc')}</p>
        </div>
      </div>
    )
  }

  // Fade panels while their data loads — surface styling lives in .panel
  const loadingStyle = (loading) => ({
    opacity: loading ? 0.4 : 1,
    transition: 'opacity 0.2s',
  })

  const statLabelStyle = {
    fontSize: 11,
    fontWeight: 600,
    textTransform: 'uppercase',
    letterSpacing: '0.08em',
    color: 'var(--text-muted)',
    marginBottom: 6,
  }

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">{t('dashboard.title')}</h1>
      </div>

      {/* ── 1. Training Status: how ready am I today? ─────────────────────── */}
      <div className="panel" style={{ ...loadingStyle(!fitnessData), marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 18 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <span className="panel-title" style={{ marginBottom: 0 }}>{t('dashboard.trainingStatus')}</span>
            <InfoTip text={t('dashboard.trainingStatusTip')} />
          </div>
          {loadComparison && (
            <button
              onClick={() => setShowCorrected(v => !v)}
              aria-label={t('dashboard.toggleCorrectedAria')}
              aria-pressed={showCorrected}
              style={{
                fontSize: 10, fontWeight: 600, padding: '3px 8px', borderRadius: 5, cursor: 'pointer',
                border: `1px solid ${showCorrected ? 'color-mix(in srgb, var(--accent) 30%, transparent)' : 'var(--border)'}`,
                background: showCorrected ? 'color-mix(in srgb, var(--accent) 10%, transparent)' : 'transparent',
                color: showCorrected ? 'var(--accent)' : 'var(--text-muted)',
                transition: 'border-color 150ms, background 150ms, color 150ms',
              }}
            >
              {showCorrected ? t('dashboard.corrected') : t('dashboard.indoorCorrection')}
            </button>
          )}
        </div>

        {currentFitness && hasFitnessData ? (
          <div className="readiness-grid">
            {/* Verdict in plain language */}
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
                <span aria-hidden="true" style={{ width: 9, height: 9, borderRadius: '50%', background: status.color, flexShrink: 0 }} />
                <span style={{ fontFamily: 'var(--font-display)', fontSize: 26, fontWeight: 700, lineHeight: 1, color: status.color, transition: 'color 200ms ease' }}>
                  {statusWord}
                </span>
              </div>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.55, maxWidth: '42ch' }}>
                {fitnessInsight === null
                  ? <span style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>{t('dashboard.analyzing')}</span>
                  : (fitnessInsight || statusDesc)}
              </div>
            </div>

            {/* The three numbers behind the verdict */}
            <div style={{ display: 'flex', gap: 32 }}>
              {[
                { name: t('dashboard.fitness'), abbr: 'CTL', value: dispCtl, color: 'var(--text-primary)', trend: ctlTrend, delta: deltaCtl },
                { name: t('dashboard.fatigue'), abbr: 'ATL', value: dispAtl, color: 'var(--text-primary)', trend: atlTrend, delta: deltaAtl },
                { name: t('dashboard.form'),    abbr: 'TSB', value: dispTsb > 0 ? `+${dispTsb}` : dispTsb, color: status.color, trend: tsbTrend, delta: null },
              ].map(({ name, abbr, value, color, trend, delta }) => (
                <div key={abbr}>
                  <div style={statLabelStyle}>{name}</div>
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: 3, lineHeight: 1 }}>
                    <span className="stat-value" style={{ fontSize: 26, color, transition: 'color 200ms ease' }}>
                      {value}
                    </span>
                    {trend !== 0 && !delta && (
                      <span style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1 }}>
                        {trend > 0 ? '↑' : '↓'}
                      </span>
                    )}
                    {delta != null && delta !== 0 && (
                      <span style={{ fontSize: 10, color: delta > 0 ? 'var(--accent)' : 'var(--text-muted)', lineHeight: 1 }}>
                        {delta > 0 ? `+${delta}` : delta}
                      </span>
                    )}
                  </div>
                  <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 5, letterSpacing: '0.06em' }}>{abbr}</div>
                </div>
              ))}
            </div>

            {/* Where fitness is heading */}
            {fitnessHistory.length >= 7 && (
              <div>
                <div style={{ ...statLabelStyle, marginBottom: 8 }}>{t('dashboard.fitness6weeks')}</div>
                <CtlSparkline data={fitnessHistory} />
              </div>
            )}
          </div>
        ) : hasFitnessData === false && fitnessData !== null ? (
          <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            {t('dashboard.uploadToTrack')}
          </div>
        ) : null}
      </div>

      {/* ── 2. Training volume: am I riding enough? ───────────────────────── */}
      <div className={hasWeeklyData ? 'dash-row dash-row-week' : 'dash-row'}>

        {/* This Week */}
        <div className="panel" style={loadingStyle(!weeklyData)}>
          <div className="panel-title">{t('dashboard.thisWeek')}</div>
          {currentWeek && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '18px 24px' }}>
              {[
                { label: t('common.rides'),     value: currentWeek.rides,                                                 unit: null },
                { label: t('common.distance'),  value: currentWeek.distance_km > 0 ? currentWeek.distance_km.toFixed(1) : '—', unit: currentWeek.distance_km > 0 ? 'km' : null },
                { label: t('common.time'),      value: currentWeek.duration_seconds > 0 ? fmtDuration(currentWeek.duration_seconds) : '—', unit: null },
                { label: t('common.elevation'), value: currentWeek.elevation_m > 0 ? Math.round(currentWeek.elevation_m).toLocaleString() : '—', unit: currentWeek.elevation_m > 0 ? 'm' : null },
              ].map(({ label, value, unit }) => (
                <div key={label}>
                  <div style={statLabelStyle}>{label}</div>
                  <div className="stat-value" style={{ fontSize: 24 }}>
                    {value}
                    {unit && <span style={{ fontSize: 13, fontWeight: 400, color: 'var(--text-muted)', marginLeft: 4 }}>{unit}</span>}
                  </div>
                </div>
              ))}
            </div>
          )}
          {weekDeltaPct !== null && currentWeek?.rides > 0 && (
            <div style={{
              marginTop: 16,
              fontSize: 12,
              color: weekDeltaPct > 0 ? 'var(--accent)' : weekDeltaPct < 0 ? 'var(--heart)' : 'var(--text-muted)',
              display: 'flex',
              alignItems: 'center',
              gap: 4,
            }}>
              {weekDeltaPct > 0 ? '↑' : weekDeltaPct < 0 ? '↓' : '→'}
              {' '}{t('dashboard.distanceVsLastWeek', { pct: `${weekDeltaPct > 0 ? '+' : ''}${weekDeltaPct}` })}
            </div>
          )}
          {currentWeek?.rides === 0 && (
            <div style={{ marginTop: 16, fontSize: 12, color: 'var(--text-muted)' }}>{t('dashboard.noRidesThisWeek')}</div>
          )}
        </div>

        {/* Weekly Load — distance bars + stress line */}
        {hasWeeklyData && (
          <div className="chart-section" style={{ marginBottom: 0 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <div className="chart-title" style={{ marginBottom: 0 }}>
                {t('dashboard.weeklyLoad')}{' '}
                <InfoTip text={t('dashboard.weeklyLoadTip')} />
              </div>
              <div style={{ display: 'flex', gap: 14, alignItems: 'center' }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: 'var(--text-muted)' }}>
                  <span style={{ width: 8, height: 8, borderRadius: 2, background: 'oklch(65% 0.2 142)', display: 'inline-block', flexShrink: 0 }} />
                  {t('dashboard.legendDistance')}
                </span>
                {hasTSSData && (
                  <span style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: 'var(--text-muted)' }}>
                    <span style={{ width: 14, height: 2, background: 'var(--heart)', display: 'inline-block', flexShrink: 0 }} />
                    {t('dashboard.legendStress')}
                  </span>
                )}
              </div>
            </div>
            <ResponsiveContainer width="100%" height={200}>
              <ComposedChart data={weeklyDisplay} barCategoryGap="32%">
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                <XAxis dataKey="label" tick={{ fill: 'var(--text-muted)', fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis yAxisId="km" tick={{ fill: 'var(--text-muted)', fontSize: 11 }} axisLine={false} tickLine={false} unit=" km" />
                {hasTSSData && (
                  <YAxis yAxisId="ss" orientation="right" tick={{ fill: 'var(--text-muted)', fontSize: 11 }} axisLine={false} tickLine={false} />
                )}
                <Tooltip content={<WeeklyTooltip />} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
                <Bar yAxisId="km" dataKey="distance_km" fill="oklch(65% 0.2 142)" radius={[3, 3, 0, 0]} name="km">
                  {weeklyDisplay.map(w => (
                    <Cell key={w.week} fill={w.week === currentWeekKey ? 'var(--accent)' : 'oklch(65% 0.2 142)'} />
                  ))}
                </Bar>
                {hasTSSData && (
                  <Line
                    yAxisId="ss"
                    type="monotone"
                    dataKey="tss"
                    stroke="var(--heart)"
                    strokeWidth={2}
                    strokeOpacity={0.75}
                    dot={{ r: 2.5, fill: 'var(--heart)', strokeWidth: 0 }}
                    activeDot={{ r: 4 }}
                    name="TSS"
                  />
                )}
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* ── 3. Rides: what have I done? ───────────────────────────────────── */}
      {lastRide && (() => {
        const metrics = [
          { key: 'distance',  label: t('common.distance'),  value: lastRide.distance_km.toFixed(1),                   unit: 'km'   },
          { key: 'time',      label: t('common.time'),       value: fmtDuration(lastRide.duration_seconds),            unit: null   },
          ...(lastRide.elevation_gain_m != null
            ? [{ key: 'elevation', label: t('common.elevation'), value: Math.round(lastRide.elevation_gain_m).toLocaleString(), unit: 'm' }]
            : []),
          { key: 'speed',     label: t('common.avgSpeed'),  value: lastRide.avg_speed_kmh?.toFixed(1),               unit: 'km/h' },
          ...(lastRide.avg_heart_rate_bpm
            ? [{ key: 'heart_rate', label: t('common.avgHr'), value: `${Math.round(lastRide.avg_heart_rate_bpm)}`,  unit: 'bpm'  }]
            : []),
        ]

        return (
          <div
            className="last-ride-strip"
            style={{ marginBottom: 16 }}
            onClick={() => navigate(`/activities/${lastRide.id}`)}
            onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); navigate(`/activities/${lastRide.id}`) } }}
            tabIndex={0}
            role="button"
            aria-label={t('dashboard.lastRideAria', { name: lastRide.name })}
          >
            {/* Identity */}
            <div className="lrs-identity">
              <div className="lrs-section-label">{t('dashboard.lastRide')}</div>
              <div className="lrs-name">{lastRide.name}</div>
              <div className="lrs-date">{format(new Date(lastRide.date.slice(0, 10) + 'T12:00:00'), 'EEE d MMM yyyy')}</div>
            </div>

            <div className="lrs-divider" aria-hidden="true" />

            {/* Metrics */}
            <div className="lrs-metrics">
              {metrics.map(({ key, label, value, unit }) => (
                <div key={key} className="lrs-metric">
                  <div className="lrs-metric-label">{label}</div>
                  <div className={`lrs-metric-value${key === 'distance' ? ' lrs-accent' : ''}`}>
                    {value}
                    {unit && <span className="lrs-metric-unit">{unit}</span>}
                  </div>
                </div>
              ))}
            </div>

            {/* TSS · IF */}
            {(lastRide.tss != null || lastRide.intensity_factor != null) && (
              <>
                <div className="lrs-divider" aria-hidden="true" />
                <div className="lrs-delta">
                  {lastRide.tss != null && (
                    <div className="lrs-metric">
                      <div className="lrs-metric-label">{t('dashboard.stress')}</div>
                      <div className="lrs-metric-value">{Math.round(lastRide.tss)}</div>
                    </div>
                  )}
                  {lastRide.intensity_factor != null && (
                    <div className="lrs-metric">
                      <div className="lrs-metric-label">{t('dashboard.intensity')}</div>
                      <div className="lrs-metric-value">{lastRide.intensity_factor.toFixed(2)}</div>
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        )
      })()}

      {/* Earlier rides — last ride lives in the strip above, so skip it here */}
      {earlierRides.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <div className="panel-title" style={{ marginBottom: 10 }}>
            {t('dashboard.earlierRides')}
          </div>
          <div className="recent-rides-list" role="list">
            <div className="rrl-head" aria-hidden="true">
              <span className="rrl-name">{t('common.ride')}</span>
              <span className="rrl-date">{t('common.date')}</span>
              <span className="rrl-stat">{t('common.distance')}</span>
              <span className="rrl-stat">{t('common.time')}</span>
              <span className="rrl-stat">{t('common.avgSpeed')}</span>
            </div>
            {earlierRides.map(a => (
              <div
                key={a.id}
                className="rrl-row"
                role="button"
                tabIndex={0}
                aria-label={t('dashboard.earlierRideAria', { name: a.name, date: format(new Date(a.date.slice(0, 10) + 'T12:00:00'), 'd MMM'), distance: a.distance_km.toFixed(1) })}
                onClick={() => navigate(`/activities/${a.id}`)}
                onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); navigate(`/activities/${a.id}`) } }}
              >
                <span className="rrl-name">{a.name}</span>
                <span className="rrl-date">{format(new Date(a.date.slice(0, 10) + 'T12:00:00'), 'd MMM')}</span>
                <span className="rrl-stat">{a.distance_km.toFixed(1)} km</span>
                <span className="rrl-stat">{fmtDuration(a.duration_seconds)}</span>
                <span className="rrl-stat">{a.avg_speed_kmh?.toFixed(1)} km/h</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── 4. Long-term signals ──────────────────────────────────────────── */}
      {(durabilityTrend?.current_avg != null || heatProfile) && (
        <div className={durabilityTrend?.current_avg != null && heatProfile ? 'dash-row dash-row-trends' : 'dash-row'}>

          {/* Durability Trend */}
          {durabilityTrend && durabilityTrend.current_avg != null && (
            <div className="chart-section" style={{ marginBottom: 0 }}>
              {/* Header row: title + summary numbers */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <TrendingUp size={14} style={{ color: 'var(--accent)' }} />
                  <span className="chart-title" style={{ marginBottom: 0 }}>
                    {t('dashboard.durability')}
                  </span>
                  <InfoTip text={t('dashboard.durabilityTip')} />
                </div>
                <div style={{ display: 'flex', gap: 20, alignItems: 'flex-start' }}>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 2 }}>{t('dashboard.currentAvg')}</div>
                    <div style={{ display: 'flex', alignItems: 'baseline', gap: 4, justifyContent: 'flex-end' }}>
                      <span className="stat-value" style={{ fontSize: 22, color: durabilityTrend.trend === 'improving' ? 'var(--status-good)' : durabilityTrend.trend === 'declining' ? 'var(--status-critical)' : 'var(--text-primary)' }}>
                        {durabilityTrend.current_avg.toFixed(1)}
                      </span>
                      <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>
                        {durabilityTrend.trend === 'improving' ? '↑' : durabilityTrend.trend === 'declining' ? '↓' : '→'}
                      </span>
                    </div>
                    <div style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'capitalize' }}>{durabilityTrend.trend}</div>
                  </div>
                  {durabilityTrend.best_ever != null && (
                    <div style={{ textAlign: 'right' }}>
                      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 2 }}>{t('dashboard.bestEver')}</div>
                      <div className="stat-value" style={{ fontSize: 22, color: 'var(--accent)' }}>
                        {durabilityTrend.best_ever.toFixed(1)}
                      </div>
                      {durabilityTrend.best_ever_date && (
                        <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>{durabilityTrend.best_ever_date}</div>
                      )}
                    </div>
                  )}
                </div>
              </div>

              {/* Weekly trend line chart */}
              {durabilityTrend.weekly_averages.length >= 2 && (
                <>
                  {/* Reference line legend */}
                  <div style={{ display: 'flex', gap: 14, marginBottom: 8 }}>
                    {[
                      { label: t('dashboard.diExcellent'), y: 95, color: '#6dffb8' },
                      { label: t('dashboard.diGood'),      y: 88, color: '#4da6ff' },
                      { label: t('dashboard.diModerate'),  y: 80, color: '#ffd93d' },
                    ].map(({ label, y, color }) => (
                      <span key={label} style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: 'var(--text-muted)' }}>
                        <span style={{ width: 16, height: 1, borderTop: `1px dashed ${color}`, display: 'inline-block', flexShrink: 0 }} />
                        {label} ({y})
                      </span>
                    ))}
                  </div>
                  <ResponsiveContainer width="100%" height={180}>
                    <LineChart data={durabilityTrend.weekly_averages} margin={{ top: 4, right: 8, bottom: 0, left: -10 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                      <XAxis
                        dataKey="week"
                        tick={{ fill: 'var(--text-muted)', fontSize: 10 }}
                        axisLine={false}
                        tickLine={false}
                        tickFormatter={w => w.slice(5)}
                      />
                      <YAxis
                        domain={[60, 105]}
                        tick={{ fill: 'var(--text-muted)', fontSize: 11 }}
                        axisLine={false}
                        tickLine={false}
                        width={32}
                      />
                      <Tooltip
                        content={({ active, payload, label }) => active && payload?.length ? (
                          <div style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-bright)', borderRadius: 6, padding: '6px 10px', fontSize: 12 }}>
                            <div style={{ color: 'var(--text-muted)', marginBottom: 3 }}>{label}</div>
                            <div style={{ fontFamily: 'var(--font-display)', fontSize: 16, color: 'var(--accent)' }}>
                              {payload[0].value?.toFixed(1)}
                              <span style={{ fontSize: 11, color: 'var(--text-muted)', marginLeft: 4 }}>{t('dashboard.diRides', { count: payload[0].payload.ride_count })}</span>
                            </div>
                          </div>
                        ) : null}
                      />
                      <ReferenceLine y={95} stroke="#6dffb8" strokeDasharray="4 3" strokeOpacity={0.5} />
                      <ReferenceLine y={88} stroke="#4da6ff" strokeDasharray="4 3" strokeOpacity={0.5} />
                      <ReferenceLine y={80} stroke="#ffd93d" strokeDasharray="4 3" strokeOpacity={0.5} />
                      <Line
                        type="monotone"
                        dataKey="avg_durability"
                        stroke="var(--accent)"
                        strokeWidth={2}
                        dot={{ r: 3, fill: 'var(--accent)', strokeWidth: 0 }}
                        activeDot={{ r: 5 }}
                        connectNulls
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </>
              )}
            </div>
          )}

          {/* Heat Readiness */}
          {heatProfile && (
            <div className="panel">
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
                <Droplets size={14} style={{ color: 'var(--text-secondary)' }} />
                <span className="panel-title" style={{ marginBottom: 0 }}>{t('dashboard.heatReadiness')}</span>
                <InfoTip text={t('dashboard.heatReadinessTip')} />
              </div>
              {[
                {
                  label: t('dashboard.adaptation'),
                  value: heatProfile.heat_adaptation_level
                    ? heatProfile.heat_adaptation_level.charAt(0).toUpperCase() + heatProfile.heat_adaptation_level.slice(1)
                    : t('dashboard.adaptationLow'),
                  color: heatProfile.heat_adaptation_level === 'high' ? 'var(--status-good)' : heatProfile.heat_adaptation_level === 'moderate' ? 'var(--status-warn)' : 'var(--text-muted)',
                  sub: t('dashboard.hotRides', { count: heatProfile.heat_rides_last_14d }),
                  link: null,
                },
                {
                  label: t('dashboard.sweatRate'),
                  value: heatProfile.has_calibrated_rate ? `${Math.round(heatProfile.sweat_rate_ml_per_hour)} ml/h` : '—',
                  color: heatProfile.has_calibrated_rate ? 'var(--text-primary)' : 'var(--text-muted)',
                  sub: heatProfile.has_calibrated_rate ? t('dashboard.personalMeasurement') : null,
                  link: !heatProfile.has_calibrated_rate ? { to: '/settings', label: t('dashboard.calibrateInSettings') } : null,
                },
              ].map(({ label, value, color, sub, link }, i, arr) => (
                <div key={label} style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '9px 0',
                  borderBottom: i < arr.length - 1 ? '1px solid var(--border)' : 'none',
                }}>
                  <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{label}</span>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontFamily: 'var(--font-display)', fontSize: 16, fontWeight: 600, color }}>{value}</div>
                    {sub && <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{sub}</div>}
                    {link && <Link to={link.to} style={{ fontSize: 11, color: 'var(--accent)', textDecoration: 'none' }}>{link.label}</Link>}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
