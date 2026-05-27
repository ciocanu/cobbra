import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  getActivities, getFitnessStats, getWeeklyStats,
  getDashboardFitnessInsight,
} from '../services/api'
import {
  BarChart, Bar, Cell, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from 'recharts'
import { format } from 'date-fns'
import { Route } from 'lucide-react'
import InfoTip from './InfoTip'

function fmtDuration(seconds) {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  return h > 0 ? `${h}h ${m}m` : `${m}m`
}

function CtlSparkline({ data }) {
  if (!data || data.length < 2) return null
  const vals = data.map(d => d.ctl)
  const min = Math.min(...vals)
  const max = Math.max(...vals)
  const range = max - min || 1
  const W = 160, H = 36
  const pts = vals.map((v, i) => {
    const x = (i / (vals.length - 1)) * W
    const y = H - 4 - ((v - min) / range) * (H - 8)
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
  return (
    <svg width={W} height={H} style={{ display: 'block', opacity: 0.7 }}>
      <polyline points={pts} fill="none" stroke="var(--speed)" strokeWidth={1.5} />
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
  const [recentRides, setRecentRides]       = useState(null)
  const [weeklyData, setWeeklyData]         = useState(null)
  const [fitnessData, setFitnessData]       = useState(null)
  const [fitnessInsight, setFitnessInsight] = useState(null) // null=loading, false=failed
  const navigate = useNavigate()

  useEffect(() => {
    getActivities({ limit: 7 }).then(r => setRecentRides(r.data)).catch(() => setRecentRides([]))
    getWeeklyStats(16).then(r => setWeeklyData(r.data)).catch(() => setWeeklyData([]))
    getFitnessStats(60).then(r => setFitnessData(r.data)).catch(() => setFitnessData([]))
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
          <p className="page-subtitle">Training overview</p>
        </div>
        <div className="empty-state">
          <div className="empty-state-icon"><Route size={48} /></div>
          <h3>No rides yet</h3>
          <p>Upload your first .gpx or .fit file to get started</p>
        </div>
      </div>
    )
  }

  const panelStyle = (loading) => ({
    background: 'var(--bg-card)',
    border: '1px solid var(--border)',
    borderRadius: 12,
    padding: '20px 24px',
    opacity: loading ? 0.4 : 1,
    transition: 'opacity 0.2s',
  })

  const labelStyle = {
    fontSize: 12,
    fontWeight: 600,
    textTransform: 'uppercase',
    letterSpacing: 1,
    color: 'var(--text-muted)',
    marginBottom: 16,
  }

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Dashboard</h1>
        <p className="page-subtitle">Training overview</p>
      </div>

      {/* ── Last Ride ─────────────────────────────────────────────────────── */}
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
            style={{ marginBottom: 20 }}
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
                      <div className="lrs-metric-label">TSS</div>
                      <div className="lrs-metric-value">{Math.round(lastRide.tss)}</div>
                    </div>
                  )}
                  {lastRide.intensity_factor != null && (
                    <div className="lrs-metric">
                      <div className="lrs-metric-label">IF</div>
                      <div className="lrs-metric-value">{lastRide.intensity_factor.toFixed(2)}</div>
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        )
      })()}

      {/* ── Two-column: This Week + Fitness & Freshness ───────────────────── */}
      <div className="dashboard-panels">

        {/* This Week */}
        <div style={panelStyle(!weeklyData)}>
          <div style={labelStyle}>This Week</div>
          {currentWeek && [
            { label: 'Rides',     value: currentWeek.rides,                                                 unit: null },
            { label: 'Distance',  value: currentWeek.distance_km > 0 ? currentWeek.distance_km.toFixed(1) : '—', unit: currentWeek.distance_km > 0 ? 'km' : null },
            { label: 'Time',      value: currentWeek.duration_seconds > 0 ? fmtDuration(currentWeek.duration_seconds) : '—', unit: null },
            { label: 'Elevation', value: currentWeek.elevation_m > 0 ? Math.round(currentWeek.elevation_m).toLocaleString() : '—', unit: currentWeek.elevation_m > 0 ? 'm' : null },
          ].map(({ label, value, unit }, i, arr) => (
            <div key={label} style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: '8px 0',
              borderBottom: i < arr.length - 1 ? '1px solid var(--border)' : 'none',
            }}>
              <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{label}</span>
              <span style={{ fontFamily: 'var(--font-display)', fontSize: 16, fontWeight: 600, color: 'var(--text-primary)' }}>
                {value}
                {unit && <span style={{ fontSize: 12, fontWeight: 400, color: 'var(--text-muted)', marginLeft: 3 }}>{unit}</span>}
              </span>
            </div>
          ))}
          {weekDeltaPct !== null && currentWeek?.rides > 0 && (
            <div style={{
              marginTop: 14,
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
            <div style={{ marginTop: 14, fontSize: 12, color: 'var(--text-muted)' }}>No rides yet this week</div>
          )}
        </div>

        {/* Fitness & Freshness */}
        <div style={{
          background: 'var(--bg-card)',
          borderRadius: 'var(--radius)',
          padding: '20px 24px',
          opacity: !fitnessData ? 0.4 : 1,
          transition: 'opacity 0.2s',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 16 }}>
            <span style={{ fontSize: 10, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--text-muted)' }}>
              Fitness &amp; Freshness
            </span>
            <InfoTip text="CTL (Fitness) = 42-day rolling training load. ATL (Fatigue) = 7-day load. TSB (Form) = CTL − ATL. Positive TSB = fresh and ready. Negative = carrying training fatigue." />
          </div>

          {currentFitness && hasFitnessData ? (
            <>
              {/* Three metrics — horizontal, no boxes */}
              <div style={{ display: 'flex', gap: 32, marginBottom: 16 }}>
                {(() => {
                  const tsbColor = currentFitness.tsb >= 5
                    ? 'var(--accent)'
                    : currentFitness.tsb <= -20
                      ? 'var(--heart)'
                      : 'var(--text-secondary)'

                  return [
                    { abbr: 'CTL', name: 'Fitness',  value: currentFitness.ctl,  color: 'var(--text-primary)', trend: ctlTrend },
                    { abbr: 'ATL', name: 'Fatigue',  value: currentFitness.atl,  color: 'var(--text-primary)', trend: atlTrend },
                    { abbr: 'TSB', name: 'Form',     value: currentFitness.tsb > 0 ? `+${currentFitness.tsb}` : currentFitness.tsb, color: tsbColor, trend: tsbTrend },
                  ].map(({ abbr, name, value, color, trend }) => (
                    <div key={abbr}>
                      <div style={{ fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-muted)', marginBottom: 6 }}>
                        {abbr}
                      </div>
                      <div style={{ display: 'flex', alignItems: 'baseline', gap: 3, lineHeight: 1 }}>
                        <span style={{ fontFamily: 'var(--font-display)', fontSize: 22, fontWeight: 700, color, transition: 'color 200ms ease' }}>
                          {value}
                        </span>
                        {trend !== 0 && (
                          <span style={{ fontSize: 11, color: 'var(--text-muted)', lineHeight: 1 }}>
                            {trend > 0 ? '↑' : '↓'}
                          </span>
                        )}
                      </div>
                      <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 4 }}>{name}</div>
                    </div>
                  ))
                })()}
              </div>

              {/* Coaching interpretation */}
              <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.5, marginBottom: 16, minHeight: 18 }}>
                {fitnessInsight === null
                  ? <span style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>Analyzing…</span>
                  : fitnessInsight || null}
              </div>

              {/* CTL sparkline */}
              {fitnessHistory.length >= 7 && (
                <div>
                  <div style={{ fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-muted)', marginBottom: 8 }}>
                    CTL trajectory · 6 weeks
                  </div>
                  <CtlSparkline data={fitnessHistory} />
                </div>
              )}
            </>
          ) : hasFitnessData === false && fitnessData !== null ? (
            <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
              Upload a few rides to start tracking fitness.
            </div>
          ) : null}
        </div>
      </div>

      {/* ── Weekly Load ───────────────────────────────────────────────────── */}
      {hasWeeklyData && (
        <div className="chart-section" style={{ marginBottom: 24 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <div className="chart-title" style={{ marginBottom: 0 }}>
              Weekly Load{' '}
              <InfoTip text="Distance (km) and training stress (TSS) per week. Spikes = overloading. Flat sections = detraining. Aim for gradual week-to-week increases with regular recovery weeks." />
            </div>
            <div style={{ display: 'flex', gap: 14, alignItems: 'center' }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: 'var(--text-muted)' }}>
                <span style={{ width: 8, height: 8, borderRadius: 2, background: 'oklch(65% 0.2 142)', display: 'inline-block', flexShrink: 0 }} />
                Distance
              </span>
              {hasTSSData && (
                <span style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: 'var(--text-muted)' }}>
                  <span style={{ width: 8, height: 8, borderRadius: 2, background: 'color-mix(in srgb, var(--heart) 55%, transparent)', display: 'inline-block', flexShrink: 0 }} />
                  TSS
                </span>
              )}
            </div>
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={weeklyDisplay} barCategoryGap="32%" barGap={3}>
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
                <Bar yAxisId="ss" dataKey="tss" fill="color-mix(in srgb, var(--heart) 50%, transparent)" radius={[3, 3, 0, 0]} name="TSS">
                  {weeklyDisplay.map(w => (
                    <Cell key={w.week} fill="color-mix(in srgb, var(--heart) 50%, transparent)" />
                  ))}
                </Bar>
              )}
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* ── Recent Rides ──────────────────────────────────────────────────── */}
      {recentRides?.length > 0 && (
        <>
          <div style={{ fontSize: 10, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--text-muted)', marginBottom: 4, marginTop: 24 }}>
            Recent Rides
          </div>
          <div className="recent-rides-list" role="list">
            {recentRides.map(a => (
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
        </>
      )}
    </div>
  )
}
