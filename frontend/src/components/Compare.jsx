import { useEffect, useState } from 'react'
import { getActivities, getActivity, getDurabilityAnalysis, compareDurability, getActivityClimbs } from '../services/api'
import { format } from 'date-fns'
import {
  LineChart, Line, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, Legend,
} from 'recharts'
import { GitCompare, Home, Trees } from 'lucide-react'
import { colors } from '../tokens'
import { useTranslation } from 'react-i18next'

function fmtDuration(s) {
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  return h > 0
    ? `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
    : `${m}:${String(sec).padStart(2, '0')}`
}

// Resample track points to N evenly-spaced distance % points
function resample(trackPoints, n = 100) {
  const pts = trackPoints.filter(p => p.distance_m != null)
  if (pts.length < 2) return []
  const maxDist = pts[pts.length - 1].distance_m
  const result = []
  for (let i = 0; i <= n; i++) {
    const target = (i / n) * maxDist
    let closest = pts[0]
    let minD = Math.abs(pts[0].distance_m - target)
    for (const p of pts) {
      const d = Math.abs(p.distance_m - target)
      if (d < minD) { minD = d; closest = p }
    }
    result.push({ pct: i, speed: closest.speed_kmh, hr: closest.heart_rate_bpm, cad: closest.cadence_rpm, ele: closest.elevation })
  }
  return result
}

function merge(a, b) {
  const len = Math.max(a.length, b.length)
  return Array.from({ length: len }, (_, i) => ({
    pct: i,
    speed1: a[i]?.speed ?? null, speed2: b[i]?.speed ?? null,
    hr1: a[i]?.hr ?? null,       hr2: b[i]?.hr ?? null,
    cad1: a[i]?.cad ?? null,     cad2: b[i]?.cad ?? null,
    ele1: a[i]?.ele ?? null,     ele2: b[i]?.ele ?? null,
  }))
}

const CompareTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  return (
    <div style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-bright)', borderRadius: 6, padding: '8px 12px', fontSize: 12 }}>
      <div style={{ color: 'var(--text-muted)', marginBottom: 4 }}>{label}%</div>
      {payload.map(p => p.value != null && (
        <div key={p.dataKey} style={{ color: p.color }}>{p.name}: {p.value?.toFixed(1)}</div>
      ))}
    </div>
  )
}

const C1 = colors.accent  // activity 1 — venom
const C2 = '#4da6ff'  // activity 2 — blue

const PLATFORM_LABELS = {
  zwift: 'Zwift', trainerroad: 'TrainerRoad', wahoo: 'Wahoo SYSTM',
  mywhoosh: 'MyWhoosh', rolo: 'Trainer', other: 'Indoor',
}

function envLabel(act) {
  if (!act?.ride_environment || act.ride_environment === 'unknown') return null
  if (act.ride_environment === 'indoor') return PLATFORM_LABELS[act.indoor_platform] || 'Indoor'
  return 'Outdoor'
}

function EnvTag({ act, color }) {
  const label = envLabel(act)
  if (!label) return null
  const isIndoor = act.ride_environment === 'indoor'
  const c = isIndoor ? '#a78bfa' : '#6dffb8'
  const Icon = isIndoor ? Home : Trees
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3, fontSize: 10, fontWeight: 600, color: c, background: `${c}18`, border: `1px solid ${c}40`, borderRadius: 5, padding: '2px 6px', marginLeft: 6 }}>
      <Icon size={9} /> {label}
    </span>
  )
}

export default function Compare() {
  const { t } = useTranslation()
  const [activities, setActivities] = useState([])
  const [id1, setId1] = useState('')
  const [id2, setId2] = useState('')
  const [act1, setAct1] = useState(null)
  const [act2, setAct2] = useState(null)
  const [climbs1, setClimbs1] = useState([])
  const [climbs2, setClimbs2] = useState([])
  const [loading, setLoading] = useState(false)
  const [dur1, setDur1] = useState(null)
  const [dur2, setDur2] = useState(null)
  const [compareNote, setCompareNote] = useState('')

  useEffect(() => {
    getActivities({ limit: 200 }).then(r => setActivities(r.data?.items ?? r.data)).catch(console.error)
  }, [])

  useEffect(() => {
    if (!id1) { setAct1(null); setDur1(null); setClimbs1([]); return }
    getActivity(id1).then(r => setAct1(r.data)).catch(console.error)
    getDurabilityAnalysis(id1).then(r => setDur1(r.data)).catch(() => setDur1(null))
    getActivityClimbs(id1).then(r => setClimbs1(r.data)).catch(() => setClimbs1([]))
  }, [id1])

  useEffect(() => {
    if (!id2) { setAct2(null); setDur2(null); setClimbs2([]); return }
    getActivity(id2).then(r => setAct2(r.data)).catch(console.error)
    getDurabilityAnalysis(id2).then(r => setDur2(r.data)).catch(() => setDur2(null))
    getActivityClimbs(id2).then(r => setClimbs2(r.data)).catch(() => setClimbs2([]))
  }, [id2])

  useEffect(() => {
    if (!id1 || !id2) { setCompareNote(''); return }
    compareDurability([Number(id1), Number(id2)])
      .then(r => setCompareNote(r.data.comparison_note))
      .catch(() => setCompareNote(''))
  }, [id1, id2])

  const chartData = act1 && act2 ? merge(resample(act1.track_points), resample(act2.track_points)) : []
  const hasHR  = chartData.some(d => d.hr1 != null || d.hr2 != null)
  const hasCad = chartData.some(d => d.cad1 != null || d.cad2 != null)
  const hasEle = chartData.some(d => d.ele1 != null || d.ele2 != null)

  const statRows = act1 && act2 ? [
    { label: t('compare.statDistance'),    v1: `${act1.distance_km.toFixed(2)} km`,          v2: `${act2.distance_km.toFixed(2)} km`,          win: act1.distance_km > act2.distance_km ? 1 : act2.distance_km > act1.distance_km ? 2 : 0 },
    { label: t('compare.statTime'),        v1: fmtDuration(act1.duration_seconds),           v2: fmtDuration(act2.duration_seconds),           win: 0 },
    { label: t('compare.statAvgSpeed'),    v1: `${act1.avg_speed_kmh.toFixed(1)} km/h`,      v2: `${act2.avg_speed_kmh.toFixed(1)} km/h`,      win: act1.avg_speed_kmh > act2.avg_speed_kmh ? 1 : act2.avg_speed_kmh > act1.avg_speed_kmh ? 2 : 0 },
    { label: t('compare.statMaxSpeed'),    v1: `${act1.max_speed_kmh.toFixed(1)} km/h`,      v2: `${act2.max_speed_kmh.toFixed(1)} km/h`,      win: act1.max_speed_kmh > act2.max_speed_kmh ? 1 : act2.max_speed_kmh > act1.max_speed_kmh ? 2 : 0 },
    ...(act1.avg_heart_rate_bpm && act2.avg_heart_rate_bpm ? [
      { label: t('compare.statAvgHR'), v1: `${Math.round(act1.avg_heart_rate_bpm)} bpm`, v2: `${Math.round(act2.avg_heart_rate_bpm)} bpm`, win: act1.avg_heart_rate_bpm < act2.avg_heart_rate_bpm ? 1 : act2.avg_heart_rate_bpm < act1.avg_heart_rate_bpm ? 2 : 0 },
    ] : []),
    ...(act1.avg_cadence_rpm && act2.avg_cadence_rpm ? [
      { label: t('compare.statAvgCadence'), v1: `${Math.round(act1.avg_cadence_rpm)} rpm`, v2: `${Math.round(act2.avg_cadence_rpm)} rpm`, win: 0 },
    ] : []),
    { label: t('compare.statElevation'), v1: `${act1.elevation_gain_m.toFixed(0)} m`,      v2: `${act2.elevation_gain_m.toFixed(0)} m`,      win: act1.elevation_gain_m > act2.elevation_gain_m ? 1 : act2.elevation_gain_m > act1.elevation_gain_m ? 2 : 0 },
    ...(act1.suffer_score != null && act2.suffer_score != null ? [
      { label: t('compare.statSufferScore'), v1: act1.suffer_score, v2: act2.suffer_score, win: act1.suffer_score > act2.suffer_score ? 1 : act2.suffer_score > act1.suffer_score ? 2 : 0 },
    ] : []),
    ...(dur1 && dur2 && dur1.durability_index != null && dur2.durability_index != null ? [
      { label: t('compare.statDurabilityIndex'), v1: `${dur1.durability_index.toFixed(1)}`, v2: `${dur2.durability_index.toFixed(1)}`, win: dur1.durability_index > dur2.durability_index ? 1 : dur2.durability_index > dur1.durability_index ? 2 : 0 },
    ] : []),
    ...(dur1 && dur2 && dur1.fade_rate_pct_per_hour != null && dur2.fade_rate_pct_per_hour != null ? [
      { label: t('compare.statFadeRate'), v1: `${dur1.fade_rate_pct_per_hour.toFixed(1)}%`, v2: `${dur2.fade_rate_pct_per_hour.toFixed(1)}%`, win: dur1.fade_rate_pct_per_hour < dur2.fade_rate_pct_per_hour ? 1 : dur2.fade_rate_pct_per_hour < dur1.fade_rate_pct_per_hour ? 2 : 0 },
    ] : []),
    ...(act1.climb_count > 0 || act2.climb_count > 0 ? [
      { label: t('compare.statClimbs'), v1: act1.climb_count || 0, v2: act2.climb_count || 0, win: (act1.climb_count || 0) > (act2.climb_count || 0) ? 1 : (act2.climb_count || 0) > (act1.climb_count || 0) ? 2 : 0 },
    ] : []),
    ...(act1.total_climbing_wkg_avg != null && act2.total_climbing_wkg_avg != null ? [
      { label: t('compare.statClimbWkg'), v1: `${act1.total_climbing_wkg_avg.toFixed(2)} W/kg`, v2: `${act2.total_climbing_wkg_avg.toFixed(2)} W/kg`, win: act1.total_climbing_wkg_avg > act2.total_climbing_wkg_avg ? 1 : act2.total_climbing_wkg_avg > act1.total_climbing_wkg_avg ? 2 : 0 },
    ] : []),
  ] : []

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">{t('compare.title')}</h1>
        <p className="page-subtitle">{t('compare.subtitle')}</p>
      </div>

      {/* Selectors */}
      <div className="compare-selectors">
        <div className="compare-selector-box" style={{ borderColor: C1 }}>
          <div className="compare-label" style={{ color: C1 }}>{t('compare.activityA')}</div>
          <select className="filter-input" style={{ width: '100%', borderColor: id1 ? C1 : undefined }}
            value={id1} onChange={e => setId1(e.target.value)}>
            <option value="">{t('compare.selectRidePlaceholder')}</option>
            {activities.filter(a => String(a.id) !== id2).map(a => (
              <option key={a.id} value={a.id}>
                {format(new Date(a.date), 'dd MMM yy')} — {a.name} ({a.distance_km.toFixed(1)} km)
              </option>
            ))}
          </select>
        </div>
        <div style={{ alignSelf: 'center', color: 'var(--text-muted)', fontSize: 20, fontWeight: 700 }}>{t('compare.vsLabel')}</div>
        <div className="compare-selector-box" style={{ borderColor: C2 }}>
          <div className="compare-label" style={{ color: C2 }}>{t('compare.activityB')}</div>
          <select className="filter-input" style={{ width: '100%', borderColor: id2 ? C2 : undefined }}
            value={id2} onChange={e => setId2(e.target.value)}>
            <option value="">{t('compare.selectRidePlaceholder')}</option>
            {activities.filter(a => String(a.id) !== id1).map(a => (
              <option key={a.id} value={a.id}>
                {format(new Date(a.date), 'dd MMM yy')} — {a.name} ({a.distance_km.toFixed(1)} km)
              </option>
            ))}
          </select>
        </div>
      </div>

      {(!act1 || !act2) && (
        <div className="empty-state" style={{ marginTop: 40 }}>
          <div className="empty-state-icon"><GitCompare size={48} /></div>
          <h3>{t('compare.emptyStateTitle')}</h3>
        </div>
      )}

      {act1 && act2 && (
        <>
          {/* Stats table */}
          <div className="compare-table-wrap">
            <table className="compare-table">
              <thead>
                <tr>
                  <th style={{ color: C1, textAlign: 'left' }}>
                    {act1.name}
                    <EnvTag act={act1} color={C1} />
                    <br />
                    <span style={{ color: 'var(--text-muted)', fontWeight: 400, fontSize: 11 }}>{format(new Date(act1.date), 'dd MMM yyyy')}</span>
                  </th>
                  <th style={{ textAlign: 'center', color: 'var(--text-muted)' }}></th>
                  <th style={{ color: C2, textAlign: 'right' }}>
                    {act2.name}
                    <EnvTag act={act2} color={C2} />
                    <br />
                    <span style={{ color: 'var(--text-muted)', fontWeight: 400, fontSize: 11 }}>{format(new Date(act2.date), 'dd MMM yyyy')}</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {statRows.map(row => (
                  <tr key={row.label}>
                    <td style={{ fontFamily: 'var(--font-display)', fontSize: 17, fontWeight: row.win === 1 ? 700 : 400, color: row.win === 1 ? C1 : 'var(--text-primary)' }}>
                      {row.v1} {row.win === 1 && '◀'}
                    </td>
                    <td style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: 12 }}>{row.label}</td>
                    <td style={{ fontFamily: 'var(--font-display)', fontSize: 17, fontWeight: row.win === 2 ? 700 : 400, color: row.win === 2 ? C2 : 'var(--text-primary)', textAlign: 'right' }}>
                      {row.win === 2 && '▶ '}{row.v2}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Charts */}
          {chartData.length > 0 && (
            <>
              {[
                { key1: 'speed1', key2: 'speed2', label: t('compare.chartSpeed'),     unit: 'km/h', show: true },
                { key1: 'hr1',    key2: 'hr2',    label: t('compare.chartHeartRate'), unit: 'bpm', show: hasHR },
                { key1: 'cad1',   key2: 'cad2',   label: t('compare.chartCadence'),   unit: 'rpm', show: hasCad },
                { key1: 'ele1',   key2: 'ele2',   label: t('compare.chartElevation'), unit: 'm',   show: hasEle },
              ].filter(c => c.show).map(({ key1, key2, label, unit }) => (
                <div key={label} className="chart-section">
                  <div className="chart-title">{label}</div>
                  <ResponsiveContainer width="100%" height={160}>
                    <LineChart data={chartData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                      <XAxis dataKey="pct" hide />
                      <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 11 }} axisLine={false} tickLine={false} unit={` ${unit}`} width={52} />
                      <Tooltip content={<CompareTooltip />} />
                      <Line type="monotone" dataKey={key1} stroke={C1} dot={false} strokeWidth={2} name={`A ${unit}`} connectNulls />
                      <Line type="monotone" dataKey={key2} stroke={C2} dot={false} strokeWidth={2} name={`B ${unit}`} connectNulls />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              ))}
            </>
          )}

          {/* Mixed indoor/outdoor warning */}
          {act1.ride_environment && act2.ride_environment
            && act1.ride_environment !== 'unknown' && act2.ride_environment !== 'unknown'
            && act1.ride_environment !== act2.ride_environment && (
            <div style={{ marginTop: 8, padding: '12px 16px', background: '#a78bfa0a', border: '1px solid #a78bfa28', borderRadius: 10, fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.6, display: 'flex', gap: 8 }}>
              <Home size={14} style={{ color: '#a78bfa', flexShrink: 0, marginTop: 1 }} />
              <span>
                {t('compare.indoorOutdoorWarning')}
                {(act1.corrected_tss != null || act2.corrected_tss != null) && (
                  <>{t('compare.indoorOutdoorWarningTSS')}</>
                )}
              </span>
            </div>
          )}

          {/* Durability comparison note */}
          {compareNote && (
            <div style={{ marginTop: 8, padding: '12px 16px', background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 10, fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.5 }}>
              <span style={{ fontSize: 10, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--text-muted)', display: 'block', marginBottom: 6 }}>{t('compare.durabilityComparisonTitle')}</span>
              {compareNote}
            </div>
          )}

          {/* Climbs comparison */}
          {(climbs1.length > 0 || climbs2.length > 0) && (
            <div className="chart-section">
              <div className="chart-title">{t('compare.climbsTitle')}</div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <div>
                  <div style={{ fontSize: 11, fontWeight: 700, color: C1, textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8 }}>
                    {t(climbs1.length === 1 ? 'compare.climbsActivityA' : 'compare.climbsActivityA_plural', { count: climbs1.length })}
                  </div>
                  {climbs1.map((c, i) => (
                    <div key={c.id} style={{ marginBottom: 8, padding: '8px 10px', borderRadius: 8, border: `1px solid ${C1}30`, background: `${C1}08` }}>
                      <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 4 }}>
                        {t('compare.climbLabel', { number: i + 1, distance: ((c.distance_m || 0) / 1000).toFixed(1), gradient: (c.avg_gradient_pct || 0).toFixed(1) })}
                      </div>
                      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                        {c.estimated_power_w != null && (
                          <span style={{ fontSize: 13, fontFamily: 'var(--font-display)', color: C1 }}>{Math.round(c.estimated_power_w)}W</span>
                        )}
                        {c.estimated_wkg != null && (
                          <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{c.estimated_wkg.toFixed(2)} W/kg</span>
                        )}
                        {c.vam_m_per_hour != null && (
                          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>VAM {Math.round(c.vam_m_per_hour)}</span>
                        )}
                      </div>
                    </div>
                  ))}
                  {climbs1.length === 0 && <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{t('compare.noClimbsDetected')}</div>}
                </div>
                <div>
                  <div style={{ fontSize: 11, fontWeight: 700, color: C2, textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8 }}>
                    {t(climbs2.length === 1 ? 'compare.climbsActivityB' : 'compare.climbsActivityB_plural', { count: climbs2.length })}
                  </div>
                  {climbs2.map((c, i) => (
                    <div key={c.id} style={{ marginBottom: 8, padding: '8px 10px', borderRadius: 8, border: `1px solid ${C2}30`, background: `${C2}08` }}>
                      <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 4 }}>
                        {t('compare.climbLabel', { number: i + 1, distance: ((c.distance_m || 0) / 1000).toFixed(1), gradient: (c.avg_gradient_pct || 0).toFixed(1) })}
                      </div>
                      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                        {c.estimated_power_w != null && (
                          <span style={{ fontSize: 13, fontFamily: 'var(--font-display)', color: C2 }}>{Math.round(c.estimated_power_w)}W</span>
                        )}
                        {c.estimated_wkg != null && (
                          <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{c.estimated_wkg.toFixed(2)} W/kg</span>
                        )}
                        {c.vam_m_per_hour != null && (
                          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>VAM {Math.round(c.vam_m_per_hour)}</span>
                        )}
                      </div>
                    </div>
                  ))}
                  {climbs2.length === 0 && <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{t('compare.noClimbsDetected')}</div>}
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
