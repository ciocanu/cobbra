import { useEffect, useState, useId } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { getDashboardFitnessInsight } from '../services/api'
import {
  useActivities, useFitnessStats, useWeeklyStats,
  useHeatProfile, useDurabilityTrend, useTrainingLoadComparison,
} from '../services/queries'
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

// Plain-language verdict for the current TSB (form) value
function formStatus(tsb) {
  if (tsb >= 15) return {
    word: 'Very Fresh',
    color: 'var(--status-good)',
    desc: 'Fully recovered — ideal for a big effort, but fitness fades if you coast here too long.',
  }
  if (tsb >= 5) return {
    word: 'Fresh',
    color: 'var(--status-good)',
    desc: 'Recovered and ready. Good day to go hard.',
  }
  if (tsb >= -10) return {
    word: 'Balanced',
    color: 'var(--text-secondary)',
    desc: 'Normal training balance. Keep riding as planned.',
  }
  if (tsb >= -25) return {
    word: 'Building',
    color: 'var(--status-warn)',
    desc: 'Carrying fatigue — productive overload, but keep an eye on recovery.',
  }
  return {
    word: 'Overreaching',
    color: 'var(--status-critical)',
    desc: 'Heavy fatigue. An easy spin or rest day will help more than another hard ride.',
  }
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
  // Preserve the old null-vs-loaded sentinels the render logic depends on:
  // queries that fell back to [] on error map undefined→null while pending and
  // []→on-error; optional panels (heat/durability/load) stay null until loaded.
  const recentRidesQuery = useActivities({ limit: 7 })
  const weeklyQuery      = useWeeklyStats(16)
  const fitnessQuery     = useFitnessStats(60)
  const heatProfileQuery = useHeatProfile()
  const durabilityQuery  = useDurabilityTrend(12)
  const loadComparisonQuery = useTrainingLoadComparison(60)

  const recentRides    = recentRidesQuery.isError ? [] : (recentRidesQuery.data ?? null)
  const weeklyData     = weeklyQuery.isError ? [] : (weeklyQuery.data ?? null)
  const fitnessData    = fitnessQuery.isError ? [] : (fitnessQuery.data ?? null)
  const heatProfile    = heatProfileQuery.data ?? null
  const durabilityTrend = durabilityQuery.data ?? null
  const loadComparison = loadComparisonQuery.data ?? null

  const [fitnessInsight, setFitnessInsight] = useState(null) // null=loading, false=failed
  const [showCorrected,  setShowCorrected]    = useState(false)
  const navigate = useNavigate()

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
    // fitnessQuery.data is referentially stable on success; isError covers the
    // error path (data stays undefined → derived []), matching the old behavior.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fitnessQuery.data, fitnessQuery.isError])

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
          <h1 className="page-title">Dashboard</h1>
        </div>
        <div className="empty-state">
          <div className="empty-state-icon"><Route size={48} /></div>
          <h3>No rides yet</h3>
          <p>Upload your first .gpx or .fit file to get started</p>
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
        <h1 className="page-title">Dashboard</h1>
      </div>

      {/* ── 1. Training Status: how ready am I today? ─────────────────────── */}
      <div className="panel" style={{ ...loadingStyle(!fitnessData), marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 18 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <span className="panel-title" style={{ marginBottom: 0 }}>Training Status</span>
            <InfoTip text="Fitness (CTL) = 42-day rolling training load. Fatigue (ATL) = 7-day load. Form (TSB) = Fitness − Fatigue. Positive form = fresh and ready. Negative = carrying training fatigue." />
          </div>
          {loadComparison && (
            <button
              onClick={() => setShowCorrected(v => !v)}
              aria-label="Toggle indoor-corrected TSS values"
              aria-pressed={showCorrected}
              style={{
                fontSize: 10, fontWeight: 600, padding: '3px 8px', borderRadius: 5, cursor: 'pointer',
                border: `1px solid ${showCorrected ? 'color-mix(in srgb, var(--accent) 30%, transparent)' : 'var(--border)'}`,
                background: showCorrected ? 'color-mix(in srgb, var(--accent) 10%, transparent)' : 'transparent',
                color: showCorrected ? 'var(--accent)' : 'var(--text-muted)',
                transition: 'border-color 150ms, background 150ms, color 150ms',
              }}
            >
              {showCorrected ? '🏠 Corrected' : 'Indoor correction'}
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
                  {status.word}
                </span>
              </div>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.55, maxWidth: '42ch' }}>
                {fitnessInsight === null
                  ? <span style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>Analyzing…</span>
                  : (fitnessInsight || status.desc)}
              </div>
            </div>

            {/* The three numbers behind the verdict */}
            <div style={{ display: 'flex', gap: 32 }}>
              {[
                { name: 'Fitness', abbr: 'CTL', value: dispCtl, color: 'var(--text-primary)', trend: ctlTrend, delta: deltaCtl },
                { name: 'Fatigue', abbr: 'ATL', value: dispAtl, color: 'var(--text-primary)', trend: atlTrend, delta: deltaAtl },
                { name: 'Form',    abbr: 'TSB', value: dispTsb > 0 ? `+${dispTsb}` : dispTsb, color: status.color, trend: tsbTrend, delta: null },
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
                <div style={{ ...statLabelStyle, marginBottom: 8 }}>Fitness · 6 weeks</div>
                <CtlSparkline data={fitnessHistory} />
              </div>
            )}
          </div>
        ) : hasFitnessData === false && fitnessData !== null ? (
          <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            Upload a few rides to start tracking fitness.
          </div>
        ) : null}
      </div>

      {/* ── 2. Training volume: am I riding enough? ───────────────────────── */}
      <div className={hasWeeklyData ? 'dash-row dash-row-week' : 'dash-row'}>

        {/* This Week */}
        <div className="panel" style={loadingStyle(!weeklyData)}>
          <div className="panel-title">This Week</div>
          {currentWeek && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '18px 24px' }}>
              {[
                { label: 'Rides',     value: currentWeek.rides,                                                 unit: null },
                { label: 'Distance',  value: currentWeek.distance_km > 0 ? currentWeek.distance_km.toFixed(1) : '—', unit: currentWeek.distance_km > 0 ? 'km' : null },
                { label: 'Time',      value: currentWeek.duration_seconds > 0 ? fmtDuration(currentWeek.duration_seconds) : '—', unit: null },
                { label: 'Elevation', value: currentWeek.elevation_m > 0 ? Math.round(currentWeek.elevation_m).toLocaleString() : '—', unit: currentWeek.elevation_m > 0 ? 'm' : null },
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
              {' '}{weekDeltaPct > 0 ? '+' : ''}{weekDeltaPct}% distance vs last week
            </div>
          )}
          {currentWeek?.rides === 0 && (
            <div style={{ marginTop: 16, fontSize: 12, color: 'var(--text-muted)' }}>No rides yet this week</div>
          )}
        </div>

        {/* Weekly Load — distance bars + stress line */}
        {hasWeeklyData && (
          <div className="chart-section" style={{ marginBottom: 0 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <div className="chart-title" style={{ marginBottom: 0 }}>
                Weekly Load · 12 weeks{' '}
                <InfoTip text="Green bars = distance per week (this week highlighted). Red line = training stress (TSS) — how hard those kilometres were. Aim for gradual increases with a lighter recovery week every 3–4 weeks." />
              </div>
              <div style={{ display: 'flex', gap: 14, alignItems: 'center' }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: 'var(--text-muted)' }}>
                  <span style={{ width: 8, height: 8, borderRadius: 2, background: 'oklch(65% 0.2 142)', display: 'inline-block', flexShrink: 0 }} />
                  Distance
                </span>
                {hasTSSData && (
                  <span style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: 'var(--text-muted)' }}>
                    <span style={{ width: 14, height: 2, background: 'var(--heart)', display: 'inline-block', flexShrink: 0 }} />
                    Stress (TSS)
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
          { key: 'distance',  label: 'Distance',  value: lastRide.distance_km.toFixed(1),                   unit: 'km'   },
          { key: 'time',      label: 'Time',       value: fmtDuration(lastRide.duration_seconds),            unit: null   },
          ...(lastRide.elevation_gain_m != null
            ? [{ key: 'elevation', label: 'Elevation', value: Math.round(lastRide.elevation_gain_m).toLocaleString(), unit: 'm' }]
            : []),
          { key: 'speed',     label: 'Avg Speed',  value: lastRide.avg_speed_kmh?.toFixed(1),               unit: 'km/h' },
          ...(lastRide.avg_heart_rate_bpm
            ? [{ key: 'heart_rate', label: 'Avg HR', value: `${Math.round(lastRide.avg_heart_rate_bpm)}`,  unit: 'bpm'  }]
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
            aria-label={`Last ride: ${lastRide.name}. Click to view.`}
          >
            {/* Identity */}
            <div className="lrs-identity">
              <div className="lrs-section-label">Last Ride</div>
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
                      <div className="lrs-metric-label">Stress</div>
                      <div className="lrs-metric-value">{Math.round(lastRide.tss)}</div>
                    </div>
                  )}
                  {lastRide.intensity_factor != null && (
                    <div className="lrs-metric">
                      <div className="lrs-metric-label">Intensity</div>
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
            Earlier Rides
          </div>
          <div className="recent-rides-list" role="list">
            <div className="rrl-head" aria-hidden="true">
              <span className="rrl-name">Ride</span>
              <span className="rrl-date">Date</span>
              <span className="rrl-stat">Distance</span>
              <span className="rrl-stat">Time</span>
              <span className="rrl-stat">Avg Speed</span>
            </div>
            {earlierRides.map(a => (
              <div
                key={a.id}
                className="rrl-row"
                role="button"
                tabIndex={0}
                aria-label={`${a.name}, ${format(new Date(a.date.slice(0, 10) + 'T12:00:00'), 'd MMM')}, ${a.distance_km.toFixed(1)} km`}
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
                    Durability
                  </span>
                  <InfoTip text="How well you hold your aerobic efficiency late into a ride (0–100). Higher = less fade in the final hour. Long steady rides build it." />
                </div>
                <div style={{ display: 'flex', gap: 20, alignItems: 'flex-start' }}>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 2 }}>Current avg</div>
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
                      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 2 }}>Best ever</div>
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
                      { label: 'Excellent', y: 95, color: '#6dffb8' },
                      { label: 'Good',      y: 88, color: '#4da6ff' },
                      { label: 'Moderate',  y: 80, color: '#ffd93d' },
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
                              <span style={{ fontSize: 11, color: 'var(--text-muted)', marginLeft: 4 }}>DI · {payload[0].payload.ride_count} ride{payload[0].payload.ride_count !== 1 ? 's' : ''}</span>
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
                <span className="panel-title" style={{ marginBottom: 0 }}>Heat Readiness</span>
                <InfoTip text="How adapted you are to riding in the heat, based on hot rides in the last 14 days. Your sweat rate sets personal hydration targets on ride pages." />
              </div>
              {[
                {
                  label: 'Adaptation',
                  value: heatProfile.heat_adaptation_level
                    ? heatProfile.heat_adaptation_level.charAt(0).toUpperCase() + heatProfile.heat_adaptation_level.slice(1)
                    : 'Low',
                  color: heatProfile.heat_adaptation_level === 'high' ? 'var(--status-good)' : heatProfile.heat_adaptation_level === 'moderate' ? 'var(--status-warn)' : 'var(--text-muted)',
                  sub: `${heatProfile.heat_rides_last_14d} hot ride${heatProfile.heat_rides_last_14d !== 1 ? 's' : ''} in 14 days`,
                  link: null,
                },
                {
                  label: 'Sweat Rate',
                  value: heatProfile.has_calibrated_rate ? `${Math.round(heatProfile.sweat_rate_ml_per_hour)} ml/h` : '—',
                  color: heatProfile.has_calibrated_rate ? 'var(--text-primary)' : 'var(--text-muted)',
                  sub: heatProfile.has_calibrated_rate ? 'Personal measurement' : null,
                  link: !heatProfile.has_calibrated_rate ? { to: '/settings', label: 'Calibrate in Settings' } : null,
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
