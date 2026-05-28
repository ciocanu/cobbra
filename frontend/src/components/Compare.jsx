import { useEffect, useState } from 'react'
import { getActivities, getActivity, getActivityClimbs } from '../services/api'
import { format } from 'date-fns'
import {
  LineChart, Line, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, Legend,
} from 'recharts'
import { GitCompare } from 'lucide-react'
import { colors } from '../tokens'

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

export default function Compare() {
  const [activities, setActivities] = useState([])
  const [id1, setId1] = useState('')
  const [id2, setId2] = useState('')
  const [act1, setAct1] = useState(null)
  const [act2, setAct2] = useState(null)
  const [climbs1, setClimbs1] = useState([])
  const [climbs2, setClimbs2] = useState([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    getActivities({ limit: 200 }).then(r => setActivities(r.data)).catch(console.error)
  }, [])

  useEffect(() => {
    if (!id1) { setAct1(null); setClimbs1([]); return }
    getActivity(id1).then(r => setAct1(r.data)).catch(console.error)
    getActivityClimbs(id1).then(r => setClimbs1(r.data)).catch(() => setClimbs1([]))
  }, [id1])

  useEffect(() => {
    if (!id2) { setAct2(null); setClimbs2([]); return }
    getActivity(id2).then(r => setAct2(r.data)).catch(console.error)
    getActivityClimbs(id2).then(r => setClimbs2(r.data)).catch(() => setClimbs2([]))
  }, [id2])

  const chartData = act1 && act2 ? merge(resample(act1.track_points), resample(act2.track_points)) : []
  const hasHR  = chartData.some(d => d.hr1 != null || d.hr2 != null)
  const hasCad = chartData.some(d => d.cad1 != null || d.cad2 != null)
  const hasEle = chartData.some(d => d.ele1 != null || d.ele2 != null)

  const statRows = act1 && act2 ? [
    { label: 'Distance',    v1: `${act1.distance_km.toFixed(2)} km`,          v2: `${act2.distance_km.toFixed(2)} km`,          win: act1.distance_km > act2.distance_km ? 1 : act2.distance_km > act1.distance_km ? 2 : 0 },
    { label: 'Time',        v1: fmtDuration(act1.duration_seconds),           v2: fmtDuration(act2.duration_seconds),           win: 0 },
    { label: 'Avg Speed',   v1: `${act1.avg_speed_kmh.toFixed(1)} km/h`,      v2: `${act2.avg_speed_kmh.toFixed(1)} km/h`,      win: act1.avg_speed_kmh > act2.avg_speed_kmh ? 1 : act2.avg_speed_kmh > act1.avg_speed_kmh ? 2 : 0 },
    { label: 'Max Speed',   v1: `${act1.max_speed_kmh.toFixed(1)} km/h`,      v2: `${act2.max_speed_kmh.toFixed(1)} km/h`,      win: act1.max_speed_kmh > act2.max_speed_kmh ? 1 : act2.max_speed_kmh > act1.max_speed_kmh ? 2 : 0 },
    ...(act1.avg_heart_rate_bpm && act2.avg_heart_rate_bpm ? [
      { label: 'Avg HR', v1: `${Math.round(act1.avg_heart_rate_bpm)} bpm`, v2: `${Math.round(act2.avg_heart_rate_bpm)} bpm`, win: act1.avg_heart_rate_bpm < act2.avg_heart_rate_bpm ? 1 : act2.avg_heart_rate_bpm < act1.avg_heart_rate_bpm ? 2 : 0 },
    ] : []),
    ...(act1.avg_cadence_rpm && act2.avg_cadence_rpm ? [
      { label: 'Avg Cadence', v1: `${Math.round(act1.avg_cadence_rpm)} rpm`, v2: `${Math.round(act2.avg_cadence_rpm)} rpm`, win: 0 },
    ] : []),
    { label: 'Elevation ↑', v1: `${act1.elevation_gain_m.toFixed(0)} m`,      v2: `${act2.elevation_gain_m.toFixed(0)} m`,      win: act1.elevation_gain_m > act2.elevation_gain_m ? 1 : act2.elevation_gain_m > act1.elevation_gain_m ? 2 : 0 },
    ...(act1.suffer_score != null && act2.suffer_score != null ? [
      { label: 'Suffer Score', v1: act1.suffer_score, v2: act2.suffer_score, win: act1.suffer_score > act2.suffer_score ? 1 : act2.suffer_score > act1.suffer_score ? 2 : 0 },
    ] : []),
    ...(act1.climb_count > 0 || act2.climb_count > 0 ? [
      { label: 'Climbs', v1: act1.climb_count || 0, v2: act2.climb_count || 0, win: (act1.climb_count || 0) > (act2.climb_count || 0) ? 1 : (act2.climb_count || 0) > (act1.climb_count || 0) ? 2 : 0 },
    ] : []),
    ...(act1.total_climbing_wkg_avg != null && act2.total_climbing_wkg_avg != null ? [
      { label: 'Climb W/kg', v1: `${act1.total_climbing_wkg_avg.toFixed(2)} W/kg`, v2: `${act2.total_climbing_wkg_avg.toFixed(2)} W/kg`, win: act1.total_climbing_wkg_avg > act2.total_climbing_wkg_avg ? 1 : act2.total_climbing_wkg_avg > act1.total_climbing_wkg_avg ? 2 : 0 },
    ] : []),
  ] : []

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Compare Activities</h1>
        <p className="page-subtitle">Side-by-side analysis of two rides</p>
      </div>

      {/* Selectors */}
      <div className="compare-selectors">
        <div className="compare-selector-box" style={{ borderColor: C1 }}>
          <div className="compare-label" style={{ color: C1 }}>Activity A</div>
          <select className="filter-input" style={{ width: '100%', borderColor: id1 ? C1 : undefined }}
            value={id1} onChange={e => setId1(e.target.value)}>
            <option value="">Select a ride…</option>
            {activities.filter(a => String(a.id) !== id2).map(a => (
              <option key={a.id} value={a.id}>
                {format(new Date(a.date), 'dd MMM yy')} — {a.name} ({a.distance_km.toFixed(1)} km)
              </option>
            ))}
          </select>
        </div>
        <div style={{ alignSelf: 'center', color: 'var(--text-muted)', fontSize: 20, fontWeight: 700 }}>vs</div>
        <div className="compare-selector-box" style={{ borderColor: C2 }}>
          <div className="compare-label" style={{ color: C2 }}>Activity B</div>
          <select className="filter-input" style={{ width: '100%', borderColor: id2 ? C2 : undefined }}
            value={id2} onChange={e => setId2(e.target.value)}>
            <option value="">Select a ride…</option>
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
          <h3>Select two rides to compare</h3>
        </div>
      )}

      {act1 && act2 && (
        <>
          {/* Stats table */}
          <div className="compare-table-wrap">
            <table className="compare-table">
              <thead>
                <tr>
                  <th style={{ color: C1, textAlign: 'left' }}>{act1.name}<br /><span style={{ color: 'var(--text-muted)', fontWeight: 400, fontSize: 11 }}>{format(new Date(act1.date), 'dd MMM yyyy')}</span></th>
                  <th style={{ textAlign: 'center', color: 'var(--text-muted)' }}></th>
                  <th style={{ color: C2, textAlign: 'right' }}>{act2.name}<br /><span style={{ color: 'var(--text-muted)', fontWeight: 400, fontSize: 11 }}>{format(new Date(act2.date), 'dd MMM yyyy')}</span></th>
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
                { key1: 'speed1', key2: 'speed2', label: 'Speed', unit: 'km/h', show: true },
                { key1: 'hr1',    key2: 'hr2',    label: 'Heart Rate', unit: 'bpm', show: hasHR },
                { key1: 'cad1',   key2: 'cad2',   label: 'Cadence',    unit: 'rpm', show: hasCad },
                { key1: 'ele1',   key2: 'ele2',    label: 'Elevation',  unit: 'm',   show: hasEle },
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

          {/* Climbs comparison */}
          {(climbs1.length > 0 || climbs2.length > 0) && (
            <div className="chart-section">
              <div className="chart-title">Climbs</div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <div>
                  <div style={{ fontSize: 11, fontWeight: 700, color: C1, textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8 }}>Activity A — {climbs1.length} climb{climbs1.length !== 1 ? 's' : ''}</div>
                  {climbs1.map((c, i) => (
                    <div key={c.id} style={{ marginBottom: 8, padding: '8px 10px', borderRadius: 8, border: `1px solid ${C1}30`, background: `${C1}08` }}>
                      <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 4 }}>Climb {i + 1} — {((c.distance_m || 0) / 1000).toFixed(1)} km @ {(c.avg_gradient_pct || 0).toFixed(1)}%</div>
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
                  {climbs1.length === 0 && <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>No climbs detected</div>}
                </div>
                <div>
                  <div style={{ fontSize: 11, fontWeight: 700, color: C2, textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8 }}>Activity B — {climbs2.length} climb{climbs2.length !== 1 ? 's' : ''}</div>
                  {climbs2.map((c, i) => (
                    <div key={c.id} style={{ marginBottom: 8, padding: '8px 10px', borderRadius: 8, border: `1px solid ${C2}30`, background: `${C2}08` }}>
                      <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 4 }}>Climb {i + 1} — {((c.distance_m || 0) / 1000).toFixed(1)} km @ {(c.avg_gradient_pct || 0).toFixed(1)}%</div>
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
                  {climbs2.length === 0 && <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>No climbs detected</div>}
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
